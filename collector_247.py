#!/usr/bin/env python3
import asyncio
import aiohttp
import os
import re
import sys
import sqlite3
import shutil
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
DB_PATH = "links.db"
LOG_FILE = "logs/crawler.log"
IA_IDENTIFIER = "awec_links_awe_o.s"
IA_ACCESS_KEY = os.environ.get("IA_ACCESS_KEY")
IA_SECRET_KEY = os.environ.get("IA_SECRET_KEY")

# Գերարագ կանոնավոր արտահայտություն (Regex)՝ ցանկացած տեսակի ուղիղ ֆայլեր և հղումներ քաղելու համար
LINK_PATTERN = re.compile(
    r'(?:https?|ftp|ftps|ssh|git|svn|ws|wss|magnet|ipfs|ipns|onion|file)://[^\s<>"\'+]+', 
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# UTILS & TIME
# ---------------------------------------------------------------------------
os.makedirs("logs", exist_ok=True)

def log(msg):
    t = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=4))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{t} [AWEC] {msg}")
    sys.stdout.flush()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{t} {msg}\n")

def get_yerevan_time():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=4)))

# ---------------------------------------------------------------------------
# DATABASE (SQLite optimized for raw write speed)
# ---------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")  # Գերարագ գրելու համար (առանց սպասելու սկավառակին)
    conn.execute("PRAGMA cache_size=-128000") # 128MB Cache հիշողության (RAM) մեջ
    conn.execute("""
        CREATE TABLE IF NOT EXISTS urls (
            url TEXT PRIMARY KEY,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    return conn

# ---------------------------------------------------------------------------
# MEGASPEED STREAMING CRAWLER
# ---------------------------------------------------------------------------
class FastCrawler:
    def __init__(self):
        self.conn = init_db()
        self.queue = set()
        self.session = None
        self.active = True
        self.total_inserted_today = 0  # Օրվա ընթացքում հավաքվածների քաունթեր

    async def upload_to_ia(self, file_path):
        if not IA_ACCESS_KEY or not IA_SECRET_KEY:
            log("⚠️ IA Keys missing. Skip upload.")
            return False
        
        filename = os.path.basename(file_path)
        upload_url = f"https://s3.us.archive.org/{IA_IDENTIFIER}/{filename}"
        headers = {
            "Authorization": f"LOW {IA_ACCESS_KEY}:{IA_SECRET_KEY}",
            "X-Archive-Create-Bucket": "0",
            "X-Archive-Keep-Old-Version": "1"
        }
        
        log(f"📡 Uploading {filename} to archive.org...")
        try:
            async with aiohttp.ClientSession() as up_session:
                with open(file_path, "rb") as f:
                    async with up_session.put(upload_url, data=f, headers=headers) as r:
                        if r.status == 200:
                            log("🎉 IA Upload successful!")
                            return True
                        log(f"❌ IA Failed: {r.status}")
        except Exception as e:
            log(f"❌ Upload error: {e}")
        return False

    async def check_and_archive(self):
        """Հսկում է Երևանի ժամը (23:55-ին ավտոմատ ուղարկում է)"""
        while True:
            now = get_yerevan_time()
            if now.hour == 23 and now.minute == 55:
                log("🕒 It's 23:55! Executing Daily Archive...")
                self.active = False
                await asyncio.sleep(3)
                
                # Հաշվում ենք քանակը
                total = self.conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
                date_str = now.strftime("%m_%d_%Y")
                archive_name = f"{date_str}_links_{total}.db"
                
                # Պատճենում և ուղարկում ենք
                self.conn.commit()
                self.conn.close()
                shutil.copy(DB_PATH, archive_name)
                
                await self.upload_to_ia(archive_name)
                
                if os.path.exists(archive_name):
                    os.remove(archive_name)
                
                # Ջնջում ենք հինը, սկսում նորը 00:00-ին
                log("Waiting for 00:00 to start fresh session...")
                while get_yerevan_time().hour != 0:
                    await asyncio.sleep(5)
                
                if os.path.exists(DB_PATH):
                    os.remove(DB_PATH)
                    for ext in ['-wal', '-shm', '-journal']:
                        if os.path.exists(DB_PATH + ext):
                            os.remove(DB_PATH + ext)
                
                self.conn = init_db()
                self.queue.clear()
                self.total_inserted_today = 0
                await self.seed()
                self.active = True
                
            await asyncio.sleep(10)

    async def seed(self):
        seeds = [
            "https://curlie.org/en",
            "https://dmoz-odp.org/",
            "https://www.directoryofdirectories.com/",
            "https://archive.org/details/software",
            "https://thepiratebay.org/",
            "https://libgen.is/",
            "https://news.ycombinator.com/lists",
            "https://reddit.com/r/all",
            "https://github.com/collections",
            "https://en.wikipedia.org/wiki/Portal:Contents"
            "https://github.com/sindresorhus/awesome",
            "https://en.wikipedia.org/wiki/Special:AllPages",
            "https://en.wikipedia.org/wiki/Special:RecentChanges",
            "https://news.ycombinator.com/newest",
            "https://news.ycombinator.com/show",
            "https://www.reddit.com/r/all/new/",
            "https://www.reddit.com/r/selfhosted/",
            "https://www.gutenberg.org/browse/recent/last7",
            "https://archive.org/details/texts",
            "https://archive.org/details/movies",
            "https://archive.org/details/audio",
            "https://www.producthunt.com/",
            "https://slashdot.org/",
            "https://digg.com/",
            "https://pinboard.in/popular/",
            "https://www.tumblr.com/explore/trending",
            "https://medium.com/topics",
            "https://www.quora.com/sitemap/questions",
            "https://stackoverflow.com/questions",
            "https://github.com/trending",
            "https://sourceforge.net/directory/",
            "https://alternativeto.net/",
            "https://www.allmusic.com/",
            "https://www.imdb.com/feature/genre/",
            "https://www.deviantart.com/topic/visual-art",
            "https://www.behance.net/galleries",
            "https://dribbble.com/shots",
            "https://www.flickr.com/explore",
            "https://vimeo.com/watch",
            "https://www.dailymotion.com",
            "https://www.twitch.tv/directory",
            "https://steamcommunity.com/discussions",
            "https://itch.io/games",
            "https://bandcamp.com/tag/electronic",
            "soundcloud.com/discover",
            "https://www.mixcloud.com/discover/",
            "https://open.spotify.com/genre/discover-page",
            "https://www.discogs.com/search/",
            "https://www.last.fm/music",
            "https://www.reverbnation.com/main/charts",
            "https://arxiv.org/list/cs/new",
            "https://www.biorxiv.org/collection/all",
            "https://www.medrxiv.org/content/early/recent",
            "https://www.ssrn.com/index.cfm/en/",
            "https://www.researchgate.net/directory/publications",
            "https://www.academia.edu/Documents",
            "https://www.semanticscholar.org/",
            "https://www.base-search.net/",
            "https://core.ac.uk/",
            "https://www.wikidata.org/wiki/Wikidata:Main_Page"
        ]
        for s in seeds:
            self.queue.add(s)
            self.conn.execute("INSERT OR IGNORE INTO urls (url, status) VALUES (?, 'pending')", (s,))
        self.conn.commit()
        db_count = self.conn.execute('SELECT COUNT(*) FROM urls').fetchone()[0]
        log(f"🌱 Seeded. Total DB: {db_count} links.")

    async def worker(self):
        """Անսահմանափակ արագագործ worker"""
        while True:
            if not self.active or not self.queue:
                await asyncio.sleep(0.01)  # Շատ կարճ սպասում՝ CPU-ն չծանրաբեռնելու համար
                continue
            
            url = self.queue.pop()
            try:
                # Թեթև հարցում առանց SSL ստուգման ու ավելորդ գլխամասերի
                async with self.session.get(url, ssl=False, timeout=5) as resp:
                    if resp.status == 200:
                        text = await resp.text(errors='ignore')
                        # Կայծակնային Regex որոնում
                        found = LINK_PATTERN.findall(text)
                        
                        if found:
                            # Զտում ենք չափազանց երկար հղումները
                            valid_links = [(l, 'pending') for l in found if len(l) < 500]
                            
                            # Միանգամից Batch (Փաթեթային) գրում բազա
                            cursor = self.conn.cursor()
                            cursor.executemany(
                                "INSERT OR IGNORE INTO urls (url, status) VALUES (?, 'pending')",
                                valid_links
                            )
                            self.conn.commit()
                            
                            # Քանակի ավելացում
                            self.total_inserted_today += cursor.rowcount
                            
                            # Լցնում ենք հերթը շղթան շարունակելու համար
                            for item in valid_links[:150]:
                                if len(self.queue) < 150_000:
                                    self.queue.add(item[0])
            except Exception:
                pass

    async def run(self):
        log("🚀 AWEC Ultra-Speed Engine Started...")
        # Օպտիմալ միացումների քանակ (բարձրացրել ենք մինչև 300 զուգահեռ սեսիա)
        connector = aiohttp.TCPConnector(limit=300, ttl_dns_cache=300, ssl=False)
        self.session = aiohttp.ClientSession(connector=connector)
        
        await self.seed()
        
        asyncio.create_task(self.check_and_archive())
        
        # Գործարկում ենք 180 կայծակնային զուգահեռ Worker-ներ
        workers = [asyncio.create_task(self.worker()) for _ in range(180)]
        
        try:
            while True:
                await asyncio.sleep(2)  # Ամեն 2 վայրկյանը մեկ թարմացվող լոգ
                if self.active:
                    total_in_db = self.conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
                    log(f"📊 [PROGRESS] Total URL count in links.db: {total_in_db} | Queue: {len(self.queue)} | Added this session: +{self.total_inserted_today}")
        except (KeyboardInterrupt, SystemExit):
            self.conn.commit()
            self.conn.close()
            await self.session.close()

if __name__ == "__main__":
    asyncio.run(FastCrawler().run())
