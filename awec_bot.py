import os
import re
import time
import random
import requests
import internetarchive as ia
from datetime import datetime
from io import BytesIO
import gzip

# --- ԿԱՐԳԱՎՈՐՈՒՄՆԵՐ ---
IA_ACCESS = os.getenv("IA_ACCESS_KEY")
IA_SECRET = os.getenv("IA_SECRET_KEY")
COLLECTION_ID = "awec_links_awe_o.s"
LINKS_FILE = "TMPLinks/daily_links.txt"
TODAY_DATE = datetime.now().strftime("%d-%m-%Y")

# --- AWEC 100+ ԿԱՏԵԳՈՐԻԱՆԵՐԻ REGEX ---
# Սա հավաքում է ամեն ինչ՝ սովորական հղումներից մինչև Dark Web և API endpoints
PATTERNS = [
    r'\b(?:https?|ftp|ftps|ssh|git|svn|ws|wss|mailto|tel|ldap|rtsp|magnet):\/\/[^\s<>"{}|\\^`\[\]]+',
    r'\b[a-zA-Z0-9.-]+\.(com|org|net|am|ru|io|onion|eth|crypto|xyz|top|info|biz|gov|edu)[^\s<>"{}|\\^`\[\]]*',
    r'\bipfs://[a-zA-Z0-9]+\b',
    r'\b[a-z2-7]{16}\.onion\b',
    r'\bmagnet:\?xt=urn:btih:[a-zA-Z0-9]+\b',
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', # Emails
    r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?\b' # IPs
]
COMBINED_REGEX = re.compile("|".join(PATTERNS), re.IGNORECASE)

def get_user_agents():
    return [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15',
        'curl/7.68.0'
    ]

def extract_from_text(text):
    found = set()
    matches = COMBINED_REGEX.findall(text)
    for match in matches:
        # Մաքրում ենք վերջին կետերը և փակագծերը
        clean = match.rstrip('.,;:)]}>')
        if len(clean) > 5:
            found.add(clean)
    return found

def load_existing_links():
    if not os.path.exists(LINKS_FILE):
        return set()
    with open(LINKS_FILE, 'r', encoding='utf-8', errors='ignore') as f:
        return set(line.strip() for line in f if line.strip())

def save_links(links_set):
    with open(LINKS_FILE, 'w', encoding='utf-8') as f:
        for link in sorted(links_set):
            f.write(link + '\n')

def upload_to_archive(content_text, filename_base):
    if not IA_ACCESS or not IA_SECRET:
        print("⚠️ Archive.org keys missing. Skipping upload.")
        return

    try:
        # Սեղմում GZIP
        buffer = BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode='wb', mtime=0) as gz:
            gz.write(content_text.encode('utf-8'))
        
        compressed_data = buffer.getvalue()
        item_id = f"awec-{filename_base}-{random.randint(1000,9999)}"
        
        print(f"🚀 Սկսում եմ ուղարկել {item_id} ({len(compressed_data)} bytes)...")

        ia_session = ia.configure(access_key=IA_ACCESS, secret_key=IA_SECRET)
        
        metadata = {
            "collection": COLLECTION_ID,
            "mediatype": "texts",
            "title": f"AWEC Daily Dump {filename_base}",
            "description": f"Automated collection of {len(content_text.splitlines())} links by AWEC Spider.",
            "creator": "AWEC_Bot_GitHub_Actions",
            "date": datetime.now().isoformat()
        }

        response = ia_session.upload(
            item_id,
            file_objects=[BytesIO(compressed_data)],
            file_names=[f"{filename_base}.links.gz"],
            metadata=metadata,
            request_kwargs={'timeout': 30}
        )
        print(f"✅ Հաջողությամբ ուղարկվեց: https://archive.org/details/{item_id}")
        return True
    except Exception as e:
        print(f"❌ Upload սխալ: {e}")
        return False

def main():
    print("🕷️ AWEC Bot started...")
    
    # 1. Բեռնել հին հղումները
    all_links = load_existing_links()
    initial_count = len(all_links)
    
    # 2. Սկանավորել նոր աղբյուրներ (Simulated Web Crawling & Input Processing)
    # Սա կարող է ընդլայնվել՝ ավելացնելով իրական URL-երի ցանկ, որոնք պետք է սկանավորել
    new_links_found = set()
    
    # Օրինակ՝ սկանավորում ենք պատահական հայտնի էջերից կամ RSS-ներից (Demo logic)
    # Իրական նախագծում այստեղ կարող եք ավելացնել ձեր սպեցիֆիկ target-ները
    demo_sources = [
        "https://www.wikipedia.org/",
        "https://github.com/trending",
        "https://news.ycombinator.com/"
    ]
    
    headers = {'User-Agent': random.choice(get_user_agents())}
    
    for url in demo_sources:
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                found = extract_from_text(resp.text)
                new_links_found.update(found)
        except:
            pass

    # Միավորել նորը և հինը
    original_len = len(all_links)
    all_links.update(new_links_found)
    added_count = len(all_links) - original_len
    
    if added_count > 0:
        print(f"✨ Գտնվեց և ավելացվեց {added_count} նոր հղում:")
        save_links(all_links)
    else:
        print("ℹ️ Նոր հղումներ չեն գտնվել այս ցիկլում:")

    # 3. Ստուգել ժամանակը Archive.org ուղարկելու համար
    now = datetime.now()
    # Եթե ժամը 23:55 է կամ անցել է, և դեռ չի ուղարկվել այսօրվա ֆայլը
    # Պարզեցնելու համար՝ եթե րոպեն 55-59 է, փորձում ենք ուղարկել
    
    if now.hour == 23 and 55 <= now.minute <= 59:
        print("⏰ Ժամանակն է օրվա արխիվը սեղմել և ուղարկել...")
        
        if len(all_links) > 0:
            content = "\n".join(sorted(all_links))
            filename_base = f"{TODAY_DATE}-count-{len(all_links)}"
            
            success = upload_to_archive(content, filename_base)
            
            if success:
                # Հաջող ուղարկումից հետո կարող ենք մաքրել ֆայլը կամ պահել որպես բեքափ
                # Այստեղ մենք պահում ենք, բայց կարող եք ջնջել՝ save_links(set())
                print("🧹 Օրվա առաքելությունը կատարված է:")
        else:
            print("⚠️ Ֆայլը դատարկ է, ուղարկում չկա:")
    
    print(f"📊 Ընդհանուր հղումների քանակը: {len(all_links)}")

if __name__ == "__main__":
    main()
