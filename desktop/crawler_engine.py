"""AWEC compliance-first recursive crawler.

Fast, resumable, domain-aware crawler core. It deliberately does not bypass
WAF/anti-bot controls, rotate IPs to evade blocks, spoof fingerprints, or
ignore robots.txt unless the operator explicitly enables that policy.
"""
from __future__ import annotations

import asyncio, hashlib, json, os, re, time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
from bs4 import BeautifulSoup

DEFAULT_TYPES = {'.jpg','.jpeg','.png','.gif','.webp','.svg','.mp4','.webm','.mp3','.wav','.pdf','.zip','.txt','.json','.xml'}

@dataclass
class CrawlPolicy:
    follow_links: bool = True
    follow_external_domains: bool = False
    include_subdomains: bool = True
    download_files: bool = True
    respect_robots: bool = True
    max_depth: int = 3
    max_file_size: int = -1
    file_types: list[str] = field(default_factory=lambda: sorted(DEFAULT_TYPES))
    workers: int = 16
    rate_limit_per_host: float = 2.0
    retry_delays: list[int] = field(default_factory=lambda: [10, 20])

@dataclass
class Seed:
    url: str
    policy: CrawlPolicy = field(default_factory=CrawlPolicy)

class Checkpoint:
    def __init__(self, path: str): self.path = Path(path)
    def save(self, state: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, self.path)
    def load(self):
        return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else None

