import os, glob, hashlib

RAW_DIR = "TMPLinks/raw"
MASTER = "TMPLinks/daily_master.txt"

def main():
    seen = set()
    # Կարդում ենք հին master-ը
    if os.path.exists(MASTER):
        with open(MASTER, 'r') as f:
            for line in f:
                seen.add(line.strip())

    # Մշակում ենք բոլոր raw batch-երը
    for fpath in glob.glob(os.path.join(RAW_DIR, "links_batch_*.txt")):
        with open(fpath, 'r') as f:
            for line in f:
                link = line.strip()
                if link and link not in seen:
                    seen.add(link)
        os.remove(fpath)   # մաքրում ենք batch-ը

    # Վերագրում ենք master-ը
    with open(MASTER, 'w') as f:
        f.write('\n'.join(sorted(seen)))

    print(f"📁 Master file: {len(seen)} unique links")

if __name__ == "__main__":
    main()
