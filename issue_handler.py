import os, re, sqlite3, requests

RE_URL = re.compile(r'(?:https?|ftp|magnet|ipfs)://[^\s<>"\'{}|\\^`\[\]]+|'
                    r'\b[a-z2-7]{16,56}\.onion\b|magnet:\?[^\s]+', re.I)

body = os.getenv("ISSUE_BODY", "")
conn = sqlite3.connect("links.db")
conn.execute("CREATE TABLE IF NOT EXISTS links (url TEXT PRIMARY KEY, added TEXT)")

links = set(RE_URL.findall(body))
new = 0
now = __import__('datetime').datetime.utcnow().isoformat()
for url in links:
    try:
        conn.execute("INSERT OR IGNORE INTO links(url,added) VALUES(?,?)", (url.strip(), now))
        if conn.total_changes > 0:
            new += 1
    except:
        pass
conn.commit()
conn.close()
print(f"Added {new} links from issue.")
