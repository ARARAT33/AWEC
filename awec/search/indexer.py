"""Search Indexer and Link Graph Manager for AWEC."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

from awec.storage.state_store import StateStore


class SearchIndexer:
    def __init__(self, store: StateStore):
        self.store = store

    @staticmethod
    def extract_text_and_metadata(html_content: str) -> Dict[str, str]:
        if not html_content:
            return {"title": "", "headings": "", "body_text": "", "description": "", "language": "en"}

        try:
            soup = BeautifulSoup(html_content, "lxml")
        except Exception:
            soup = BeautifulSoup(html_content, "html.parser")

        # Remove scripts & styles
        for s in soup(["script", "style", "noscript"]):
            s.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else ""

        # Language
        html_tag = soup.find("html")
        lang = html_tag.get("lang", "").strip().lower() if html_tag and html_tag.get("lang") else ""
        if not lang:
            # Simple Armenian script detection
            if re.search(r"[\u0531-\u058F]", html_content):
                lang = "hy"
            elif re.search(r"[\u0400-\u04FF]", html_content):
                lang = "ru"
            else:
                lang = "en"

        # Headings
        headings = " ".join([h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3", "h4"])])

        # Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        description = meta_desc.get("content", "").strip() if meta_desc and meta_desc.get("content") else ""

        # Body text
        body_text = soup.get_text(separator=" ", strip=True)

        return {
            "title": title,
            "headings": headings,
            "body_text": body_text[:500000],  # Bounded memory
            "description": description,
            "language": lang
        }

    def index_resource(self, resource_id: str, url: str, domain: str, html_content: str) -> None:
        meta = self.extract_text_and_metadata(html_content)
        self.store.index_search_doc(
            resource_id=resource_id,
            url=url,
            title=meta["title"],
            headings=meta["headings"],
            body_text=meta["body_text"],
            description=meta["description"],
            domain=domain,
            language=meta["language"]
        )


class LinkGraphManager:
    def __init__(self, store: StateStore):
        self.store = store

    def add_edge(self, source_url: str, target_url: str, discovery_type: str, crawl_id: str, relationship_type: str = "link") -> None:
        self.store.add_link_edge(
            source_url=source_url,
            target_url=target_url,
            discovery_type=discovery_type,
            crawl_id=crawl_id,
            relationship_type=relationship_type
        )
