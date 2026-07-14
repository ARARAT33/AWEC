#!/usr/bin/env python3
import asyncio
import aiohttp
import os
import re
import sys
import sqlite3
import shutil
from datetime import datetime, timedelta, timezone

DB_PATH = "links.db"
LOG_FILE = "logs/crawler.log"
IA_IDENTIFIER = "awec_links_awe_o.s"
IA_ACCESS_KEY = os.environ.get("IA_ACCESS_KEY")
IA_SECRET_KEY = os.environ.get("IA_SECRET_KEY")

LINK_PATTERN = re.compile(r'https?://[^\s<>"\'+]+', re.IGNORECASE)

os.makedirs("logs", exist_ok=True)

def log(msg):
    t = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=4))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{t} [AWEC] {msg}")
    sys.stdout.flush()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{t} {msg}\n")

class ContinuousHarvester:
    def __init__(self):
        self.db_conn = None
        self.session = None
        self.active = True
        self.total_saved = 0
        self.visited_urls = set()
        self.active_pool = list()

    def init_db(self):
        self.db_conn = sqlite3.connect(DB_PATH)
        # Օգտագործում ենք TRUNCATE ռեժիմ WAL-ի փոխարեն, որպեսզի տվյալները միանգամից գրվեն հիմնական ֆայլում
        self.db_conn.execute("PRAGMA journal_mode=TRUNCATE")
        self.db_conn.execute("PRAGMA synchronous=NORMAL")
        self.db_conn.execute("CREATE TABLE IF NOT EXISTS urls (url TEXT PRIMARY KEY)")
        self.db_conn.commit()

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

    async def worker(self):
        while True:
            if not self.active or not self.active_pool:
                await asyncio.sleep(0.01)
                continue

            url = self.active_pool.pop(0) if self.active_pool else None
            if not url:
                continue

            try:
                async with self.session.get(url, ssl=False, timeout=4) as resp:
                    if resp.status == 200:
                        text = await resp.text(errors='ignore')
                        found = LINK_PATTERN.findall(text)
                        
                        new_links = []
                        for l in found:
                            if len(l) < 300 and l.startswith(('http://', 'https://')):
                                if l not in self.visited_urls:
                                    self.visited_urls.add(l)
                                    new_links.append(l)

                        if new_links:
                            cursor = self.db_conn.cursor()
                            cursor.executemany("INSERT OR IGNORE INTO urls (url) VALUES (?)", [(link,) for link in new_links])
                            self.db_conn.commit()
                            self.total_saved += cursor.rowcount
                            
                            if len(self.active_pool) < 100000:
                                self.active_pool.extend(new_links[:100])
            except Exception:
                pass

    async def run(self):
        log("🚀 AWEC Non-Stop Fast Harvester Started...")
        self.init_db()
        self.seed()
        
        connector = aiohttp.TCPConnector(limit=300, force_close=True, ssl=False)
        self.session = aiohttp.ClientSession(connector=connector)
        
        for _ in range(180):
            asyncio.create_task(self.worker())
        
        try:
            while True:
                await asyncio.sleep(2)
                if self.active:
                    real_db_count = self.db_conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
                    log(f"📊 [LIVE STATE] Links inside links.db: {real_db_count} | Session Added: +{self.total_saved} | Queue: {len(self.active_pool)}")
        except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            pass
        finally:
            # Սա երաշխավորում է, որ ցանկացած անջատման դեպքում տվյալները 100% կգրվեն սկավառակին
            log("💾 Safely saving database before exit...")
            self.db_conn.commit()
            self.db_conn.close()
            await self.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(ContinuousHarvester().run())
    except KeyboardInterrupt:
        pass