class AWECrawler:
    def __init__(self, seeds: list[Seed], checkpoint: str, on_event=None, output_dir=None):
        self.seeds = seeds
        self.checkpoint = Checkpoint(checkpoint)
        self.on_event = on_event or (lambda *_: None)
        self.output_dir = Path(output_dir) if output_dir else None
        self.queue: asyncio.Queue = asyncio.Queue()
        self.pending: list[list] = []
        self.seen: set[str] = set()
        self.downloaded: set[str] = set()
        self.paused = False; self.stopped = False
        self.stats = {'status':'AWEC Stopped','pages':0,'files':0,'bytes':0,'errors':0,'queued':0,'domains':0,'skipped_robots':0}
        self.domain_bytes = {}; self.host_last = {}; self.robots = {}; self.domain_set=set()
        self._state_lock=asyncio.Lock(); self._last_checkpoint=0.0

    def emit(self, event, **data):
        payload={**self.stats, **data}; self.on_event(event,payload)

    @staticmethod
    def domain(url): return (urlparse(url).hostname or '').lower().rstrip('.')

    def allowed(self, url, seed):
        u=urlparse(url); host=self.domain(url); root=self.domain(seed.url)
        if u.scheme not in ('http','https') or not host: return False
        same=host==root or (seed.policy.include_subdomains and host.endswith('.'+root))
        return same or seed.policy.follow_external_domains

    async def enqueue(self, url, seed, depth):
        url=url.split('#',1)[0].strip()
        if not url or url in self.seen or depth > seed.policy.max_depth or not self.allowed(url,seed): return
        self.seen.add(url); self.domain_set.add(self.domain(url)); await self.queue.put((url,seed,depth)); self.stats['queued']=self.queue.qsize(); self.stats['domains']=len(self.domain_set)

    async def can_fetch(self, session, url, policy):
        if not policy.respect_robots: return True
        p=urlparse(url); root=f'{p.scheme}://{p.netloc}'
        rp=self.robots.get(root)
        if rp is None:
            rp=RobotFileParser(); rp.set_url(root+'/robots.txt')
            try:
                async with session.get(root+'/robots.txt',timeout=aiohttp.ClientTimeout(total=10)) as r:
                    text=(await r.text(errors='ignore')) if r.status < 400 else ''
                rp.parse(text.splitlines()); self.robots[root]=rp
            except Exception:
                # Fail closed for robots retrieval failures.
                self.robots[root]=False; return False
        return bool(rp) and rp.can_fetch('AWEC/1.0',url)

    async def fetch(self, session, url, policy):
        if not await self.can_fetch(session,url,policy):
            self.stats['skipped_robots']+=1; self.emit('robots_skip',url=url); return None,None
        for attempt in range(len(policy.retry_delays)+1):
            try:
                host=self.domain(url); interval=max(0.0,policy.rate_limit_per_host)
                wait=interval-(time.monotonic()-self.host_last.get(host,0))
                if wait>0: await asyncio.sleep(wait)
                self.host_last[host]=time.monotonic()
                async with session.get(url,allow_redirects=True,timeout=aiohttp.ClientTimeout(total=45),headers={'User-Agent':'AWEC/1.0 (respectful archival crawler)'}) as r:
                    if r.status in (408,425,429,500,502,503,504): raise RuntimeError(f'HTTP {r.status}')
                    if r.status>=400: return None,r.status
                    data=await r.read(); return (r.headers.get('content-type',''),data,r.url),r.status
            except Exception as e:
                self.stats['errors']+=1; self.emit('error',url=url,error=str(e),attempt=attempt+1)
                if attempt < len(policy.retry_delays): await asyncio.sleep(policy.retry_delays[attempt])
        return None,None

    @staticmethod
    def is_file(url,ctype,types):
        ext=Path(urlparse(url).path.lower()).suffix
        if '*' in {x.lower() for x in types}: return not ('html' in ctype.lower())
        return ext in {x.lower() for x in types}

    def persist_file(self,url,data):
        if not self.output_dir: return None
        domain=self.domain(url); fid=hashlib.sha256(url.encode()).hexdigest()[:16]
        ext=Path(urlparse(url).path).suffix or '.bin'; folder=self.output_dir/domain; folder.mkdir(parents=True,exist_ok=True)
        path=folder/f'{fid}{ext}'
        if not path.exists(): path.write_bytes(data)
        self.downloaded.add(url); return str(path)

    async def worker(self,session):
        while not self.stopped:
            if self.paused: await asyncio.sleep(.2); continue
            try: url,seed,depth=await asyncio.wait_for(self.queue.get(),.5)
            except asyncio.TimeoutError: continue
            try:
                result,_=await self.fetch(session,url,seed.policy)
                if not result: continue
                ctype,data,final=result; self.stats['pages']+=1; self.stats['bytes']+=len(data)
                d=self.domain(final); self.domain_bytes[d]=self.domain_bytes.get(d,0)+len(data)
                if seed.policy.download_files and self.is_file(str(final),ctype,seed.policy.file_types):
                    allowed_size=seed.policy.max_file_size<0 or len(data)<=seed.policy.max_file_size
                    if allowed_size: self.stats['files']+=1; path=self.persist_file(str(final),data); self.emit('file',url=str(final),path=path,size=len(data))
                if seed.policy.follow_links and ('html' in ctype.lower() or not ctype):
                    soup=BeautifulSoup(data,'html.parser')
                    for tag,attr in [('a','href'),('link','href'),('img','src'),('script','src'),('source','src'),('video','src'),('audio','src')]:
                        for node in soup.find_all(tag,**{attr:True}): await self.enqueue(urljoin(str(final),node[attr]),seed,depth+1)
                self.emit('page',url=str(final),depth=depth)
            finally:
                self.queue.task_done(); self.stats['queued']=self.queue.qsize()
                await self.save_checkpoint()

    async def save_checkpoint(self):
        async with self._state_lock:
            state=self.state(); self.checkpoint.save(state); self._last_checkpoint=time.monotonic()

    def state(self):
        # Queue contents are reconstructed from pending URLs stored by the producer/worker lifecycle.
        return {'seen':list(self.seen),'downloaded':list(self.downloaded),'pending':list(self.pending),'stats':self.stats,'domain_bytes':self.domain_bytes,'seeds':[asdict(s) for s in self.seeds]}

    async def run(self):
        self.stats['status']='AWEC Running'; self.emit('status')
        old=self.checkpoint.load()
        if old:
            self.seen=set(old.get('seen',[])); self.downloaded=set(old.get('downloaded',[])); self.stats.update(old.get('stats',{})); self.domain_bytes=old.get('domain_bytes',{}); self.stats['status']='AWEC Running'
        # A persisted pending queue is restored first; only unseen seeds are then added.
        restored=0
        for item in old.get('pending',[]) if old else []:
            if len(item)==3:
                try:
                    seed=Seed(item[0],CrawlPolicy(**item[1])); await self.queue.put((item[0],seed,item[2])); restored+=1
                except Exception: pass
        for s in self.seeds:
            if s.url not in self.seen: await self.enqueue(s.url,s,0)
        self.stats['queued']=self.queue.qsize()+restored
        workers_count=max(1,min(128,sum(max(1,s.policy.workers) for s in self.seeds)))
        conn=aiohttp.TCPConnector(limit=workers_count,ttl_dns_cache=300)
        async with aiohttp.ClientSession(connector=conn) as session:
            workers=[asyncio.create_task(self.worker(session)) for _ in range(workers_count)]
            try: await self.queue.join()
            finally:
                self.stopped=True
                for w in workers: w.cancel()
                await self.save_checkpoint(); self.stats['status']='AWEC Stopped'; self.emit('status')

    def pause(self): self.paused=True; self.stats['status']='AWEC Paused'; self.checkpoint.save(self.state()); self.emit('status')
    def stop(self): self.stopped=True; self.stats['status']='AWEC Stopped'; self.checkpoint.save(self.state()); self.emit('status')
    def resume(self): self.paused=False; self.stopped=False; self.stats['status']='AWEC Running'; self.emit('status')
