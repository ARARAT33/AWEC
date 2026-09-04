"""High-coverage HTML/CSS/JS/sitemap/feed resource discovery."""
from __future__ import annotations
import gzip,re,xml.etree.ElementTree as ET
from typing import List,Tuple
from urllib.parse import urljoin
from bs4 import BeautifulSoup

URL_REGEX=re.compile(r"https?://[^\s<>\"'`{}|\\^]+",re.I)
CSS_URL_REGEX=re.compile(r"url\s*\(\s*['\"]?([^'\"()]+)['\"]?\s*\)",re.I)
JS_URL_REGEX=re.compile(r"['\"]((?:https?://|/|\.\./|\./)[^'\"\s<>]+)['\"]",re.I)

def _clean(u):
    return u.strip().rstrip('.,;:)]') if u else ''

class ContentExtractor:
    @staticmethod
    def extract_html_links(base_url:str,html_content:str)->List[Tuple[str,str,str]]:
        results=[]; seen=set()
        try:soup=BeautifulSoup(html_content,'lxml')
        except Exception:soup=BeautifulSoup(html_content,'html.parser')
        base=soup.find('base',href=True)
        if base: base_url=urljoin(base_url,base['href'])
        def add(raw,kind,mime=''):
            u=_clean(urljoin(base_url,str(raw)))
            if not u or u.startswith(('javascript:','mailto:','tel:','data:','blob:','#')):return
            if u not in seen:seen.add(u);results.append((u,kind,mime))
        for tag in soup.find_all(['a','area','link'],href=True):
            href=tag.get('href','').strip(); rel=' '.join(tag.get('rel',[])).lower(); typ=tag.get('type','').lower()
            if tag.name=='link':
                if 'stylesheet' in rel:add(href,'stylesheet','text/css')
                elif 'icon' in rel:add(href,'icon','image/*')
                elif 'alternate' in rel and ('rss' in typ or 'atom' in typ or 'json' in typ):add(href,'feed',typ)
                else:add(href,'html_link','text/html')
            else:add(href,'html_link','text/html')
        for tag,attr,kind,mime in [('img','src','image','image/*'),('script','src','script','application/javascript'),('iframe','src','media','text/html'),('video','src','media','video/*'),('audio','src','media','audio/*'),('source','src','media','*'),('embed','src','media','*'),('object','data','media','*')]:
            for node in soup.find_all(tag):
                if node.get(attr):add(node[attr],kind,mime)
                if node.get('srcset'):
                    for part in node['srcset'].split(','): add(part.strip().split()[0],kind,mime)
        for node in soup.find_all(['form'],action=True):add(node['action'],'form','')
        for meta in soup.find_all('meta',content=True):
            if str(meta.get('http-equiv','')).lower()=='refresh':
                m=re.search(r'url\s*=\s*(.+)',meta.get('content',''),re.I)
                if m:add(m.group(1).strip(' \"\''),'meta_refresh','text/html')
        # Catch URLs in inline data, JSON-LD and framework-generated markup.
        for raw in URL_REGEX.findall(html_content):add(raw,'html_embedded','')
        return results
    @staticmethod
    def extract_css_links(base_url,css_content):
        out=[];seen=set()
        for m in CSS_URL_REGEX.finditer(css_content):
            raw=m.group(1).strip()
            if raw.startswith(('data:','about:','#')):continue
            u=_clean(urljoin(base_url,raw))
            if u and u not in seen:seen.add(u);out.append((u,'css_resource',''))
        return out
    @staticmethod
    def extract_js_links(base_url,js_content):
        out=[];seen=set()
        for raw in list(URL_REGEX.findall(js_content))+[m.group(1) for m in JS_URL_REGEX.finditer(js_content)]:
            u=_clean(urljoin(base_url,raw))
            if u and not u.startswith(('javascript:','data:','blob:')) and u not in seen:seen.add(u);out.append((u,'js_literal',''))
        return out
    @staticmethod
    def parse_feed(feed_content,base_url):
        out=[]
        try:
            root=ET.fromstring(feed_content); ns=root.tag.split('}')[0]+'}' if root.tag.startswith('{') else ''
            for item in root.findall('.//item'):
                e=item.find('link');t=item.find('title')
                if e is not None and e.text:out.append((urljoin(base_url,e.text.strip()),'feed_entry',t.text.strip() if t is not None and t.text else ''))
            for entry in root.findall(f'.//{ns}entry'):
                t=entry.find(f'{ns}title'); title=t.text.strip() if t is not None and t.text else ''
                for link in entry.findall(f'{ns}link'):
                    if link.get('href'):out.append((urljoin(base_url,link['href'].strip()),'feed_entry',title))
        except Exception:pass
        return out
    @staticmethod
    def parse_sitemap(sitemap_bytes,is_gzipped=False):
        try:
            root=ET.fromstring(gzip.decompress(sitemap_bytes) if is_gzipped else sitemap_bytes); ns=root.tag.split('}')[0]+'}' if root.tag.startswith('{') else ''
            return [e.text.strip() for e in root.findall(f'.//{ns}loc') if e.text and e.text.strip()]
        except Exception:return []

class BrowserRenderer:
    """Optional browser rendering for JS-generated pages; never bypasses access controls."""
    def __init__(self,timeout_sec=30,max_tabs=2):self.timeout_sec=timeout_sec;self.max_tabs=max_tabs
    async def render_page(self,url):
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser=await p.chromium.launch(headless=True);page=await browser.new_page()
                await page.goto(url,wait_until='networkidle',timeout=int(self.timeout_sec*1000));content=await page.content();await browser.close()
                return content,ContentExtractor.extract_html_links(url,content)
        except Exception:return '',[]
