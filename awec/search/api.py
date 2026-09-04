"""Search API with FTS5 ranking and multilingual/Armenian Unicode support."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from awec.storage.state_store import StateStore


class SearchAPI:
    def __init__(self, store: StateStore):
        self.store = store

    def search(self, query: str, domain: str = "", language: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        query_str = query.strip()
        if not query_str:
            return []

        # Sanitize FTS query for safety
        fts_query = f'"{query_str}"' if " " in query_str else query_str
        return self.store.search(fts_query, domain=domain, language=language, limit=limit)
