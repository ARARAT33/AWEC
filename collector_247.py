#!/usr/bin/env python3
import asyncio
import aiohttp
import os
import re
import sys
import sqlite3
import shutil
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# 1. ԿԱՐԳԱՎՈՐՈՒՄՆԵՐ
# ---------------------------------------------------------------------------
DB_PATH = "links.db"
LOG_FILE = "logs/crawler.log"
IA_IDENTIFIER = "awec_links_awe_o.s"
IA_ACCESS_KEY = os.environ.get("IA_ACCESS_KEY")
IA_SECRET_KEY = os.environ.get("IA_SECRET_KEY")

# Գերարագ Regex
LINK_PATTERN = re.compile(r'https?://[^\s<>"\'+]+', re.IGNORECASE)

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
# 2. ԳԵՐԱՐԱԳ ՇԱՐԺԻՉԸ (ԱՆԴԱԴԱՐ ՑԻԿԼ)
# ---------------------------------------------------------------------------
class ContinuousHarvester:
    def __init__(self):
        self.db_conn = None
        self.session = None
        self.active = True
        self.total_saved = 0
        
        # RAM-ի մեջ պահվող արագ բուֆերներ
        self.visited_urls = set()  # Կրկնությունները բացառելու համար
        self.active_pool = list()  # Հղումների ցիկլիկ ավազան (հերթ)

    def init_db(self):
        self.db_conn = sqlite3.connect(DB_PATH)
        self.db_conn.execute("PRAGMA journal_mode=WAL")
        self.db_conn.execute("PRAGMA synchronous=OFF")  # Գերարագ գրելու համար
        self.db_conn.execute("CREATE TABLE IF NOT EXISTS urls (url TEXT PRIMARY KEY)")
        self.db_conn.commit()

    async def upload_to_ia(self, file_path):
        if not IA_ACCESS_KEY or not IA_SECRET_KEY:
            log("⚠️ IA Keys are missing! Skipping upload.")
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
                            log("🎉 Internet Archive Upload successful!")
                            return True
                        log(f"❌ Upload failed: {r.status}")
        except Exception as e:
            log(f"❌ Upload error: {e}")
        return False

    async def archive_routine(self):
        """Ամեն օր 23:55-ին պահպանում և ուղարկում է Archive.org"""
        while True:
            now = get_yerevan_time()
            if now.hour == 23 and now.minute == 55:
                log("🕒 It's 23:55! Pausing spider and archiving...")
                self.active = False
                await asyncio.sleep(5)
                
                self.db_conn.commit()
                self.db_conn.close()
                
                date_str = now.strftime("%m_%d_%Y")
                archive_name = f"{date_str}_links_{self.total_saved}.db"
                
                shutil.copy(DB_PATH, archive_name)
                await self.upload_to_ia(archive_name)
                
                if os.path.exists(archive_name):
                    os.remove(archive_name)
                if os.path.exists(DB_PATH):
                    os.remove(DB_PATH)
                    for ext in ['-wal', '-shm', '-journal']:
                        if os.path.exists(DB_PATH + ext):
                            os.remove(DB_PATH + ext)

                log("Waiting for midnight (00:00) to start a new clean session...")
                while get_yerevan_time().hour != 0:
                    await asyncio.sleep(5)
                
                self.total_saved = 0
                self.visited_urls.clear()
                self.active_pool.clear()
                self.init_db()
                self.seed()
                self.active = True

            await asyncio.sleep(10)

    def seed(self):
        seeds = [
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
            "https://soundcloud.com/discover",
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
            self.visited_urls.add(s)
            self.active_pool.append(s)
            self.db_conn.execute("INSERT OR IGNORE INTO urls (url) VALUES (?)", (s,))
        self.db_conn.commit()
        log(f"🌱 Seeded {len(seeds)} Mega Links. Harvester ready to loop.")

    async def worker(self):
        """Անդադար աշխատող վորքեր՝ առանց կանգնելու հնարավորության"""
        while True:
            if not self.active or not self.active_pool:
                await asyncio.sleep(0.01)
                continue

            # Վերցնում ենք ակտիվ ավազանից հաջորդ հղումը
            url = self.active_pool.pop(0) if self.active_pool else None
            if not url:
                continue

            try:
                # Կայծակնային GET
                async with self.session.get(url, ssl=False, timeout=4) as resp:
                    if resp.status == 200:
                        text = await resp.text(errors='ignore')
                        found = LINK_PATTERN.findall(text)
                        
                        new_links = []
                        for l in found:
                            # Ստուգում ենք կրկնությունը RAM-ում (միլիվայրկյաններում)
                            if len(l) < 300 and l.startswith(('http://', 'https://')):
                                if l not in self.visited_urls:
                                    self.visited_urls.add(l)
                                    new_links.append(l)

                        if new_links:
                            # 1. Գրում ենք բազայի մեջ
                            cursor = self.db_conn.cursor()
                            cursor.executemany("INSERT OR IGNORE INTO urls (url) VALUES (?)", [(link,) for link in new_links])
                            self.db_conn.commit()
                            self.total_saved += cursor.rowcount
                            
                            # 2. Նոր հղումները հետ ենք լցնում ավազանի մեջ, որպեսզի շղթան երբեք չկտրվի (Recursion)
                            # Սահմանափակում ենք RAM-ի բուֆերը 100,000-ով, որ չպայթի
                            if len(self.active_pool) < 100000:
                                self.active_pool.extend(new_links[:100])
            except Exception:
                pass

    async def run(self):
        log("🚀 AWEC Non-Stop Fast Harvester Started...")
        self.init_db()
        self.seed()
        
        # 350 զուգահեռ ակտիվ TCP միացումներ
        connector = aiohttp.TCPConnector(limit=350, force_close=True, ssl=False)
        self.session = aiohttp.ClientSession(connector=connector)
        
        asyncio.create_task(self.archive_routine())

        # Միացնում ենք 200 զուգահեռ ակտիվ worker-ներ
        for _ in range(200):
            asyncio.create_task(self.worker())
        
        # Պարբերական Լոգեր
        try:
            while True:
                await asyncio.sleep(2)
                if self.active:
                    real_db_count = self.db_conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
                    log(f"📊 [LIVE STATE] Links inside links.db: {real_db_count} | Session Added: +{self.total_saved} | Queue: {len(self.active_pool)}")
        except (KeyboardInterrupt, SystemExit):
            self.db_conn.commit()
            self.db_conn.close()
            await self.session.close()

if __name__ == "__main__":
    asyncio.run(ContinuousHarvester().run())
