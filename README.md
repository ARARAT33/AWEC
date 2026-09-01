# AWEC — Web Archive Engine

AWEC is a desktop-first recursive web crawler and Internet Archive dataset uploader.

## Desktop features

- English as the canonical UI language plus Armenian, Russian, Spanish, French, German, Portuguese, Italian, Chinese and Japanese.
- Custom `.awec.language` files and an in-app language editor so every visible label can be renamed.
- Add seed sites manually or import URLs from TXT, JSON, DOC and DOCX files.
- Recursive HTML link discovery with configurable workers, depth, URL count and per-host delay.
- Select file extensions or `*` for all supported content; file-size limit supports `-1` for unlimited.
- Per-file global ID plus sanitized site/domain name in the archive object key.
- Global SQLite metadata index groups files by domain without storing downloaded bodies by default.
- Internet Archive S3 upload with retry/backoff. If IA is unavailable, downloaded bytes are saved to the user-selected fallback folder.
- Live dashboard for queue, fetched pages, discovered files, uploads, active workers and errors.
- Retry/backoff for transient network and archive errors.

## Important network behavior

AWEC identifies itself as AWEC, supports `robots.txt`, throttles requests per host and uses exponential backoff. It does **not** bypass Cloudflare/WAF controls, CAPTCHAs, IP blocks, robots restrictions, or disguise an automated client as a human. A remote site can therefore still reject a request; AWEC records the error and retries transient failures according to the configured policy.

## Run

```bash
cd desktop
python -m pip install -r requirements.txt
python awec_desktop.py
```

## Internet Archive

Enter your IA S3 endpoint, access key, secret key, collection and identifier in the desktop UI. Credentials are held in memory for the run and are not written to the AWEC metadata database.

The local database stores crawl/file metadata only. File bodies are kept locally only when an IA upload cannot be completed.

## Custom language

A custom language is a UTF-8 JSON file with the `.awec.language` extension. Start with `desktop/languages/example.awec.language`, import it in the Language tab, then edit any label you want.

## Archive object layout

```text
files/<site-name>/<global-id>_<filename>
```

This makes each archived file traceable to its source domain and unique global ID. The SQLite metadata index also stores the domain, source URL, filename, content type, size and IA object key.
