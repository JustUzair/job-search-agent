from __future__ import annotations

import os

from .base import DiscoveryPlugin
from .url_utils import normalize_url

try:
    from .. import scraper
except ImportError:
    import scraper


class DDGOptionalDiscovery(DiscoveryPlugin):
    def __init__(self):
        enabled = os.environ.get("ENABLE_DDG_SEARCH", "false").lower() in ("1", "true", "yes")
        super().__init__(name="ddg_optional", enabled=enabled)

    def discover(self, campaign: dict, limit: int = 50) -> list[dict]:
        if not self.enabled:
            return []
        items = []
        seen = set()
        for query in campaign.get("search_queries", []):
            for url in scraper._ddg_search(query, max_results=10):
                normalized = normalize_url(url)
                canonical = normalized["canonical_url"]
                if not canonical or canonical in seen:
                    continue
                seen.add(canonical)
                items.append(
                    {
                        "url": url,
                        "original_url": normalized["original_url"],
                        "canonical_url": canonical,
                        "title": "",
                        "company": "",
                        "snippet": "",
                        "source": self.name,
                        "query": query,
                        "confidence": 0.5,
                        "metadata": {},
                    }
                )
                if len(items) >= limit:
                    return items
        return items
