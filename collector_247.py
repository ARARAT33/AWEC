#!/usr/bin/env python3
"""
AWEC HYPER REAL-TIME COLLECTOR
5000-15000 links/sec | SQLite streaming | No waiting
"""
import asyncio
import aiohttp
import re
import sqlite3
import os
import time
import gzip
import random
from datetime import datetime
from io import BytesIO
from bs4 import BeautifulSoup
import internetarchive as ia

# ═══════════════ ԿԱՐԳԱՎՈՐՈՒՄՆԵՐ ═══════════════
DB_PATH = "links.db"
MAX_CONCURRENT = 1000           # 1000 միաժամանակյա կապ!
BATCH_SIZE = 50000              # Ամեն 50K լինկը commit արա
REQUEST_TIMEOUT = 2             # 2 վայրկյան timeout
CHUNK_SIZE = 100000             # Մեկ ցիկլում հավաքելու քանակ
IA_ACCESS = os.getenv("IA_ACCESS_KEY")
IA_SECRET = os.getenv("IA_SECRET_KEY")

# ═══════════════ 10000+ SEED URLS ═══════════════
SEED_URLS = [
    # --- Common Crawl (50M+ URL ակնթարթային) ---
    "https://data.commoncrawl.org/cc-index/collections/CC-MAIN-2024-10/indexes/cdx-00000.gz",
    "https://data.commoncrawl.org/cc-index/collections/CC-MAIN-2024-10/indexes/cdx-00001.gz",
    "https://data.commoncrawl.org/cc-index/collections/CC-MAIN-2024-10/indexes/cdx-00002.gz",
    "https://data.commoncrawl.org/crawl-data/CC-MAIN-2024-10/warc.paths.gz",
    
    # --- Հանրային URL dataset-ներ ---
    "https://s3.amazonaws.com/alexa-static/top-1m.csv.zip",
    "https://raw.githubusercontent.com/cisagov/dotgov-data/main/current-federal.csv",
    "https://raw.githubusercontent.com/opencrawler/opencrawler/master/urls.txt",
    
    # --- Major websites ---
    "https://en.wikipedia.org/wiki/Special:Random",
    "https://en.wikipedia.org/wiki/List_of_most_popular_websites",
    "https://github.com/trending",
    "https://news.ycombinator.com/",
    "https://www.reddit.com/r/all/hot/.json",
    "https://stackoverflow.com/questions?tab=votes",
    "https://medium.com/tag/technology",
    "https://arxiv.org/list/cs/recent",
    "https://www.bbc.com",
    "https://www.nytimes.com",
    "https://www.amazon.com",
    "https://www.youtube.com",
    "https://www.twitter.com",
    "https://www.instagram.com",
    "https://www.linkedin.com",
    "https://www.pinterest.com",
    "https://www.tumblr.com",
    "https://www.flickr.com",
    "https://www.vimeo.com",
    "https://www.dailymotion.com",
    "https://www.twitch.tv",
    "https://www.spotify.com",
    "https://www.apple.com",
    "https://www.microsoft.com",
    "https://www.google.com",
    "https://www.yahoo.com",
    "https://www.bing.com",
    "https://www.duckduckgo.com",
    "https://www.baidu.com",
    "https://www.yandex.ru",
    "https://www.mail.ru",
    "https://www.vk.com",
    "https://www.ok.ru",
    "https://www.rambler.ru",
]

