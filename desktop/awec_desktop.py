#!/usr/bin/env python3
"""AWEC Desktop: configurable recursive web crawler + Internet Archive dataset uploader."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
import boto3
import requests
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QDoubleSpinBox, QTabWidget, QVBoxLayout, QWidget
)

URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.I)
HREF_RE = re.compile(r"(?:href|src)\s*=\s*['\"]([^'\"]+)['\"]", re.I)

@dataclass
class Config:
    collection: str = ""
    identifier: str = "awec"
    creator: str = ""
    title: str = "AWEC Web Crawl"
    description: str = "AWEC recursive web URL index"
    subject: str = "web;urls;archive"
    access_key: str = ""
    secret_key: str = ""
    endpoint: str = "https://s3.us.archive.org"
    seeds: list[str] = None
    workers: int = 64
    max_depth: int = 8
    max_urls: int = 0
    per_host_delay: float = 0.25
    timeout: int = 15
    chunk_size: int = 10000
    upload_every: int = 10000
    respect_robots: bool = True
    same_domain_only: bool = False
    capture_html: bool = False
    upload_html: bool = False

    def __post_init__(self):
        if self.seeds is None:
            self.seeds = []

class Signals(QObject):
    log = Signal(str)
    stats = Signal(int, int, int, int, str)
    finished = Signal(str)
    failed = Signal(str)

class Crawler:
    def __init__(self, cfg: Config, signals: Signals, workdir: Path):
        self.cfg = cfg
        self.s = signals
        self.workdir = workdir
        self.db_path = workdir / "awec.db"
        self.out = workdir / "dataset"
        self.html = workdir / "html"
        self.out.mkdir(parents=True, exist_ok=True)
        if cfg.capture_html:
            self.html.mkdir(parents=True, exist_ok=True)
        self.stop_event = asyncio.Event()
        self.queue: asyncio.Queue[tuple[str, int, str]] = asyncio.Queue(maxsize=max(1000, cfg.workers * 50))
        self.seen: set[str] = set()
        self.enqueued = 0
        self.found = 0
        self.saved = 0
        self.failed = 0
        self.active = 0
        self.chunk: list[dict] = []
        self.chunk_no = 0
        self.host_locks: dict[str, asyncio.Lock] = {}
        self.last_request: dict[str, float] = {}
        self.robots: dict[str, RobotFileParser | None] = {}
        self.session: aiohttp.ClientSession | None = None
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA busy_timeout=30000")
        self.db.execute("CREATE TABLE IF NOT EXISTS urls(url TEXT PRIMARY KEY, depth INTEGER, source TEXT, status INTEGER, content_type TEXT, fetched_at TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, started TEXT, stopped TEXT, saved INTEGER, found INTEGER)")
        self.db.commit()
        self.db_lock = threading.Lock()

    def log(self, text: str):
        self.s.log.emit(text)

    def db_has(self, url: str) -> bool:
        with self.db_lock:
            return self.db.execute("SELECT 1 FROM urls WHERE url=? LIMIT 1", (url,)).fetchone() is not None

    def save_url(self, item: dict):
        with self.db_lock:
            self.db.execute("INSERT OR IGNORE INTO urls VALUES (?,?,?,?,?,?)", (
                item["url"], item["depth"], item["source"], item["status"], item["content_type"], item["fetched_at"]))
            self.db.commit()

    async def allowed(self, url: str) -> bool:
        if not self.cfg.respect_robots:
            return True
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self.robots:
            rp = RobotFileParser()
            rp.set_url(origin + "/robots.txt")
            try:
                async with self.session.get(origin + "/robots.txt", timeout=8) as r:
                    if r.status == 200:
                        rp.parse((await r.text(errors="ignore")).splitlines())
                    else:
                        self.robots[origin] = None
                        return True
                self.robots[origin] = rp
            except Exception:
                self.robots[origin] = None
                return True
        rp = self.robots[origin]
        return True if rp is None else rp.can_fetch("AWEC", url)

    async def throttle(self, host: str):
        lock = self.host_locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            wait = self.cfg.per_host_delay - (now - self.last_request.get(host, 0))
            if wait > 0:
                await asyncio.sleep(wait)
            self.last_request[host] = time.monotonic()

    def normalize(self, base: str, value: str) -> str | None:
        value = value.strip()
        if not value or value.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            return None
        u = urldefrag(urljoin(base, value))[0]
        p = urlparse(u)
        if p.scheme not in ("http", "https") or not p.netloc:
            return None
        return u[:2000]

    async def enqueue(self, url: str, depth: int, source: str):
        if depth > self.cfg.max_depth or url in self.seen:
            return
        if self.cfg.max_urls and self.enqueued >= self.cfg.max_urls:
            return
        if self.cfg.same_domain_only and self.cfg.seeds:
            seed_hosts = {urlparse(x).netloc.lower() for x in self.cfg.seeds}
            if urlparse(url).netloc.lower() not in seed_hosts:
                return
        self.seen.add(url)
        self.enqueued += 1
        await self.queue.put((url, depth, source))

    async def fetch(self, url: str, depth: int, source: str):
        p = urlparse(url)
        await self.throttle(p.netloc.lower())
        if not await self.allowed(url):
            self.failed += 1
            return
        self.active += 1
        try:
            async with self.session.get(url, allow_redirects=True, max_redirects=8) as r:
                ctype = r.headers.get("content-type", "")[:200]
                body = await r.read()
                now = datetime.now(timezone.utc).isoformat()
                item = {"url": str(r.url), "depth": depth, "source": source, "status": r.status,
                        "content_type": ctype, "bytes": len(body), "fetched_at": now}
                self.found += 1
                self.save_url(item)
                self.chunk.append(item)
                self.saved += 1
                if self.cfg.capture_html and "text/html" in ctype:
                    digest = hashlib.sha256(str(r.url).encode()).hexdigest()
                    (self.html / f"{digest}.html").write_bytes(body)
                if "text/html" in ctype and depth < self.cfg.max_depth:
                    text = body.decode(r.charset or "utf-8", errors="ignore")
                    links = []
                    for raw in HREF_RE.findall(text):
                        u = self.normalize(str(r.url), raw)
                        if u:
                            links.append(u)
                    for u in URL_RE.findall(text):
                        n = self.normalize(str(r.url), u)
                        if n:
                            links.append(n)
                    for u in dict.fromkeys(links):
                        await self.enqueue(u, depth + 1, str(r.url))
                if len(self.chunk) >= self.cfg.chunk_size:
                    await self.flush_chunk()
        except Exception as e:
            self.failed += 1
            self.log(f"⚠️ {url} — {type(e).__name__}: {e}")
        finally:
            self.active -= 1
            self.s.stats.emit(self.enqueued, self.found, self.saved, self.failed, str(self.queue.qsize()))

    async def worker(self):
        while not self.stop_event.is_set():
            try:
                url, depth, source = await asyncio.wait_for(self.queue.get(), timeout=1)
            except asyncio.TimeoutError:
                if self.active == 0 and self.queue.empty():
                    return
                continue
            try:
                await self.fetch(url, depth, source)
            finally:
                self.queue.task_done()

    async def flush_chunk(self):
        if not self.chunk:
            return
        self.chunk_no += 1
        path = self.out / f"urls_{self.chunk_no:06d}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for row in self.chunk:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.log(f"📦 Created {path.name} ({len(self.chunk):,} records)")
        if self.cfg.access_key and self.cfg.secret_key and self.cfg.identifier:
            await asyncio.to_thread(self.upload_file, path)
        self.chunk.clear()

    def upload_file(self, path: Path):
        s3 = boto3.client("s3", endpoint_url=self.cfg.endpoint, aws_access_key_id=self.cfg.access_key,
                          aws_secret_access_key=self.cfg.secret_key, region_name="us-east-1")
        key = f"data/{path.name}"
        s3.upload_file(str(path), self.cfg.identifier, key, ExtraArgs={"ContentType": "application/x-ndjson"})
        self.log(f"☁️ IA upload complete: {key}")

    def finalize_metadata(self):
        if not (self.cfg.access_key and self.cfg.secret_key and self.cfg.identifier):
            return
        metadata = {
            "title": self.cfg.title, "creator": self.cfg.creator, "description": self.cfg.description,
            "subject": self.cfg.subject, "collection": self.cfg.collection
        }
        metadata = {k: v for k, v in metadata.items() if v}
        try:
            r = requests.post(f"https://archive.org/metadata/{self.cfg.identifier}", data={"metadata": json.dumps(metadata)}, timeout=30)
            if r.ok:
                self.log("🏛️ Internet Archive metadata updated")
            else:
                self.log(f"⚠️ IA metadata HTTP {r.status_code}: {r.text[:300]}")
        except Exception as e:
            self.log(f"⚠️ IA metadata error: {e}")

    async def run(self):
        started = datetime.now(timezone.utc).isoformat()
        self.log(f"🚀 AWEC started — {len(self.cfg.seeds)} seed(s), {self.cfg.workers} workers")
        self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=self.cfg.workers * 2, ssl=False),
                                             timeout=aiohttp.ClientTimeout(total=self.cfg.timeout),
                                             headers={"User-Agent": "AWEC/2.0 (+https://github.com/ARARAT33/AWEC)"})
        try:
            for seed in self.cfg.seeds:
                u = self.normalize(seed, seed)
                if u:
                    await self.enqueue(u, 0, "seed")
            tasks = [asyncio.create_task(self.worker()) for _ in range(self.cfg.workers)]
            await self.queue.join()
            self.stop_event.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.flush_chunk()
            self.finalize_metadata()
            with self.db_lock:
                self.db.execute("INSERT INTO runs(started,stopped,saved,found) VALUES(?,?,?,?,?)".replace("VALUES(?,?,?,?,?)", "VALUES(?,?,?,?)"),
                                (started, datetime.now(timezone.utc).isoformat(), self.saved, self.found))
                self.db.commit()
            self.s.finished.emit(f"Done — {self.saved:,} records, {self.failed:,} failures")
        except Exception as e:
            self.s.failed.emit(f"Fatal: {type(e).__name__}: {e}")
        finally:
            if self.session:
                await self.session.close()
            self.db.close()

    def stop(self):
        self.stop_event.set()

class Runner(QObject):
    log = Signal(str); stats = Signal(int,int,int,int,str); finished = Signal(str); failed = Signal(str)
    def __init__(self, cfg: Config, workdir: Path):
        super().__init__(); self.cfg=cfg; self.workdir=workdir; self.crawler=None
    def start(self):
        self.crawler=Crawler(self.cfg, self, self.workdir)
        self.crawler.s.log.connect(self.log); self.crawler.s.stats.connect(self.stats)
        self.crawler.s.finished.connect(self.finished); self.crawler.s.failed.connect(self.failed)
        asyncio.run(self.crawler.run())
    def stop(self):
        if self.crawler: self.crawler.stop()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("AWEC Desktop — Web Crawler + Internet Archive"); self.resize(1100,760)
        self.workdir=Path.home()/"AWEC"; self.workdir.mkdir(exist_ok=True)
        tabs=QTabWidget(); tabs.addTab(self.build_config(), "⚙ Configuration"); tabs.addTab(self.build_seeds(), "🌐 Sites"); tabs.addTab(self.build_monitor(), "📊 Monitor"); self.setCentralWidget(tabs)
        self.thread=None; self.runner=None

    def build_config(self):
        w=QWidget(); form=QFormLayout(w)
        self.collection=QLineEdit(); self.identifier=QLineEdit("awec-crawl"); self.creator=QLineEdit(); self.title=QLineEdit("AWEC Web Crawl"); self.description=QLineEdit("AWEC recursive web URL index"); self.subject=QLineEdit("web;urls;archive")
        self.access=QLineEdit(); self.access.setEchoMode(QLineEdit.Password); self.secret=QLineEdit(); self.secret.setEchoMode(QLineEdit.Password); self.endpoint=QLineEdit("https://s3.us.archive.org")
        form.addRow("IA collection",self.collection); form.addRow("IA identifier",self.identifier); form.addRow("Creator",self.creator); form.addRow("Title",self.title); form.addRow("Description",self.description); form.addRow("Subject",self.subject); form.addRow("S3 access key",self.access); form.addRow("S3 secret key",self.secret); form.addRow("S3 endpoint",self.endpoint)
        self.workers=QSpinBox(); self.workers.setRange(1,512); self.workers.setValue(64); form.addRow("Workers",self.workers)
        self.depth=QSpinBox(); self.depth.setRange(0,100); self.depth.setValue(8); form.addRow("Max depth",self.depth)
        self.maxurls=QSpinBox(); self.maxurls.setRange(0,1000000000); self.maxurls.setValue(0); form.addRow("Max URLs (0=unlimited)",self.maxurls)
        self.delay=QDoubleSpinBox(); self.delay.setRange(0,60); self.delay.setDecimals(3); self.delay.setValue(.25); form.addRow("Per-host delay (sec)",self.delay)
        self.timeout=QSpinBox(); self.timeout.setRange(2,300); self.timeout.setValue(15); form.addRow("Timeout (sec)",self.timeout)
        self.chunk=QSpinBox(); self.chunk.setRange(100,1000000); self.chunk.setValue(10000); form.addRow("Records per file",self.chunk)
        self.robots=QCheckBox("Respect robots.txt"); self.robots.setChecked(True); form.addRow(self.robots)
        self.same=QCheckBox("Stay on seed domains only"); form.addRow(self.same)
        self.capture=QCheckBox("Capture HTML snapshots (opt-in)"); form.addRow(self.capture)
        return w

    def build_seeds(self):
        w=QWidget(); lay=QVBoxLayout(w); self.seedlist=QListWidget(); lay.addWidget(self.seedlist)
        row=QHBoxLayout(); self.seed=QLineEdit(); self.seed.setPlaceholderText("https://example.com"); add=QPushButton("Add"); rem=QPushButton("Remove selected"); add.clicked.connect(lambda:self.seedlist.addItem(self.seed.text().strip()) if self.seed.text().strip() else None); rem.clicked.connect(lambda:self.seedlist.takeItem(self.seedlist.currentRow()) if self.seedlist.currentRow()>=0 else None); row.addWidget(self.seed); row.addWidget(add); row.addWidget(rem); lay.addLayout(row)
        return w

    def build_monitor(self):
        w=QWidget(); lay=QVBoxLayout(w); self.status=QLabel("Ready"); lay.addWidget(self.status); self.logbox=QPlainTextEdit(); self.logbox.setReadOnly(True); lay.addWidget(self.logbox)
        row=QHBoxLayout(); start=QPushButton("▶ Start crawl"); stop=QPushButton("■ Stop"); start.clicked.connect(self.start); stop.clicked.connect(self.stop); row.addWidget(start); row.addWidget(stop); lay.addLayout(row); return w

    def cfg(self):
        seeds=[self.seedlist.item(i).text() for i in range(self.seedlist.count())]
        return Config(collection=self.collection.text().strip(),identifier=self.identifier.text().strip(),creator=self.creator.text().strip(),title=self.title.text(),description=self.description.text(),subject=self.subject.text(),access_key=self.access.text(),secret_key=self.secret.text(),endpoint=self.endpoint.text().strip(),seeds=seeds,workers=self.workers.value(),max_depth=self.depth.value(),max_urls=self.maxurls.value(),per_host_delay=self.delay.value(),timeout=self.timeout.value(),chunk_size=self.chunk.value(),respect_robots=self.robots.isChecked(),same_domain_only=self.same.isChecked(),capture_html=self.capture.isChecked())

    def start(self):
        cfg=self.cfg()
        if not cfg.seeds: QMessageBox.warning(self,"AWEC","Ավելացրու առնվազն մեկ կայք։"); return
        if not cfg.identifier: QMessageBox.warning(self,"AWEC","IA identifier-ը պարտադիր է։"); return
        self.logbox.appendPlainText("=== START ===")
        self.thread=QThread(); self.runner=Runner(cfg,self.workdir); self.runner.moveToThread(self.thread); self.thread.started.connect(self.runner.start); self.runner.log.connect(self.logbox.appendPlainText); self.runner.stats.connect(lambda a,b,c,d,q:self.status.setText(f"Queued {a:,} | Fetched {b:,} | Saved {c:,} | Failed {d:,} | Queue {q}")); self.runner.finished.connect(lambda x:self.status.setText(x)); self.runner.failed.connect(lambda x:self.status.setText(x)); self.runner.finished.connect(self.thread.quit); self.runner.failed.connect(self.thread.quit); self.thread.start()

    def stop(self):
        if self.runner: self.runner.stop(); self.status.setText("Stopping…")

def main():
    app=QApplication([]); win=MainWindow(); win.show(); app.exec()
if __name__=="__main__": main()
