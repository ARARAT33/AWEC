# AWEC Desktop UI

## Dashboard
- Status badge: AWEC Running / Paused / Stopped
- Current domain and crawl item identifier
- Pages scanned, files found, files downloaded
- Downloaded bytes / total limit
- Current speed, queue size, workers, errors, HTTP 429/503 counters
- Per-domain progress and overall progress
- Live event log

## Crawler
- Seed URL list
- Import TXT, JSON, DOCX
- Follow links
- Follow subdomains
- Follow external domains
- Download discovered files
- Respect robots.txt
- Maximum depth (-1 = unlimited)
- Maximum individual file size (-1 = unlimited)
- Maximum total download size (-1 = unlimited)
- File types: explicit extensions or * for all supported discovered types
- Workers
- Requests/second per host
- Retry count and delays
- Pause / Resume / Stop

## Storage
- Internet Archive
- Local PC folder
- Both
- Checkpoint location
- Archive item naming: domain-DD-MM-YYYY-awec

## Languages
- English base language
- Armenian, Russian, Spanish, French, German, Portuguese, Italian, Chinese, Japanese built-in packs
- Custom .awec.language import
- Visual language editor: edit every UI key, preview button labels, rename language, save/export pack

## Compliance
AWEC uses robots-aware crawling, bounded rate limiting, retry/backoff and transparent user-agent identification. It does not bypass WAFs, evade bot detection, rotate identities to defeat blocking, or circumvent access controls.
