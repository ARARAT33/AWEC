#!/usr/bin/env python3
"""
AWEC – Matrix-aware harvester with checkpoint & YAML integration.
Usage:
    python collector_247.py --db <path> --shard-index <N> --total-shards <M>
"""

import argparse
import asyncio
import aiohttp
import json
import os
import re
import shutil
import signal
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

# ── Constants ─────────────────────────────────────────────
LINK_PATTERN = re.compile(r'https?://[^\s<>"\'+]+', re.IGNORECASE)
LOG_DIR = Path("logs")
CHECKPOINT_DIR = Path("checkpoints")          # YAML-ը կօգտագործի այս թղթապանակը
CHECKPOINT_JSON = "harvester_checkpoint.json"
CHECKPOINT_DB_COPY = "links.db"               # կպատճենվի checkpoint/links.db

# ── Configurable defaults (env) ──────────────────────────
WORKER_COUNT = int(os.getenv("CRAWLER_MAX_CONCURRENT", 180))
BATCH_SIZE = int(os.getenv("CRAWLER_BATCH_SIZE", 5000))
QUEUE_LIMIT = int(os.getenv("CRAWLER_QUEUE_LIMIT", 100000))
CHECKPOINT_INTERVAL = int(os.getenv("CHECKPOINT_INTERVAL_SEC", 300))

LOG_DIR.mkdir(exist_ok=True)

