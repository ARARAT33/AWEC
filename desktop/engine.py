"""AWEC desktop engine bridge for the v12 command center."""
from __future__ import annotations
import asyncio, json, threading
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from desktop.crawler_engine import CrawlPolicy
from desktop.crawler_engine_v12 import ResumableAWECrawler
from awec.archive.ia import IAUploader

class Engine(QObject):
    log = Signal(str); stats = Signal(dict); finished = Signal(str)
    def __init__(self, cfg):
        super().__init__(); self.cfg=cfg; self.is_paused=False; self.stop_event=threading.Event(); self._crawler=None

    def _policy(self):
        return CrawlPolicy(
            network_mode=getattr(self.cfg,'network_mode','standard'), follow_links=True,
            follow_external_domains=not getattr(self.cfg,'same_domain_only',True), include_subdomains=True,
            download_files=True, respect_robots=getattr(self.cfg,'respect_robots',True),
            max_depth=getattr(self.cfg,'max_depth',8), max_file_size=getattr(self.cfg,'max_file_size',-1),
            file_types=getattr(self.cfg,'file_types',['*']) or ['*'], workers=max(1,getattr(self.cfg,'workers',32)),
            rate_limit_per_host=max(0.0,getattr(self.cfg,'per_host_delay',0.15)), retry_delays=[2,5,15,30],
            ua_rotation=getattr(self.cfg,'ua_rotation_enabled',True), delay_jitter=max(0.0,getattr(self.cfg,'delay_jitter_sec',0.25)),
            auto_headers=getattr(self.cfg,'auto_headers_enabled',True), verify_ssl=getattr(self.cfg,'verify_ssl',True),
            proxy_url=getattr(self.cfg,'proxy_url',''), custom_headers={},
            max_local_mb=getattr(self.cfg,'max_local_storage_mb',0), purge_after_upload=getattr(self.cfg,'purge_local_files_after_upload',True),
            mirror_all_resources=True)

    def _event(self,name,payload):
        if name=='crawl_started': self.log.emit('🚀 AWEC v12 • crawl started — recursive reachable-resource mirror + live archive publishing')
        elif name=='crawl_resumed': self.log.emit(f"♻️ RESUME • restored session {payload.get('crawl_id')} from {payload.get('path')}")
        elif name=='page_fetched': self.log.emit(f"⬇️ [{payload.get('status')}] {payload.get('url')} → {payload.get('local_path')} ({payload.get('size',0):,} bytes)")
        elif name=='archive_uploaded': self.log.emit(f"☁️ IA VERIFIED • {payload.get('remote_key')} ({payload.get('size',0):,} bytes)")
        elif name=='archive_upload_failed': self.log.emit(f"⚠️ IA upload failed • {payload.get('url')}: {payload.get('message')}")
        elif name=='storage_guard': self.log.emit(f"🛡️ STORAGE GUARD • {payload.get('message')}")
        elif name=='crawl_finished': self.log.emit(f"🏁 Crawl finished • mirrored={payload.get('mirrored',0):,} • uploaded={payload.get('uploaded',0):,} • errors={payload.get('errors',0):,}")
        elif name=='crawler_error': self.log.emit(f"💥 {payload.get('message')}")

    def _archive(self):
        if not getattr(self.cfg,'archive_upload_live',True): return None
        if not getattr(self.cfg,'ia_access_key','') or not getattr(self.cfg,'ia_secret_key','') or not getattr(self.cfg,'ia_identifier',''): return None
        return IAUploader(getattr(self.cfg,'ia_access_key',''),getattr(self.cfg,'ia_secret_key',''),getattr(self.cfg,'ia_identifier',''),getattr(self.cfg,'ia_endpoint','https://s3.us.archive.org'),collection=getattr(self.cfg,'ia_collection',''),title=getattr(self.cfg,'ia_title',''),creator=getattr(self.cfg,'ia_creator',''),description=getattr(self.cfg,'ia_description',''))

    async def _run(self):
        seeds=list(getattr(self.cfg,'seeds',[]) or [])
        if not seeds: self.log.emit('❌ No seed URL configured'); return
        tmp=getattr(self.cfg,'tmpcrawl_dir','') or getattr(self.cfg,'fallback_dir','') or str(Path.home()/'AWEC'/'tmpcrawl')
        root=Path(tmp); root.mkdir(parents=True,exist_ok=True)
        resume_dir=getattr(self.cfg,'resume_dir','') or None
        uploader=self._archive()
        self._crawler=ResumableAWECrawler(seeds,self._policy(),on_event=self._event,output_dir=root,resume_dir=resume_dir,ia_uploader=uploader,archive_verify=getattr(self.cfg,'archive_verify_uploads',True),purge_after_upload=getattr(self.cfg,'purge_local_files_after_upload',True),min_free_space_mb=getattr(self.cfg,'min_free_space_mb',2048),max_local_mb=getattr(self.cfg,'max_local_storage_mb',0),keep_local_mirror=getattr(self.cfg,'keep_local_mirror',True))
        self.log.emit(f'🌐 Seeds: {", ".join(seeds)}')
        self.log.emit(f'📦 tmpcrawl: {root} • limit={getattr(self.cfg,"max_local_storage_mb",0) or "UNLIMITED"} MB • reserve={getattr(self.cfg,"min_free_space_mb",2048)} MB')
        self.log.emit('🔎 Resource mode: ALL reachable HTML/CSS/JS/media/files')
        if uploader: self.log.emit('☁️ Internet Archive: LIVE upload + optional verification enabled')
        await self._crawler.run(); s=self._crawler.stats
        self.stats.emit({'queued':s.get('queued',0),'enqueued':s.get('enqueued',0),'fetched':s.get('pages',0)+s.get('files',0),'pages':s.get('pages',0),'found':s.get('files',0),'files':s.get('files',0),'downloaded':s.get('mirrored',0),'uploaded':s.get('uploaded',0),'mirrored':s.get('mirrored',0),'mirror_bytes':s.get('mirror_bytes',0),'errors':s.get('errors',0),'active':0,'speed':s.get('status','Completed'),'active_domain':s.get('active_domain',seeds[0])})

    def start(self):
        try: self.log.emit('▶ Starting AWEC v12 crawler engine NOW'); asyncio.run(self._run())
        except Exception as exc: self.log.emit(f'💥 Fatal crawler error: {type(exc).__name__}: {exc}')
        finally: self.finished.emit(json.dumps({'status':'stopped' if self.stop_event.is_set() else 'completed'}))
    def stop(self): self.stop_event.set(); self._crawler and self._crawler.stop()
    def pause(self): self.is_paused=True; self._crawler and self._crawler.pause()
    def resume(self): self.is_paused=False; self._crawler and self._crawler.resume()
