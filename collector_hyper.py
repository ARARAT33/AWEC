#!/usr/bin/env python3
"""
AWEC Hyper Collector – asyncio + aiohttp + 50k links instantly
"""
import asyncio
import aiohttp
import aiofiles
import os
import re
import time
import random
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from datetime import datetime

# --- Կարգավորումներ ---
MAX_CONCURRENT = 200          # Միաժամանակյա 200+ հարցում
REQUEST_TIMEOUT = 4
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "curl/8.4.0",
    "AWEC-Hyper/3.0"
]
OUTPUT_FILE = "TMPLinks/raw/links_batch_{}.txt"
SEED_FILES_DIR = "TMPLinks/input"
BULK_URL_SOURCES = [
    "https://raw.githubusercontent.com/ARKBAN/arkban-urls/main/urls.txt",
    "https://commoncrawl.s3.amazonaws.com/crawl-data/CC-MAIN-2024-10/warc.paths.gz",
    # ... ավելացրեք ցանկացած մեծ URL ցուցակ
]

RE_URL = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+|magnet:\?[^\s]+|ipfs://[^\s]+|\.onion\b', re.I)

# --- Հավաքողի միջուկ ---
class HyperCollector:
    def __init__(self):
        self.session = None
        self.found_links = set()
        self.lock = asyncio.Lock()

    async def init_session(self):
        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=20)
        self.session = aiohttp.ClientSession(connector=connector)

    async def fetch_url(self, url):
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        try:
            async with self.session.get(url, timeout=REQUEST_TIMEOUT, headers=headers) as resp:
                if resp.status == 200 and 'text/html' in resp.content_type:
                    return await resp.text()
        except:
            pass
        return None

    def extract_links(self, html, source_url):
        links = set()
        # Regex-ով արագ
        for m in RE_URL.finditer(html):
            link = m.group(0).rstrip('.,;:)>')
            if len(link) > 5:
                links.add(link)
        # BeautifulSoup-ով ավելի խելացի (ոչ պարտադիր արագության համար)
        soup = BeautifulSoup(html, 'lxml')
        for tag in soup.find_all(['a', 'link', 'script', 'img', 'source', 'iframe']):
            for attr in ['href', 'src', 'data-src']:
                val = tag.get(attr)
                if val and (val.startswith('http') or '://' in val):
                    links.add(val)
        return links

    async def process_url(self, url, source="web"):
        html = await self.fetch_url(url)
        if html:
            links = self.extract_links(html, url)
            async with self.lock:
                self.found_links.update(links)

    async def process_seed_file(self, filepath):
        async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
            async for line in f:
                line = line.strip()
                if line.startswith('http'):
                    await self.process_url(line, source="seed")

    async def load_bulk_list(self, list_url):
        """Ներբեռնում ենք արտաքին մեծ ցուցակներ (կարող է ունենալ 100k+ URL)"""
        try:
            async with self.session.get(list_url, timeout=30) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    urls = RE_URL.findall(text)
                    for u in urls:
                        self.found_links.add(u.rstrip('.,;)>'))
        except:
            pass

    async def save_batch(self, batch_num):
        if self.found_links:
            fname = OUTPUT_FILE.format(batch_num)
            async with aiofiles.open(fname, 'w', encoding='utf-8') as f:
                await f.write('\n'.join(sorted(self.found_links)))
            return len(self.found_links)
        return 0

    async def run(self, batch=0):
        await self.init_session()
        start = time.time()
        tasks = []

        # 1. Մշակել user-ի input ֆայլերը (եթե կան)
        if os.path.isdir(SEED_FILES_DIR):
            for fname in os.listdir(SEED_FILES_DIR):
                if fname.endswith('.txt'):
                    tasks.append(self.process_seed_file(os.path.join(SEED_FILES_DIR, fname)))

        # 2. Բեռնել մեծ ցուցակներ (50k+ URL ակնթարթային)
        for bulk_url in BULK_URL_SOURCES:
            tasks.append(self.load_bulk_list(bulk_url))

        # 3. Զուգահեռ աշխատեցնել
        await asyncio.gather(*tasks)

        # 4. Պահպանել
        count = await self.save_batch(batch)
        elapsed = time.time() - start
        print(f"✅ Batch {batch}: {count} links in {elapsed:.1f}s")
        await self.session.close()
        return count

if __name__ == "__main__":
    collector = HyperCollector()
    asyncio.run(collector.run(batch=int(datetime.now().strftime("%H%M"))))
