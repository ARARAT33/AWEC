#!/usr/bin/env python3
import asyncio
import aiohttp
import hashlib
import logging
import os
import sys
import time
import sqlite3
import shutil
import warnings
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, urldefrag
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
class Config:
    db_path = "links.db"
    log_file = "logs/crawler.log"
    max_workers = 120
    max_queue_size = 150_000
    request_timeout = 7
    flush_interval = 60.0  # 1 րոպեն մեկ flush
    
    # Internet Archive Credentials (GitHub Secrets)
    ia_access_key = os.environ.get("IA_ACCESS_KEY")
    ia_secret_key = os.environ.get("IA_SECRET_KEY")
    ia_identifier = "awec_links_awe_o.s"  # Քո կոնկրետ էջը

# ---------------------------------------------------------------------------
# LOGGER SETUP
# ---------------------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("awec")
logger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

fh = logging.FileHandler(Config.log_file)
fh.setFormatter(fmt)
logger.addHandler(fh)

sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(fmt)
logger.addHandler(sh)

# ---------------------------------------------------------------------------
# DATABASE (Thread-Safe SQLite)
# ---------------------------------------------------------------------------
class Database:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.conn = None
        self._db_lock = asyncio.Lock()
        self._buffer = []
        self._buf_lock = asyncio.Lock()
        self.connect()

    def connect(self):
        self.conn = sqlite3.connect(self.cfg.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA busy_timeout=15000")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS urls (
                url TEXT PRIMARY KEY,
                status TEXT DEFAULT 'pending',
                source TEXT DEFAULT 'unknown'
            )
        """)
        self.conn.commit()

    async def insert_many(self, urls: list, source: str = 'crawled'):
        async with self._buf_lock:
            for u in urls:
                self._buffer.append((u, source))

    async def flush(self):
        async with self._buf_lock:
            if not self._buffer:
                return
            to_write = list(self._buffer)
            self._buffer.clear()

        async with self._db_lock:
            await asyncio.to_thread(self._sync_write, to_write)

    def _sync_write(self, data):
        for url, src in data:
            try:
                self.conn.execute(
                    "INSERT OR IGNORE INTO urls (url, status, source) VALUES (?, 'pending', ?)",
                    (url, src)
                )
            except Exception:
                pass
        self.conn.commit()

    async def get_pending(self, limit=3000) -> list:
        async with self._db_lock:
            return await asyncio.to_thread(self._sync_get_pending, limit)

    def _sync_get_pending(self, limit):
        rows = self.conn.execute(
            "SELECT url FROM urls WHERE status='pending' LIMIT ?", (limit,)
        ).fetchall()
        for (url,) in rows:
            self.conn.execute("UPDATE urls SET status='visited' WHERE url=?", (url,))
        self.conn.commit()
        return [r[0] for r in rows]

    def total_count(self) -> int:
        try:
            return self.conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
        except Exception:
            return 0

    def close(self):
        if self.conn:
            self.conn.commit()
            self.conn.close()

# ---------------------------------------------------------------------------
# GLOBAL LINK EXTRACTOR (Extracts absolutely all link types & direct files)
# ---------------------------------------------------------------------------
import re
LINK_PATTERN = re.compile(
    r'(?:https?|ftp|ftps|ssh|git|svn|ws|wss|magnet|ipfs|ipns|onion|file)://[^\s<>"\'{}|\\^`]+', 
    re.IGNORECASE
)

def extract_all_links(text: str, base_url: str) -> set:
    links = set()
    if not text:
        return links
    
    for m in LINK_PATTERN.finditer(text):
        links.add(m.group(0).rstrip('.,;:)>]'))

    try:
        soup = BeautifulSoup(text, 'lxml')
        for tag in soup.find_all(['a', 'link', 'script', 'img', 'iframe', 'source', 'embed', 'audio', 'video']):
            for attr in ('href', 'src', 'data-src', 'action'):
                val = tag.get(attr)
                if val:
                    val = val.strip()
                    if val.startswith('/') or not urlparse(val).scheme:
                        try:
                            val = urljoin(base_url, val)
                        except Exception:
                            continue
                    links.add(val)
    except Exception:
        pass

    cleaned = set()
    for l in links:
        if l and len(l) < 4000:
            url, _ = urldefrag(l)
            cleaned.add(url)
    return cleaned

# ---------------------------------------------------------------------------
# CRAWLER ENGINE
# ---------------------------------------------------------------------------
class Crawler:
    def __init__(self):
        self.cfg = Config()
        self.db = Database(self.cfg)
        self.queue = asyncio.Queue(maxsize=self.cfg.max_queue_size)
        self.session = None
        self.active = True

    def get_yerevan_time(self) -> datetime:
        """Վերադարձնում է ընթացիկ ժամը Երևանի ժամային գոտով (UTC+4)"""
        utc_now = datetime.now(timezone.utc)
        return utc_now.astimezone(timezone(timedelta(hours=4)))

    async def _periodic_flush_loop(self):
        while True:
            await asyncio.sleep(self.cfg.flush_interval)
            if self.active:
                await self.db.flush()
                logger.info("💾 Auto-flush. Total links in active DB: %d", self.db.total_count())

    async def _seed(self):
        logger.info("🌱 Seeding mega hubs with billions of internal/external links...")
        seeds = [
            "https://curlie.org/en",                          # Ամենամեծ կատալոգը
            "https://dmoz-odp.org/",                           # Հսկայական ինդեքսացված արխիվ
            "https://www.directoryofdirectories.com/",         # Միլիոնավոր ֆայլերի հղումներ
            "https://archive.org/details/software",            # Ուղիղ ֆայլեր և մեդիա
            "https://thepiratebay.org/",                       # Տորենտներ և Magnet հղումներ
            "https://libgen.is/",                              # Գրքեր, PDF-ներ, արխիվներ
            "https://news.ycombinator.com/lists",              # Արժեքավոր տեխնոլոգիական հղումներ
            "https://reddit.com/r/all",                        # Աշխարհի ամենաակտիվ էջը
            "https://github.com/collections",                  # Կոդեր և ռեպոզիտորիաներ
            "https://en.wikipedia.org/wiki/Portal:Contents",   # Վիքիպեդիայի մայր էջը
            "https://www.w3.org/Consortium/Member/List"        # Պաշտոնական գլոբալ ցուցակ
        ]
        await self.db.insert_many(seeds, source='seed')
        await self.db.flush()

        pending = await self.db.get_pending(3000)
        logger.info("Loaded %d URLs to active queue.", len(pending))
        for url in pending:
            await self.queue.put(url)

    async def _worker(self):
        while True:
            if not self.active:
                await asyncio.sleep(1)
                continue

            try:
                url = await asyncio.wait_for(self.queue.get(), timeout=5)
            except asyncio.TimeoutError:
                continue

            try:
                async with self.session.get(url, allow_redirects=True, ssl=False) as resp:
                    if resp.status == 200:
                        text = await resp.text(errors='ignore')
                        found_links = extract_all_links(text, url)
                        
                        if found_links and self.active:
                            await self.db.insert_many(found_links)
                            for fl in list(found_links)[:80]:
                                try:
                                    self.queue.put_nowait(fl)
                                except asyncio.QueueFull:
                                    break
            except Exception:
                pass
            finally:
                self.queue.task_done()

    async def upload_to_internet_archive(self, file_path: str):
        """Վերբեռնում է .db ֆայլը Internet Archive-ի քո նշված էջի մեջ (Retry-ով)"""
        if not self.cfg.ia_access_key or not self.cfg.ia_secret_key:
            logger.warning("⚠️ Internet Archive keys are missing! Upload skipped.")
            return False

        filename = os.path.basename(file_path)
        upload_url = f"https://s3.us.archive.org/{self.cfg.ia_identifier}/{filename}"
        
        headers = {
            "Authorization": f"LOW {self.cfg.ia_access_key}:{self.cfg.ia_secret_key}",
            "X-Archive-Create-Bucket": "0",  # Էջը արդեն գոյություն ունի
            "X-Archive-Keep-Old-Version": "1"
        }

        # 3 անգամ Retry ձախողման դեպքում
        for attempt in range(1, 4):
            logger.info("📡 Upload attempt %d/3 for %s...", attempt, filename)
            try:
                async with aiohttp.ClientSession() as upload_session:
                    with open(file_path, "rb") as f_data:
                        async with upload_session.put(upload_url, data=f_data, headers=headers) as resp:
                            if resp.status == 200:
                                logger.info("🎉 SUCCESS! %s uploaded to IA.", filename)
                                return True
                            else:
                                resp_text = await resp.text()
                                logger.error("❌ Attempt %d failed. Status: %d, Msg: %s", attempt, resp.status, resp_text)
            except Exception as e:
                logger.error("❌ Exception during upload attempt %d: %s", attempt, e)
            await asyncio.sleep(10)
        return False

    async def run_archive_routine(self):
        """23:55-ի արխիվացման գործողությունները"""
        logger.info("🕒 It is 23:55 (Yerevan Time). Pausing Crawler for Archive Routine...")
        self.active = False
        await asyncio.sleep(2) # Սպասում ենք, որ վերջին հարցումները փակվեն
        await self.db.flush()

        # 1. Հաշվում ենք ընդհանուր քանակը
        total_links = self.db.total_count()
        logger.info("Total links collected today: %d", total_links)

        # 2. Ձևավորում ենք ֆայլի անունը (MM_DD_YYYY_links_count.db)
        yerevan_now = self.get_yerevan_time()
        date_str = yerevan_now.strftime("%m_%d_%Y")
        archive_filename = f"{date_str}_links_{total_links}.db"

        # 3. Փակում ենք բազայի կապը, որպեսզի ֆայլը ապահով պատճենվի
        self.db.close()
        shutil.copy(Config.db_path, archive_filename)
        logger.info("Created daily archive copy: %s", archive_filename)

        # 4. Վերբեռնում ենք Internet Archive
        upload_success = await self.upload_to_internet_archive(archive_filename)
        
        # 5. Ջնջում ենք տեղային պատճենը վերբեռնելուց հետո
        if os.path.exists(archive_filename):
            os.remove(archive_filename)

        # 6. Ժամը 00:00-ի նոր սեսիայի պատրաստում
        logger.info("Waiting for midnight (00:00) to start new session...")
        while True:
            now = self.get_yerevan_time()
            if now.hour == 0 and now.minute >= 0:
                break
            await asyncio.sleep(5)

        # 7. Ջնջում ենք հին links.db-ն և ստեղծում նորը
        if os.path.exists(Config.db_path):
            os.remove(Config.db_path)
            # Եթե WAL ռեժիմի կողմնակի ֆայլերը կան, դրանք էլ ենք ջնջում
            for ext in ['-wal', '-journal', '-shm']:
                if os.path.exists(Config.db_path + ext):
                    os.remove(Config.db_path + ext)

        logger.info("🆕 Starting new session for a brand new day!")
        self.db.connect()
        
        # 8. Մաքրում ենք հին հերթը ու նորից սնուցում Seed-երով
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except Exception:
                break

        await self._seed()
        self.active = True
        logger.info("🚀 Crawler resumed successfully.")

    async def _time_monitor_loop(self):
        """Անդադար հսկում է Երևանի ժամանակը 23:55-ին հասնելու համար"""
        while True:
            now = self.get_yerevan_time()
            if now.hour == 23 and now.minute == 55:
                await self.run_archive_routine()
            await asyncio.sleep(15) # Ստուգում ենք 15 վայրկյանը մեկ

    async def run(self):
        logger.info("🪐 AWEC Continuous Planetary Crawler Initiated...")
        
        connector = aiohttp.TCPConnector(limit=0, limit_per_host=0, force_close=True)
        timeout = aiohttp.ClientTimeout(total=self.cfg.request_timeout)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)

        # Գործարկում ենք ֆոնային պարբերական աշխատանքները
        asyncio.create_task(self._periodic_flush_loop())
        asyncio.create_task(self._time_monitor_loop())

        # Եթե բազան դատարկ է, լցնում ենք Seed-երով
        if self.db.total_count() == 0:
            await self._seed()
        else:
            pending = await self.db.get_pending(3000)
            for url in pending:
                await self.queue.put(url)

        # Աշխատողներ
        workers = [asyncio.create_task(self._worker()) for _ in range(self.cfg.max_workers)]

        # Անվերջ պահում ենք սկրիպտը ակտիվ (քանի որ VPS-ի վրա է աշխատելու)
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutting down...")
            for w in workers:
                w.cancel()
            await self.db.flush()
            await self.session.close()
            self.db.close()

if __name__ == "__main__":
    asyncio.run(Crawler().run())
