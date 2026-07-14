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

# Գերարագ Regex՝ ցանկացած տեսակի հղում RAW տեքստից միանգամից քաղելու համար
LINK_PATTERN = re.compile(r'https?://[^\s<>"\'+]+', re.IGNORECASE)

os.makedirs("logs", exist_ok=True)

# ---------------------------------------------------------------------------
# 2. ՕԺԱՆԴԱԿ ՖՈՒՆԿՑԻԱՆԵՐ
# ---------------------------------------------------------------------------
def log(msg):
    t = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=4))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{t} [AWEC] {msg}")
    sys.stdout.flush()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{t} {msg}\n")

def get_yerevan_time():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=4)))

# ---------------------------------------------------------------------------
# 3. ԳԵՐԱՐԱԳ ՇԱՐԺԻՉԸ (ԱՌԱՆՑ ՀԵՐԹԻ)
# ---------------------------------------------------------------------------
class FastHarvester:
    def __init__(self):
        self.db_conn = None
        self.session = None
        self.active = True
        self.total_saved = 0  # Բազա գրվածների իրական քանակը

    def init_db(self):
        self.db_conn = sqlite3.connect(DB_PATH)
        self.db_conn.execute("PRAGMA journal_mode=WAL")
        self.db_conn.execute("PRAGMA synchronous=OFF")  # Գերարագ գրելու համար (առանց սկավառակին սպասելու)
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
                log("🕒 It's 23:55! Executing Daily Archive...")
                self.active = False
                await asyncio.sleep(5)
                
                self.db_conn.commit()
                self.db_conn.close()
                
                # Արխիվի ֆայլի անունը
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
                self.init_db()
                self.active = True

            await asyncio.sleep(10)

    async def fetch_and_save(self, url):
        """Կարդում է կայքը, քաղում հղումները և միանգամից գրում բազա"""
        if not self.active:
            return

        try:
            async with self.session.get(url, ssl=False, timeout=5) as resp:
                if resp.status == 200:
                    text = await resp.text(errors='ignore')
                    found = LINK_PATTERN.findall(text)
                    
                    # Զտում ենք չափազանց երկար ու սխալ հղումները
                    valid_links = [(l,) for l in found if len(l) < 300 and l.startswith(('http://', 'https://'))]
                    
                    if valid_links:
                        cursor = self.db_conn.cursor()
                        # Միանգամից գրում ենք բազայի մեջ առանց հերթի
                        cursor.executemany("INSERT OR IGNORE INTO urls (url) VALUES (?)", valid_links)
                        self.db_conn.commit()
                        self.total_saved += cursor.rowcount
        except Exception:
            pass

    async def run(self):
        log("🚀 AWEC Non-Stop Fast Harvester Started...")
        self.init_db()
        
        # 300 զուգահեռ միացումների հնարավորություն
        connector = aiohttp.TCPConnector(limit=300, force_close=True, ssl=False)
        self.session = aiohttp.ClientSession(connector=connector)
        
        # Ֆոնային արխիվացումը
        asyncio.create_task(self.archive_routine())

        # 50 Mega Seeds
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

        # Գործարկում ենք բոլոր seed-երը միաժամանակ
        tasks = [asyncio.create_task(self.fetch_and_save(url)) for url in seeds]
        
        # Պարբերական Լոգեր (Ամեն 2 վայրկյանը մեկ կոնսոլում ցույց է տալիս, թե ինչքան հղում գրվեց db-ում)
        try:
            while self.active:
                await asyncio.sleep(2)
                # Կարդում ենք SQL-ից իրական քանակը, որ համոզվենք, որ տվյալները գրվել են
                real_db_count = self.db_conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
                log(f"📊 [LIVE STATE] Links inside links.db: {real_db_count} | Session Added: +{self.total_saved}")
        except (KeyboardInterrupt, SystemExit):
            self.db_conn.commit()
            self.db_conn.close()
            await self.session.close()

if __name__ == "__main__":
    asyncio.run(FastHarvester().run())