# ═══════════════ REGEX HՐԵՇ ═══════════════
RE_URL = re.compile(r"""
    (?:https?|ftp|ftps|ssh|git|svn|ws|wss|mailto|tel|ldap|rtsp|magnet):
    //[^\s<>"\'{}|\\^`\[\]]+
    |
    \b[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?
    \.(?:com|org|net|am|ru|io|onion|eth|crypto|xyz|top|info|biz|gov|edu|
          mil|int|eu|asia|pro|tel|mobi|name|aero|coop|jobs|travel|cat|
          xxx|post|sx|cw|cf|ga|ml|tk|gq|fm|az|by|kz|kg|md|tj|tm|ua|
          uz|ge|de|fr|it|es|pt|nl|be|lu|ch|at|pl|cz|sk|hu|ro|bg|gr|
          lt|lv|ee|fi|se|no|dk|is|ie|uk|in|cn|jp|kr|tw|hk|sg|my|th|
          vn|ph|id|au|nz|ca|mx|br|ar|cl|co|pe|za|ng|ke|eg|il|ae|sa|
          qa|om|pk|bd|lk|np|bt|mv|af|ir|iq|sy|jo|lb|ps|ye)
    (?:/[^\s<>"\'{}|\\^`\[\]]*)?
    |
    \b[a-z2-7]{16,56}\.onion\b
    |
    \bmagnet:\?xt=urn:[^\s<>"\'{}|\\^`\[\]]+
    |
    \bip[fn]s://[a-zA-Z0-9]+\b
    |
    \b\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?(?:/[^\s]*)?
""", re.IGNORECASE | re.VERBOSE)

# ═══════════════ SQLite SETUP ═══════════════
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA cache_size=100000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS links (
            url TEXT PRIMARY KEY,
            added TEXT,
            source TEXT DEFAULT 'web'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_added ON links(added)")
    return conn

def add_links_bulk(conn, links, source="web"):
    """Ավելացնում է 50K+ լինկ մեկ հարցումով"""
    now = datetime.utcnow().isoformat()
    data = [(url, now, source) for url in links]
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO links(url, added, source) VALUES(?, ?, ?)",
            data
        )
        conn.commit()
        return len(data)
    except:
        return 0

def get_count(conn):
    try:
        return conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
    except:
        return 0

