"""Content Discovery and Resource Extraction Parsers for HTML, CSS, JS, Sitemap, Feeds."""
from __future__ import annotations

import gzip
import re
import xml.etree.ElementTree as ET
from typing import List, Set, Tuple
from urllib.parse import urljoin
from bs4 import BeautifulSoup

URL_REGEX = re.compile(r"https?://[^\s<>\"'`{}|\\^]+", re.I)
CSS_URL_REGEX = re.compile(r"url\s*\(\s*['\"]?([^'\"()]+)['\"]?\s*\)", re.I)
JS_URL_REGEX = re.compile(r"['\"]((?:https?://|/|\.\./)[a-zA-Z0-9_\-/.?=&%#]+)['\"]", re.I)


class ContentExtractor:
    @staticmethod
    def extract_html_links(base_url: str, html_content: str) -> List[Tuple[str, str, str]]:
        """Returns list of (absolute_url, discovery_type, mime_hint)"""
        results: List[Tuple[str, str, str]] = []
        try:
            soup = BeautifulSoup(html_content, "lxml")
        except Exception:
            soup = BeautifulSoup(html_content, "html.parser")

        # <base href="...">
        base_tag = soup.find("base", href=True)
        if base_tag:
            base_url = urljoin(base_url, base_tag["href"])

        # <a href>, <area href>
        for tag in soup.find_all(["a", "area"], href=True):
            href = tag["href"].strip()
            if href and not href.startswith(("javascript:", "mailto:", "tel:", "#")):
                results.append((urljoin(base_url, href), "html_link", "text/html"))

        # <img src>, <img srcset>
        for img in soup.find_all("img"):
            if img.get("src"):
                results.append((urljoin(base_url, img["src"].strip()), "image", "image/*"))
            if img.get("srcset"):
                for part in img["srcset"].split(","):
                    u = part.strip().split()[0]
                    if u:
                        results.append((urljoin(base_url, u), "image", "image/*"))

        # <script src>
        for sc in soup.find_all("script", src=True):
            results.append((urljoin(base_url, sc["src"].strip()), "script", "application/javascript"))

        # <link href>
        for link in soup.find_all("link", href=True):
            rel = " ".join(link.get("rel", [])).lower()
            u = urljoin(base_url, link["href"].strip())
            if "stylesheet" in rel:
                results.append((u, "stylesheet", "text/css"))
            elif "icon" in rel:
                results.append((u, "icon", "image/*"))
            elif "canonical" in rel:
                results.append((u, "canonical", "text/html"))
            elif "alternate" in rel:
                type_attr = link.get("type", "").lower()
                if "rss" in type_attr or "atom" in type_attr or "json" in type_attr:
                    results.append((u, "feed", type_attr))
                else:
                    results.append((u, "alternate", ""))
            else:
                results.append((u, "html_link", ""))

        # <source src>, <video src>, <audio src>, <iframe src>
        for media in soup.find_all(["source", "video", "audio", "iframe", "embed", "object"]):
            src = media.get("src") or media.get("data")
            if src:
                results.append((urljoin(base_url, src.strip()), "media", ""))

        return results

    @staticmethod
    def extract_css_links(base_url: str, css_content: str) -> List[Tuple[str, str, str]]:
        results: List[Tuple[str, str, str]] = []
        for match in CSS_URL_REGEX.finditer(css_content):
            raw = match.group(1).strip()
            if raw and not raw.startswith(("data:", "about:", "#")):
                results.append((urljoin(base_url, raw), "css_resource", ""))
        return results

    @staticmethod
    def extract_js_links(base_url: str, js_content: str) -> List[Tuple[str, str, str]]:
        results: List[Tuple[str, str, str]] = []
        for match in JS_URL_REGEX.finditer(js_content):
            raw = match.group(1).strip()
            if raw and len(raw) > 3 and not raw.startswith("data:"):
                results.append((urljoin(base_url, raw), "js_literal", ""))
        return results

    @staticmethod
    def parse_feed(feed_content: str, base_url: str) -> List[Tuple[str, str, str]]:
        """Parses RSS, Atom, or JSON Feed and returns (url, discovery_type, title)"""
        results: List[Tuple[str, str, str]] = []
        try:
            root = ET.fromstring(feed_content)
            # RSS
            for item in root.findall(".//item"):
                link_elem = item.find("link")
                title_elem = item.find("title")
                if link_elem is not None and link_elem.text:
                    u = urljoin(base_url, link_elem.text.strip())
                    t = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                    results.append((u, "feed_entry", t))

            # Atom
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"
            for entry in root.findall(f".//{ns}entry"):
                title_elem = entry.find(f"{ns}title")
                t = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                for link in entry.findall(f"{ns}link"):
                    href = link.get("href")
                    if href:
                        results.append((urljoin(base_url, href.strip()), "feed_entry", t))
        except Exception:
            pass
        return results

    @staticmethod
    def parse_sitemap(sitemap_bytes: bytes, is_gzipped: bool = False) -> List[str]:
        urls: List[str] = []
        try:
            content = gzip.decompress(sitemap_bytes) if is_gzipped else sitemap_bytes
            root = ET.fromstring(content)
            # Handle default namespace
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"

            # Sitemap Index or Urlset
            for elem in root.findall(f".//{ns}loc"):
                if elem.text and elem.text.strip():
                    urls.append(elem.text.strip())
        except Exception:
            pass
        return urls


class BrowserRenderer:
    """Optional isolated browser rendering engine (disabled by default)."""

    def __init__(self, timeout_sec: float = 30.0, max_tabs: int = 2):
        self.timeout_sec = timeout_sec
        self.max_tabs = max_tabs

    async def render_page(self, url: str) -> Tuple[str, List[Tuple[str, str, str]]]:
        """Renders page using Playwright if available, otherwise returns empty."""
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, timeout=int(self.timeout_sec * 1000))
                content = await page.content()
                await browser.close()
                links = ContentExtractor.extract_html_links(url, content)
                return content, links
        except Exception:
            return "", []
