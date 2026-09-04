from pathlib import Path
import tempfile

from awec.discovery.parsers import ContentExtractor
from awec.storage.state_store import StateStore
from desktop.crawler_engine_v12 import find_resumable_crawls


def test_html_discovers_embedded_and_media_resources():
    html='''<html><link rel="stylesheet" href="/app.css"><script src="/app.js"></script><img src="/hero.webp"><iframe src="/frame"></iframe><a href="/docs/page">docs</a><script>fetch("/api/data.json")</script></html>'''
    found=ContentExtractor.extract_html_links('https://example.com/',html)
    urls={x[0] for x in found}
    assert 'https://example.com/app.css' in urls
    assert 'https://example.com/app.js' in urls
    assert 'https://example.com/hero.webp' in urls
    assert 'https://example.com/frame' in urls
    assert 'https://example.com/docs/page' in urls
    assert 'https://example.com/api/data.json' in urls


def test_interrupted_frontier_is_recoverable():
    with tempfile.TemporaryDirectory() as d:
        store=StateStore(Path(d)/'state.db')
        with store.lock, store._get_conn() as conn:
            conn.execute("INSERT INTO frontier(url,canonical_url,domain,depth,status,created_at) VALUES (?,?,?,?,?,datetime('now'))",('https://example.com/a','https://example.com/a','example.com',0,'in_progress'))
            conn.commit()
        assert store.recover_interrupted_frontier()==1
        assert store.frontier_counts()['pending']==1


def test_find_resumable_crawls():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d); crawl=root/'crawls'/'crawl-test'; crawl.mkdir(parents=True)
        store=StateStore(crawl/'state.db')
        with store.lock, store._get_conn() as conn:
            conn.execute("INSERT INTO frontier(url,canonical_url,domain,depth,status,created_at) VALUES (?,?,?,?,?,datetime('now'))",('https://example.com/a','https://example.com/a','example.com',0,'pending'))
            conn.commit()
        rows=find_resumable_crawls(root)
        assert rows and rows[0]['crawl_id']=='crawl-test'
