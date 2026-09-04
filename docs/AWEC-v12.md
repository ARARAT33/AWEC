# AWEC v12

AWEC v12 is the liquid-glass desktop command center for reachable-resource web archiving.

## Crawl pipeline

1. Validate the configured Internet Archive collection/item.
2. Crawl the seed and recursively discover reachable HTML, CSS, JS, media, forms and embedded URLs.
3. Stage response bytes in the user-selected `TMPCRAWL` directory.
4. Persist frontier, resource metadata, WARC offsets and link graph in SQLite.
5. Publish each successful resource to the configured Internet Archive item immediately when live publishing is enabled.
6. Optionally verify the remote object size.
7. Optionally purge the local payload after verified upload.

## Storage safety

`TMPCRAWL` has a user-selected size limit. `0` means no AWEC software quota, but AWEC always keeps a configurable free-disk reserve. The physical maximum remains the available storage and filesystem limits.

## Resume

The frontier is durable. On restart, interrupted `in_progress` URLs are returned to `pending`. The desktop Resume Center discovers crawl sessions with unfinished frontier work and lets the user continue them.

## Archive Explorer

The desktop explorer shows the local downloaded resource tree, previews HTML/text resources, and opens the configured Internet Archive item in the browser.

## Network/FANTI

FANTI provides adaptive request behavior, host memory, retries, jitter, connection management and configurable headers. AWEC does not attempt to defeat authentication, CAPTCHA, paywalls, robots restrictions or other access controls.