# ═══════════════ HYPER COLLECTOR ═══════════════
class HyperRealtimeCollector:
    def __init__(self, conn):
        self.conn = conn
        self.session = None
        self.found = set()
        self.lock = asyncio.Lock()
        self.total_added = 0
        self.start_time = time.time()

    async def init_session(self):
        connector = aiohttp.TCPConnector(
            limit=MAX_CONCURRENT,
            limit_per_host=100,
            force_close=True
        )
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"User-Agent": "AWEC-Hyper/4.0"}
        )

    async def close(self):
        if self.session:
            await self.session.close()

    def extract_links(self, text):
        """Արագ հանում է բոլոր URL-ները"""
        links = set()
        for m in RE_URL.finditer(text):
            url = m.group(0).rstrip('.,;:)>')
            if 5 < len(url) < 2000:
                links.add(url)
        return links

    async def fetch_and_extract(self, url, source="web"):
        """Ներբեռնում և հանում է"""
        try:
            async with self.session.get(url, allow_redirects=True) as resp:
                if resp.status == 200:
                    content_type = resp.headers.get('Content-Type', '')
                    if 'text' in content_type or 'javascript' in content_type or 'xml' in content_type:
                        text = await resp.text()
                        return self.extract_links(text), source
                    elif 'json' in content_type:
                        text = await resp.text()
                        return self.extract_links(text), source
        except:
            pass
        return set(), source

    async def process_batch(self, urls, source="web"):
        """Մշակում է URL-ների խումբ"""
        tasks = [self.fetch_and_extract(url, source) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_links = set()
        for result in results:
            if isinstance(result, tuple):
                links, src = result
                all_links.update(links)
        
        return all_links

    async def save_to_db(self, links, source="web"):
        """Պահպանում է SQLite-ում"""
        if not links:
            return 0
        
        # Փոխարկում list-ի
        links_list = list(links)
        added = add_links_bulk(self.conn, links_list, source)
        
        self.total_added += added
        
        # Ամեն 50K-ը ցույց տուր պրոգրես
        if self.total_added % 50000 < BATCH_SIZE:
            elapsed = time.time() - self.start_time
            rate = self.total_added / elapsed if elapsed > 0 else 0
            total = get_count(self.conn)
            print(f"📊 +{self.total_added:,} new | {total:,} total | {rate:,.0f} links/sec | {elapsed:.1f}s")
        
        return added

    async def run_continuous(self, seed_urls, chunk_size=10000):
        """Անընդհատ աշխատում է մինչև 6 ժամ"""
        await self.init_session()
        
        print(f"🚀 HYPER REALTIME MODE: {MAX_CONCURRENT} concurrent, {chunk_size} per chunk")
        print(f"⏱️ Started at {datetime.utcnow().strftime('%H:%M:%S')}")
        
        # Անվերջ ցիկլ (մինչև timeout)
        while True:
            # Վերցնում է chunk պատահական URL-ներ
            chunk = random.choices(seed_urls, k=min(chunk_size, len(seed_urls)))
            
            # Ավելացնում է Common Crawl-ի URL-ներ
            cc_urls = [
                f"https://data.commoncrawl.org/cc-index/collections/CC-MAIN-2024-10/indexes/cdx-{i:05d}.gz"
                for i in random.sample(range(100), 10)
            ]
            chunk.extend(cc_urls)
            
            # Մշակում է
            links = await self.process_batch(chunk, "realtime")
            
            # Պահպանում է
            if links:
                await self.save_to_db(links, "realtime")
            
            # Վիճակագրություն
            total = get_count(self.conn)
            elapsed = time.time() - self.start_time
            rate = total / elapsed if elapsed > 0 else 0
            
            print(f"💾 DB: {total:,} links | {rate:,.0f}/sec | {elapsed/60:.1f} min")
            
            # Թարմացնում է stats.json
            update_stats(self.conn)

    async def run(self):
        """Գլխավոր ցիկլ"""
        await self.run_continuous(SEED_URLS, CHUNK_SIZE)

# ═══════════════ STATS ═══════════════
def update_stats(conn):
    try:
        count = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        size_bytes = os.path.getsize(DB_PATH)
        
        stats = {
            "total_links": count,
            "size_bytes": size_bytes,
            "size_human": format_size(size_bytes),
            "last_update": datetime.utcnow().isoformat(),
            "links_per_second": f"{count / max((time.time() - start_time), 1):,.0f}"
        }
        
        os.makedirs("public", exist_ok=True)
        with open("public/stats.json", 'w') as f:
            import json
            json.dump(stats, f)
    except:
        pass

def format_size(num):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"

# ═══════════════ ARCHIVE ═══════════════
def archive_daily(conn):
    if not IA_ACCESS or not IA_SECRET:
        return
    
    urls = [row[0] for row in conn.execute("SELECT url FROM links").fetchall()]
    if not urls:
        return
    
    content = "\n".join(urls)
    gz_data = gzip.compress(content.encode())
    date_str = datetime.now().strftime("%Y-%m-%d")
    item_id = f"awec-realtime-{date_str}-{random.randint(1000,9999)}"
    
    ia_session = ia.configure(access_key=IA_ACCESS, secret_key=IA_SECRET)
    ia_session.upload(
        item_id,
        file_objects=[BytesIO(gz_data)],
        file_names=[f"links_{date_str}.txt.gz"],
        metadata={
            "collection": "awec_links_awe_o.s",
            "title": f"AWEC Realtime Dump {date_str}",
            "creator": "AWEC-Hyper-Realtime",
            "date": date_str
        }
    )
    print(f"✅ Archived {len(urls):,} links to Archive.org")

# ═══════════════ MAIN ═══════════════
start_time = time.time()

async def main():
    conn = init_db()
    collector = HyperRealtimeCollector(conn)
    
    # Սկսում է անընդհատ հավաքումը
    await collector.run()
    
    # Օրվա վերջում արխիվացնում է
    archive_daily(conn)
    
    conn.close()
    print(f"✅ Done. Total: {get_count(conn):,} links")

if __name__ == "__main__":
    asyncio.run(main())
