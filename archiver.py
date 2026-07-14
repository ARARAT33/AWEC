import os, gzip, random
from datetime import datetime
import internetarchive as ia

IA_ACCESS = os.getenv("IA_ACCESS_KEY")
IA_SECRET = os.getenv("IA_SECRET_KEY")
MASTER = "TMPLinks/daily_master.txt"

def upload():
    if not IA_ACCESS or not IA_SECRET:
        print("⚠️ No IA keys")
        return

    if not os.path.exists(MASTER):
        return

    with open(MASTER, 'r') as f:
        content = f.read()
    if not content.strip():
        return

    compressed = gzip.compress(content.encode())
    item_id = f"awec-hyper-{datetime.now().strftime('%Y%m%d%H%M')}-{random.randint(1000,9999)}"
    ia_session = ia.configure(access_key=IA_ACCESS, secret_key=IA_SECRET)

    meta = {
        "collection": "awec_links_awe_o.s",
        "mediatype": "texts",
        "title": f"AWEC Hyper Dump {datetime.now().isoformat()}",
        "creator": "AWEC-Bot-v3"
    }

    ia_session.upload(
        item_id,
        file_objects=[io.BytesIO(compressed)],
        file_names=["links.gz"],
        metadata=meta,
        request_kwargs={'timeout': 60}
    )
    print(f"✅ Uploaded to archive.org/details/{item_id}")

if __name__ == "__main__":
    upload()
