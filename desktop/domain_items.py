from datetime import datetime, timezone
import re

def safe_domain(domain: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+','-',domain.lower()).strip('-')

def item_identifier(domain: str, when=None) -> str:
    when = when or datetime.now(timezone.utc)
    return f'{safe_domain(domain)}-{when:%d-%m-%Y}-awec'
