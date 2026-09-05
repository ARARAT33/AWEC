"""AWEC desktop engine bridge with portable storage and conservative resource usage."""
from __future__ import annotations
import asyncio, json, threading, re
from pathlib import Path
from urllib.parse import urlparse
from PySide6.QtCore import QObject, Signal
from desktop.crawler_engine import CrawlPolicy
from desktop.crawler_engine_v12 import ResumableAWECrawler
from awec.archive.ia import IAUploader
from storage_layout import ensure_layout, app_root

class Engine(QObject):
    log=Signal(str); stats=Signal(dict); finished=Signal(str)
    def __init__(self,cfg): super().__init__(); self.cfg=cfg; self.is_paused=False; self.stop_event=threading.Event(); self._crawler=None
    def _policy(self):
        depth=getattr(self.cfg,'max_depth',0); depth=100000 if depth<=0 else depth
        try: headers=json.loads(getattr(self.cfg,'custom_headers_json','{}') or '{}'); headers=headers if isinstance(headers,dict) else {}
        except Exception: headers={}
        workers=min(8,max(1,int(getattr(self.cfg,'workers',8)))); delay=max(0.,float(getattr(self.cfg,'per_host_delay',.15))); rate=1./delay if delay else 1000.
        return CrawlPolicy(network_mode=getattr(self.cfg,'network_mode','standard'),follow_links=getattr(self.cfg,'follow_links',True),follow_external_domains=getattr(self.cfg,'follow_external_domains',False),include_subdomains=True,download_files=True,respect_robots=getattr(self.cfg,'respect_robots',True),max_depth=depth,max_file_size=getattr(self.cfg,'max_file_size',-1),file_types=['*'],workers=workers,rate_limit_per_host=rate,retry_delays=[2,5,15,30],ua_rotation=getattr(self.cfg,'ua_rotation_enabled',True),delay_jitter=max(0.,getattr(self.cfg,'delay_jitter_sec',.25)),auto_headers=getattr(self.cfg,'auto_headers_enabled',True),verify_ssl=getattr(self.cfg,'verify_ssl',True),proxy_url=getattr(self.cfg,'proxy_url',''),custom_headers=headers,max_local_mb=0,purge_after_upload=getattr(self.cfg,'purge_local_files_after_upload',False),mirror_all_resources=True,fanti_user_agent_profile=getattr(self.cfg,'fanti_user_agent_profile','archive'),fanti_custom_user_agent=getattr(self.cfg,'custom_user_agent',''),fanti_header_profile=getattr(self.cfg,'fanti_header_profile','Default Archive'),fanti_min_delay=getattr(self.cfg,'fanti_min_delay',.05),fanti_max_delay=getattr(self.cfg,'fanti_max_delay',8.),fanti_initial_delay=getattr(self.cfg,'fanti_initial_delay',.15),fanti_adaptive_pacing=getattr(self.cfg,'fanti_adaptive_pacing',True),fanti_min_concurrency=getattr(self.cfg,'fanti_min_concurrency',1),fanti_max_concurrency=min(8,max(1,int(getattr(self.cfg,'fanti_max_concurrency',8)))),fanti_initial_concurrency=min(4,max(1,int(getattr(self.cfg,'fanti_initial_concurrency',4)))),fanti_adaptive_concurrency=getattr(self.cfg,'fanti_adaptive_concurrency',True),fanti_max_retries=getattr(self.cfg,'fanti_max_retries',5),fanti_backoff_strategy=getattr(self.cfg,'fanti_backoff_strategy','full_jitter'),fanti_base_retry_delay=getattr(self.cfg,'fanti_base_retry_delay',1.),fanti_max_retry_delay=getattr(self.cfg,'fanti_max_retry_delay',60.),fanti_circuit_breaker_enabled=getattr(self.cfg,'fanti_circuit_breaker_enabled',True),fanti_circuit_breaker_threshold=getattr(self.cfg,'fanti_circuit_breaker_threshold',5),fanti_circuit_breaker_cooldown=getattr(self.cfg,'fanti_circuit_breaker_cooldown',30.),fanti_max_connections=min(32,max(8,int(getattr(self.cfg,'fanti_max_connections',32)))),fanti_max_connections_per_host=min(8,max(2,int(getattr(self.cfg,'fanti_max_connections_per_host',8)))),fanti_keepalive_timeout=getattr(self.cfg,'fanti_keepalive_timeout',30.),fanti_dns_timeout=getattr(self.cfg,'fanti_dns_timeout',10.),fanti_connect_timeout=getattr(self.cfg,'fanti_connect_timeout',10.),fanti_read_timeout=getattr(self.cfg,'fanti_read_timeout',30.),fanti_total_timeout=getattr(self.cfg,'fanti_total_timeout',60.),fanti_max_redirects=getattr(self.cfg,'fanti_max_redirects',10),fanti_allow_cross_domain_redirects=getattr(self.cfg,'fanti_allow_cross_domain_redirects',True),fanti_cookie_policy=getattr(self.cfg,'fanti_cookie_policy','per-job'),fanti_bandwidth_limit_bytes_per_sec=getattr(self.cfg,'fanti_bandwidth_limit_bytes_per_sec',0),fanti_enable_browser_rendering=False,fanti_browser_timeout=getattr(self.cfg,'fanti_browser_timeout',30.),fanti_diagnostic_mode=getattr(self.cfg,'fanti_diagnostic_mode',False))
    def _event(self,name,payload):
        if name=='crawl_started': self.log.emit('🚀 AWEC • lightweight crawler started')
        elif name=='crawl_resumed': self.log.emit(f"♻️ RESUME • {payload.get('crawl_id')} restored")
        elif name=='discovery': self.log.emit(f"🔎 DISCOVERY • +{payload.get('found',0)} found • queued={payload.get('queued',0):,} • rejected={payload.get('rejected',0):,}")
        elif name=='page_fetched': self.log.emit(f"⬇️ [{payload.get('status')}] {payload.get('url')} → {payload.get('local_path')} ({payload.get('size',0):,} bytes)")
        elif name=='request_failed': self.log.emit(f"⚠️ FETCH FAILED • [{payload.get('status')}] {payload.get('url')}")
        elif name=='archive_uploaded': self.log.emit(f"☁️ IA VERIFIED • {payload.get('remote_key')}")
        elif name=='archive_upload_failed': self.log.emit(f"⚠️ IA upload failed • {payload.get('url')}: {payload.get('message')}")
        elif name=='storage_guard': self.log.emit(f"🛡️ STORAGE GUARD • {payload.get('message')}")
        elif name=='crawl_finished': self.log.emit(f"🏁 Finished • {payload.get('mirrored',0):,} resources • discovered={payload.get('discovered',0):,} • IA {payload.get('uploaded',0):,} • errors {payload.get('errors',0):,}")
        elif name=='crawler_error': self.log.emit(f"💥 {payload.get('message')}")
    def _archive(self):
        if not getattr(self.cfg,'destination_archive',True) or not getattr(self.cfg,'ia_access_key','') or not getattr(self.cfg,'ia_secret_key','') or not getattr(self.cfg,'ia_identifier',''): return None
        raw_identifier=str(self.cfg.ia_identifier).strip()
        identifier=re.sub(r"[^A-Za-z0-9_.-]+","-",raw_identifier).strip("-")[:100]
        if identifier != raw_identifier:
            self.log.emit(f"ℹ️ IA identifier normalized: {raw_identifier} → {identifier}")
        collection=(getattr(self.cfg,'ia_collection','') or __import__('os').environ.get('AWEC_IA_COLLECTION','')).strip()
        uploader=IAUploader(self.cfg.ia_access_key,self.cfg.ia_secret_key,identifier,getattr(self.cfg,'ia_endpoint','https://s3.us.archive.org'),collection=collection,title=getattr(self.cfg,'ia_title','') or raw_identifier,creator=getattr(self.cfg,'ia_creator',''),description=getattr(self.cfg,'ia_description',''))
        # Keep the collection on the uploader even when the item already exists.
        # upload_file_s3() validates the destination before every PUT, so clearing
        # it here makes existing items fail with COLLECTION_NAME_REQUIRED.
        uploader.check_item()
        return uploader
    async def _run(self):
        seeds=list(getattr(self.cfg,'seeds',[]) or [])
        if not seeds: self.log.emit('❌ No seed URL configured'); return
        paths=ensure_layout(Path(getattr(self.cfg,'storage_root','') or app_root())); root=Path(getattr(self.cfg,'fallback_dir','') or paths['fallback']); root.mkdir(parents=True,exist_ok=True); resume_dir=getattr(self.cfg,'resume_dir','') or None; uploader=self._archive()
        # robots.txt and sitemap.xml are optional discovery resources, not seeds.
        # A site returning 404 for either must not create crawler errors/retries.
        self._crawler=ResumableAWECrawler(seeds,self._policy(),on_event=self._event,output_dir=root,resume_dir=resume_dir,ia_uploader=uploader,archive_verify=True,purge_after_upload=getattr(self.cfg,'purge_local_files_after_upload',False),min_free_space_mb=max(256,int(getattr(self.cfg,'min_free_space_gb',1.)*1024)),max_local_mb=max(1,int(getattr(self.cfg,'max_storage_gb',10.)*1024)),keep_local_mirror=getattr(self.cfg,'keep_local_mirror',True))
        async def _no_bootstrap():
            return None
        self._crawler._seed_bootstrap=_no_bootstrap
        self.log.emit(f'🌐 Seeds: {", ".join(seeds)}'); self.log.emit(f'🕸️ Concurrency: {self._policy().workers} workers'); self.log.emit(f'📦 AWEC storage: {paths["root"]} • quota={getattr(self.cfg,"max_storage_gb",10):g} GB • reserve={getattr(self.cfg,"min_free_space_gb",1):g} GB'); self.log.emit(f'🗂️ Data: {root} • persistent: {paths["config"]}, {paths["ia"]}')
        if uploader:self.log.emit('☁️ Internet Archive LIVE upload + verification enabled')
        await self._crawler.run(); s=self._crawler.stats; self.stats.emit({'queued':s.get('queued',0),'enqueued':s.get('enqueued',0),'fetched':s.get('pages',0)+s.get('files',0),'pages':s.get('pages',0),'found':s.get('files',0),'files':s.get('files',0),'downloaded':s.get('mirrored',0),'uploaded':s.get('uploaded',0),'mirrored':s.get('mirrored',0),'mirror_bytes':s.get('mirror_bytes',0),'errors':s.get('errors',0),'active':0,'speed':s.get('status','Completed'),'active_domain':s.get('active_domain',seeds[0])})
    def start(self):
        try:self.log.emit('▶ Starting AWEC crawler'); asyncio.run(self._run())
        except Exception as exc:self.log.emit(f'💥 Fatal crawler error: {type(exc).__name__}: {exc}')
        finally:self.finished.emit(json.dumps({'status':'stopped' if self.stop_event.is_set() else 'completed'}))
    def stop(self): self.stop_event.set(); self._crawler and setattr(self._crawler,'stopped',True)
    def pause(self): self.is_paused=True; self._crawler and setattr(self._crawler,'paused',True)
    def resume(self): self.is_paused=False; self._crawler and setattr(self._crawler,'paused',False)