def log(msg: str) -> None:
    t = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=4))).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{t} [AWEC] {msg}"
    print(line)
    sys.stdout.flush()
    with open(LOG_DIR / "crawler.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── Seed list ─────────────────────────────────────────────
SEEDS = [
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

def seeds_for_shard(shard_index: int, total_shards: int) -> List[str]:
    return [s for i, s in enumerate(SEEDS) if i % total_shards == shard_index]

# ═══════════════════════════════════════════════════════════
class ContinuousHarvester:
    def __init__(self, db_path: str, shard_index: int, total_shards: int):
        self.db_path = db_path
        self.shard_index = shard_index
        self.total_shards = total_shards
        self.db_conn: Optional[sqlite3.Connection] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.active = True
        self.total_saved = 0
        self.active_pool: List[str] = []
        self.processed_set: set = set()

    # ── Database ──────────────────────────────────────────
    def init_db(self) -> None:
        self.db_conn = sqlite3.connect(self.db_path)
        self.db_conn.execute("PRAGMA journal_mode=TRUNCATE")
        self.db_conn.execute("PRAGMA synchronous=NORMAL")
        self.db_conn.execute("PRAGMA cache_size=-500000")
        self.db_conn.execute("PRAGMA temp_store=MEMORY")
        self.db_conn.execute("CREATE TABLE IF NOT EXISTS urls (url TEXT PRIMARY KEY)")
        self.db_conn.commit()

    # ── Seed / warm‑up ────────────────────────────────────
    def seed(self) -> None:
        count = self.db_conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
        if count > 0:
            log(f"📚 DB has {count} URLs – loading last 5000 into queue…")
            cursor = self.db_conn.execute("SELECT url FROM urls ORDER BY rowid DESC LIMIT 5000")
            self.active_pool = [row[0] for row in cursor.fetchall()]
        my_seeds = seeds_for_shard(self.shard_index, self.total_shards)
        self.active_pool.extend(my_seeds)
        self.db_conn.executemany("INSERT OR IGNORE INTO urls (url) VALUES (?)", [(s,) for s in my_seeds])
        self.db_conn.commit()
        log(f"🌱 Shard {self.shard_index} – {len(my_seeds)} seeds, queue={len(self.active_pool)}")

    # ── Checkpoint ────────────────────────────────────────
    def save_checkpoint(self, copy_db: bool = True) -> None:
        """
        Պահպանում է JSON checkpoint-ը և, ցանկության դեպքում, պատճենում DB-ն
        checkpoint/links.db, որպեսզի YAML-ը կարողանա tar անել:
        """
        state = {
            "shard_index": self.shard_index,
            "total_shards": self.total_shards,
            "total_saved": self.total_saved,
            "queue": self.active_pool,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        CHECKPOINT_DIR.mkdir(exist_ok=True)
        # JSON
        with open(CHECKPOINT_DIR / CHECKPOINT_JSON, "w", encoding="utf-8") as f:
            json.dump(state, f)
        # DB copy
        if copy_db:
            try:
                # Ensure DB is committed
                self.db_conn.commit()
                shutil.copy2(self.db_path, CHECKPOINT_DIR / CHECKPOINT_DB_COPY)
                log(f"💾 Checkpoint written (DB + JSON) – queue {len(self.active_pool)}")
            except Exception as e:
                log(f"⚠️ Failed to copy DB for checkpoint: {e}")
        else:
            log(f"💾 Checkpoint JSON written – queue {len(self.active_pool)}")

    def load_checkpoint(self) -> bool:
        json_path = CHECKPOINT_DIR / CHECKPOINT_JSON
        db_copy = CHECKPOINT_DIR / CHECKPOINT_DB_COPY
        if json_path.exists() and db_copy.exists():
            try:
                # Restore DB
                shutil.copy2(db_copy, self.db_path)
                self.db_conn.close()
                self.init_db()
                with open(json_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                self.total_saved = state["total_saved"]
                self.active_pool = state["queue"]
                log(f"🔄 Checkpoint restored – queue size {len(self.active_pool)}")
                return True
            except Exception as e:
                log(f"⚠️ Failed to load checkpoint: {e}")
        return False

    # ── Worker ────────────────────────────────────────────
    async def worker(self) -> None:
        while True:
            if not self.active or not self.active_pool:
                await asyncio.sleep(0.05)
                continue
            url = self.active_pool.pop(0)
            if not url:
                continue
            try:
                async with self.session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        text = await resp.text(errors='ignore')
                        found = LINK_PATTERN.findall(text)
                        new_links = []
                        for link in found:
                            if (len(link) < 300 and
                                link.startswith(('http://', 'https://')) and
                                link not in self.processed_set):
                                new_links.append(link)
                                self.processed_set.add(link)
                        if new_links:
                            cursor = self.db_conn.cursor()
                            cursor.executemany(
                                "INSERT OR IGNORE INTO urls (url) VALUES (?)",
                                [(l,) for l in new_links]
                            )
                            self.db_conn.commit()
                            self.total_saved += cursor.rowcount
                            if len(self.active_pool) < QUEUE_LIMIT:
                                take = min(100, len(new_links))
                                self.active_pool.extend(new_links[:take])
            except (asyncio.TimeoutError, aiohttp.ClientError):
                pass
            except Exception as e:
                log(f"⚠️ Worker error on {url}: {type(e).__name__}: {e}")
                await asyncio.sleep(0.02)

    async def checkpoint_loop(self) -> None:
        while self.active:
            await asyncio.sleep(CHECKPOINT_INTERVAL)
            if self.active:
                self.save_checkpoint(copy_db=True)

    # ── Main runner ───────────────────────────────────────
    async def run(self) -> None:
        log(f"🚀 AWEC Harvester – Shard {self.shard_index}/{self.total_shards-1} (DB: {self.db_path})")
        self.init_db()

        if not self.load_checkpoint():
            self.seed()

        connector = aiohttp.TCPConnector(limit=300, force_close=True, ssl=False)
        self.session = aiohttp.ClientSession(connector=connector)

        workers = [asyncio.create_task(self.worker()) for _ in range(WORKER_COUNT)]
        ckpt_task = asyncio.create_task(self.checkpoint_loop())

        try:
            while self.active:
                await asyncio.sleep(2)
                if self.active:
                    db_count = self.db_conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
                    log(f"📊 [Shard {self.shard_index}] DB: {db_count} | Added: +{self.total_saved} | Queue: {len(self.active_pool)}")
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            log("🛑 Shutting down…")
            self.active = False
            ckpt_task.cancel()
            try:
                await ckpt_task
            except asyncio.CancelledError:
                pass
            for t in workers:
                t.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

            # Վերջնական checkpoint
            self.save_checkpoint(copy_db=True)
            self.db_conn.close()
            await self.session.close()
            log("✅ Harvester stopped cleanly")

# ── Signal handling ───────────────────────────────────────
def setup_signal_handler(harvester: ContinuousHarvester, loop):
    def handle():
        log("📢 Interrupt received – shutting down")
        harvester.active = False
        for task in asyncio.all_tasks(loop):
            task.cancel()
    try:
        loop.add_signal_handler(signal.SIGINT, handle)
        loop.add_signal_handler(signal.SIGTERM, handle)
    except NotImplementedError:
        signal.signal(signal.SIGINT, lambda s, f: handle())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--total-shards", type=int, required=True)
    args = parser.parse_args()

    if not (0 <= args.shard_index < args.total_shards):
        sys.exit("❌ Invalid shard index")

    harvester = ContinuousHarvester(args.db, args.shard_index, args.total_shards)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    setup_signal_handler(harvester, loop)
    try:
        loop.run_until_complete(harvester.run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()

if __name__ == "__main__":
    main()
