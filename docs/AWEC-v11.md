# AWEC v11

AWEC v11 is the desktop command-center generation of the archival crawler.

## Whole-program language switching

The existing 10 built-in languages remain intact: English, Armenian, Russian,
Spanish, French, German, Portuguese, Italian, Chinese and Japanese. The runtime
localization layer switches the visible application UI from the canonical English
catalog and then applies per-language user overrides. Custom `.awec.language` packs
and the v10 naming studio remain supported.

## Universal naming

Users can rename visible labels/buttons per language. Names persist locally and are
never mixed with IA/S3 credentials or other secrets.

## Complete reachable-resource mirroring

When `mirror_all_resources` is enabled (the v11 default), every successful response
that the crawler discovers in the configured scope is saved as a real local file and
also represented in the WARC archive. HTML resources discover links and first-class
assets; CSS discovers `url(...)` resources; JavaScript discovers literal URL references.

Each crawl gets:

- `site/` — deterministic host/path mirror
- `_awec_manifest.json` — URL, local path, status, MIME, size and SHA-256
- `WARC/` — archival response stream
- `state.db` — crawl state, resource records and search/index data

The crawler keeps same-origin/subdomain scoping unless explicitly configured otherwise.
It does not attempt to defeat authentication, CAPTCHA, paywalls, or other access controls.

## Adaptive network

FANTI remains the high-control network mode with per-host pacing, adaptive
concurrency, cookies, retries, circuit breaking, TLS controls and configurable headers.
These controls are for reliable archival retrieval and respectful handling of throttling,
not for bypassing access controls.

## UI

v11 adds a premium command-center hero, mirror telemetry cards, storage quick action,
whole-program language switching and refreshed dark glass styling.
