# AWEC Desktop

AWEC Desktop is a local GUI for recursive web URL discovery and Internet Archive dataset publishing.

## Features

- Add any number of seed sites from the **Sites** tab.
- Recursive HTTP/HTTPS link discovery with configurable depth and URL limit.
- Async workers with per-host throttling.
- Optional `robots.txt` compliance (enabled by default).
- SQLite WAL database for the local index.
- JSONL dataset chunking so results become independent archive files while crawling continues.
- Direct Internet Archive S3-compatible uploads when S3 credentials are configured.
- Internet Archive metadata update for collection, creator, title, description and subject.
- Optional HTML snapshots; disabled by default.
- Live queue/fetch/save/failure counters.

## Run

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r desktop/requirements.txt
python desktop/awec_desktop.py
```

## Internet Archive

Set the IA item identifier and S3 access/secret keys in the GUI. The default S3 endpoint is `https://s3.us.archive.org`.

`IA collection` is written to item metadata; it is not a credential. The item identifier must be unique in Internet Archive. Do not commit S3 credentials to GitHub.

## Crawl model

```text
Seed sites
   -> fetch
   -> parse HTML href/src + absolute URLs
   -> normalize/deduplicate
   -> queue newly discovered URLs
   -> repeat until queue drains or URL/depth limits are reached
   -> write JSONL chunk
   -> upload chunk to Internet Archive
```

The application indexes URLs and response metadata. It does **not** silently mirror arbitrary page content. HTML capture is an explicit opt-in and should only be used for content you are authorized to archive.

## Important limits

"Scan everything" is bounded by the configured seeds, depth, URL limit, server availability, robots policy, rate limits and network conditions. The app does not attempt to crawl the entire Internet by default.
