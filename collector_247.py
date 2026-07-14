#!/usr/bin/env python3
"""
AWEC 24/7 Hyper Collector – 25 min work / 30 sec sleep, 6-hour loops
"""
import asyncio, aiohttp, aiofiles, os, re, time, sqlite3, json, gzip, random
from datetime import datetime, timedelta
from io import BytesIO
from bs4 import BeautifulSoup
import internetarchive as ia

# ---- ԿԱՐԳԱՎՈՐՈՒՄՆԵՐ ----
DB_PATH = "links.db"
STATS_FILE = "public/stats.json"
SEED_URLS = [
    "https://en.wikipedia.org/wiki/Special:Random",
    "https://github.com/trending",
    "https://news.ycombinator.com/",
    "https://www.reddit.com/r/all/hot/.json",
    # ... ավելացրեք 1000+ սկզբնական URL
]
MAX_CONCURRENT = 200
WORK_MINUTES = 25
SLEEP_SECONDS = 30
IA_ACCESS = os.getenv("IA_ACCESS_KEY")
IA_SECRET = os.getenv("IA_SECRET_KEY")

# URL regex հրեշ
RE_URL = re.compile(r'(?:https?|ftp|magnet|ipfs)://[^\s<>"\'{}|\\^`\[\]]+|'
                    r'\b[a-z2-7]{16,56}\.onion\b|'
                    r'\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b|'
                    r'magnet:\?[^\s]+', re.I)

# ---- ՏՎՅԱԼՆԵՐԻ ԲԱԶԱ ----
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS links (url TEXT PRIMARY KEY, added TEXT)")
    return conn

def add_links(conn, links):
    now = datetime.utcnow().isoformat()
    new = 0
    with conn:
        for url in links:
            try:
                conn.execute("INSERT OR IGNORE INTO links(url,added) VALUES(?,?)", (url, now))
                if conn.total_changes > 0:
                    new += 1
            except:
                pass
    return new

def count_links(conn):
    return conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]

def get_db_size_mb():
    return os.path.getsize(DB_PATH) / (1024 * 1024)

def update_stats(conn):
    count = count_links(conn)
    size_bytes = os.path.getsize(DB_PATH)
    stats = {
        "total_links": count,
        "size_bytes": size_bytes,
        "size_human": format_size(size_bytes),
        "last_update": datetime.utcnow().isoformat()
    }
    os.makedirs("public", exist_ok=True)
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f)
    return stats

def format_size(num):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"

# ---- ASYNC ՀԱՎԱՔՈՂ ----
class HyperCollector:
    def __init__(self, conn):
        self.conn = conn
        self.session = None
        self.found = set()
        self.lock = asyncio.Lock()

    async def init(self):
        conn = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=30)
        self.session = aiohttp.ClientSession(connector=conn)

    async def close(self):
        await self.session.close()

    async def fetch(self, url):
        try:
            async with self.session.get(url, timeout=5, headers={"User-Agent": "AWEC/3.0"}) as resp:
                if resp.status == 200 and 'text/html' in resp.content_type:
                    return await resp.text()
        except:
            pass
        return None

    def extract(self, html):
        links = set(RE_URL.findall(html))
        # also bs4
        soup = BeautifulSoup(html, 'lxml')
        for tag in soup.find_all(['a', 'link', 'script', 'img', 'source', 'iframe']):
            for attr in ['href', 'src', 'data-src']:
                val = tag.get(attr)
                if val and '://' in val:
                    links.add(val)
        return links

    async def process_url(self, url):
        html = await self.fetch(url)
        if html:
            links = self.extract(html)
            async with self.lock:
                self.found.update(links)

    async def process_seeds(self, urls):
        tasks = [self.process_url(u) for u in urls]
        await asyncio.gather(*tasks)

    async def run_burst(self, seed_list):
        await self.init()
        await self.process_seeds(seed_list)
        await self.close()
        return self.found

# ---- ԱՐԽԻՎԱՑՈՒՄ Archive.org ----
def archive_daily(conn):
    if not IA_ACCESS or not IA_SECRET:
        print("⚠️ IA keys missing, skip archive")
        return
    urls = [row[0] for row in conn.execute("SELECT url FROM links")]
    if not urls:
        return
    content = "\n".join(urls)
    gz_data = gzip.compress(content.encode())
    date_str = datetime.now().strftime("%Y-%m-%d")
    item_id = f"awec-daily-{date_str}-{random.randint(1000,9999)}"
    ia_session = ia.configure(access_key=IA_ACCESS, secret_key=IA_SECRET)
    ia_session.upload(
        item_id,
        file_objects=[BytesIO(gz_data)],
        file_names=[f"links_{date_str}.txt.gz"],
        metadata={
            "collection": "awec_links_awe_o.s",
            "title": f"AWEC Daily Dump {date_str}",
            "creator": "AWEC-24/7",
            "date": date_str
        },
        request_kwargs={'timeout': 60}
    )
    print(f"✅ Archived {len(urls)} links to {item_id}")

# ---- MAIN LOOP ----
async def main():
    conn = init_db()
    collector = HyperCollector(conn)
    cycle_start = datetime.utcnow()
    deadline = cycle_start + timedelta(hours=6)

    while datetime.utcnow() < deadline:
        print(f"🔁 New 25-min burst at {datetime.utcnow().strftime('%H:%M:%S')}")
        found = await collector.run_burst(SEED_URLS)
        if found:
            new = add_links(conn, found)
            print(f"   ➕ {new} new links (total {count_links(conn)})")
        else:
            print("   ⚠️ no links found")

        update_stats(conn)

        # Ստուգել՝ արդյոք մոտենում է 23:55, եթե այո՝ արքիվացնել
        now = datetime.utcnow()
        if now.hour == 23 and now.minute >= 55:
            print("⏰ Daily archive trigger")
            archive_daily(conn)

        # Քնել 30 վայրկյան, բայց միայն եթե դեռ ժամանակ կա
        if datetime.utcnow() + timedelta(seconds=SLEEP_SECONDS) < deadline:
            await asyncio.sleep(SLEEP_SECONDS)
        else:
            break

    conn.close()
    print("🛑 6-hour cycle finished.")

if __name__ == "__main__":
    asyncio.run(main())
