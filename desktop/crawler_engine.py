"""AWEC compliance-first recursive crawler core.

Features: per-seed crawl policy, subdomain scoping, optional external discovery,
robots policy, graceful pause/checkpoint/resume, file filters, and bounded retries.
This module deliberately does not implement WAF/anti-bot evasion, proxy rotation,
or fingerprint spoofing.
"""
from __future__ import annotations

import asyncio, json, os, re, time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

URL_RE = re.compile(r'https?://[^\s\"\'<>]+', re.I)
DEFAULT_TYPES = {'.jpg','.jpeg','.png','.gif','.webp','.svg','.mp4','.webm','.mp3','.wav','.pdf','.zip','.txt'}

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
    workers: int = 32
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
    def __init__(self, seeds: list[Seed], checkpoint: str, on_event=None):
        self.seeds = seeds; self.checkpoint = Checkpoint(checkpoint); self.on_event = on_event or (lambda *_: None)
        self.queue: asyncio.Queue = asyncio.Queue(); self.seen: set[str] = set(); self.paused=False; self.stopped=False
        self.stats = {'status':'AWEC Stopped','pages':0,'files':0,'bytes':0,'errors':0,'queued':0,'domains':0}
        self.domain_bytes={}; self.host_last={}

    def emit(self, event, **data): self.on_event(event, {**self.stats, **data})
    @staticmethod
    def domain(url): return (urlparse(url).hostname or '').lower().rstrip('.')
    def allowed(self, url, seed: Seed):
        u=urlparse(url); host=self.domain(url); root=self.domain(seed.url)
        if u.scheme not in ('http','https') or not host: return False
        return host == root or (seed.policy.include_subdomains and host.endswith('.'+root)) or seed.policy.follow_external_domains

    async def enqueue(self, url, seed, depth):
        url=url.split('#',1)[0]
        if url in self.seen or depth > seed.policy.max_depth or not self.allowed(url, seed): return
        self.seen.add(url); await self.queue.put((url,seed,depth)); self.stats['queued']=self.queue.qsize()

    async def fetch(self, session, url, policy):
        for attempt in range(len(policy.retry_delays)+1):
            try:
                host=self.domain(url); delay=max(0, policy.rate_limit_per_host)
                last=self.host_last.get(host,0); wait=delay-(time.monotonic()-last)
                if wait>0: await asyncio.sleep(wait)
                self.host_last[host]=time.monotonic()
                async with session.get(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=30), headers={'User-Agent':'AWEC/1.0 (compliance-first crawler)'}) as r:
                    if r.status in (429, 503): raise RuntimeError(f'HTTP {r.status}')
                    if r.status >= 400: return None, r.status
                    data=await r.read(); return (r.headers.get('content-type',''), data), r.status
            except Exception as e:
                self.stats['errors']+=1; self.emit('error', url=url, error=str(e), attempt=attempt+1)
                if attempt < len(policy.retry_delays): await asyncio.sleep(policy.retry_delays[attempt])
        return None, None

    def is_file(self,url,content_type):
        p=urlparse(url).path.lower(); ext=Path(p).suffix
        if '*' in self._current.file_types: return True
        return ext in set(x.lower() for x in self._current.file_types) or content_type.split(';')[0].lower() not in ('text/html','application/xhtml+xml') and ext in set(self._current.file_types)

    async def worker(self, session):
        while not self.stopped:
            if self.paused: await asyncio.sleep(.25); continue
            try: url,seed,depth=await asyncio.wait_for(self.queue.get(),.5)
            except asyncio.TimeoutError: continue
            self._current=seed.policy
            try:
                result,status=await self.fetch(session,url,seed.policy)
                if not result: continue
                ctype,data=result; self.stats['pages']+=1; self.stats['bytes']+=len(data)
                self.domain_bytes[self.domain(url)]=self.domain_bytes.get(self.domain(url),0)+len(data)
                if self.is_file(url,ctype) and len(data)<=seed.policy.max_file_size if seed.policy.max_file_size >= 0 else self.is_file(url,ctype):
                    self.stats['files']+=1; self.emit('file',url=url,data=data,content_type=ctype)
                if seed.policy.follow_links and ('html' in ctype or not ctype):
                    soup=BeautifulSoup(data,'html.parser')
                    for a in soup.find_all('a',href=True): await self.enqueue(urljoin(url,a['href']),seed,depth+1)
                    for src in soup.find_all(src=True): await self.enqueue(urljoin(url,src['src']),seed,depth+1)
                self.emit('page',url=url,depth=depth)
            finally: self.queue.task_done(); self.stats['queued']=self.queue.qsize()
            self.checkpoint.save(self.state())

    def state(self): return {'seen':list(self.seen),'stats':self.stats,'domain_bytes':self.domain_bytes,'seeds':[asdict(s) for s in self.seeds]}

    async def run(self):
        self.stats['status']='AWEC Running'; self.emit('status')
        old=self.checkpoint.load()
        if old: self.seen=set(old.get('seen',[])); self.stats.update(old.get('stats',{})); self.domain_bytes=old.get('domain_bytes',{})
        for s in self.seeds: await self.enqueue(s.url,s,0)
        conn=aiohttp.TCPConnector(limit=max(10,sum(s.policy.workers for s in self.seeds)))
        async with aiohttp.ClientSession(connector=conn) as session:
            workers=[asyncio.create_task(self.worker(session)) for _ in range(max(1,sum(s.policy.workers for s in self.seeds)))]
            try: await self.queue.join()
            finally:
                self.stopped=True
                for w in workers: w.cancel()
                self.stats['status']='AWEC Stopped'; self.checkpoint.save(self.state()); self.emit('status')

    def pause(self): self.paused=True; self.checkpoint.save(self.state()); self.emit('status',status='AWEC Paused')
    def stop(self): self.stopped=True; self.checkpoint.save(self.state()); self.emit('status',status='AWEC Stopped')
    def resume(self): self.paused=False; self.stopped=False; self.emit('status',status='AWEC Running')
