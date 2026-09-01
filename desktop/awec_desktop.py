#!/usr/bin/env python3
"""AWEC Desktop 3.0 - multilingual recursive web archive client.

This application crawls configured seed sites, discovers same-page URLs,
optionally downloads selected file types, and sends file bytes directly to
Internet Archive S3 when credentials are configured. Only metadata is kept in
the local SQLite index by default; downloaded bodies are written locally only
when the configured IA upload is unavailable.

The client uses explicit AWEC identification, robots.txt support, per-host
throttling and exponential backoff. It deliberately does not bypass WAFs,
CAPTCHAs, IP blocks, Cloudflare controls, or pretend to be a human.
"""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
import boto3
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (QApplication,QCheckBox,QComboBox,QDoubleSpinBox,
 QFileDialog,QFormLayout,QGridLayout,QGroupBox,QHBoxLayout,QLabel,QLineEdit,
 QListWidget,QMainWindow,QMessageBox,QPlainTextEdit,QPushButton,QSpinBox,
 QTabWidget,QVBoxLayout,QWidget)

try:
    from docx import Document
except Exception:
    Document = None

APP_DIR = Path.home() / "AWEC"
LANG_DIR = Path(__file__).resolve().parent / "languages"
URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.I)
HREF_RE = re.compile(r"(?:href|src)\s*=\s*['\"]([^'\"]+)['\"]", re.I)

# English is the canonical language. The other nine are built-in translations.
LANGS = {
 "English":{"code":"en","start":"Start","stop":"Stop","settings":"Settings","sites":"Sites","files":"Files","dashboard":"Dashboard","language":"Language","add":"Add","remove":"Remove","import":"Import","save":"Save","collection":"IA Collection","identifier":"IA Identifier","creator":"Creator","workers":"Workers","depth":"Max depth","max_urls":"Max URLs (0 = unlimited)","delay":"Per-host delay (sec)","max_file":"Max file size (bytes; -1 = unlimited)","extensions":"File extensions","fallback":"Fallback folder","robots":"Respect robots.txt","download":"Download matching files","custom":"Custom","logs":"Logs"},
 "Հայերեն":{"code":"hy","start":"Սկսել","stop":"Կանգնեցնել","settings":"Կարգավորումներ","sites":"Կայքեր","files":"Ֆայլեր","dashboard":"Վահանակ","language":"Լեզու","add":"Ավելացնել","remove":"Հեռացնել","import":"Ներմուծել","save":"Պահել","collection":"IA Collection","identifier":"IA Identifier","creator":"Ստեղծող","workers":"Աշխատողներ","depth":"Առավելագույն խորություն","max_urls":"Առավելագույն URL-ներ (0 = անսահման)","delay":"Կայք առ կայք դադար (վրկ.)","max_file":"Ֆայլի առավելագույն չափ (բայթ, -1 = անսահման)","extensions":"Ֆայլերի ընդլայնումներ","fallback":"Պահուստային պանակ","robots":"Հարգել robots.txt","download":"Ներբեռնել համապատասխան ֆայլերը","custom":"Custom","logs":"Մատյան"},
 "Русский":{"code":"ru","start":"Запуск","stop":"Стоп","settings":"Настройки","sites":"Сайты","files":"Файлы","dashboard":"Панель","language":"Язык","add":"Добавить","remove":"Удалить","import":"Импорт","save":"Сохранить","collection":"IA Collection","identifier":"IA Identifier","creator":"Автор","workers":"Потоки","depth":"Макс. глубина","max_urls":"Макс. URL (0 = без лимита)","delay":"Задержка хоста (сек.)","max_file":"Макс. размер файла (байт; -1 = без лимита)","extensions":"Расширения файлов","fallback":"Папка резерва","robots":"Соблюдать robots.txt","download":"Скачивать подходящие файлы","custom":"Custom","logs":"Журнал"},
 "Español":{"code":"es","start":"Iniciar","stop":"Detener","settings":"Ajustes","sites":"Sitios","files":"Archivos","dashboard":"Panel","language":"Idioma","add":"Añadir","remove":"Eliminar","import":"Importar","save":"Guardar","collection":"Colección IA","identifier":"Identificador IA","creator":"Creador","workers":"Trabajadores","depth":"Profundidad máxima","max_urls":"Máx. URLs (0 = ilimitado)","delay":"Espera por host (seg.)","max_file":"Tamaño máx. (bytes; -1 = ilimitado)","extensions":"Extensiones","fallback":"Carpeta de respaldo","robots":"Respetar robots.txt","download":"Descargar archivos coincidentes","custom":"Custom","logs":"Registro"},
 "Français":{"code":"fr","start":"Démarrer","stop":"Arrêter","settings":"Paramètres","sites":"Sites","files":"Fichiers","dashboard":"Tableau de bord","language":"Langue","add":"Ajouter","remove":"Supprimer","import":"Importer","save":"Enregistrer","collection":"Collection IA","identifier":"Identifiant IA","creator":"Créateur","workers":"Workers","depth":"Profondeur max.","max_urls":"URLs max. (0 = illimité)","delay":"Délai par hôte (sec.)","max_file":"Taille max. (octets; -1 = illimité)","extensions":"Extensions","fallback":"Dossier de secours","robots":"Respecter robots.txt","download":"Télécharger les fichiers correspondants","custom":"Custom","logs":"Journal"},
 "Deutsch":{"code":"de","start":"Starten","stop":"Stopp","settings":"Einstellungen","sites":"Websites","files":"Dateien","dashboard":"Dashboard","language":"Sprache","add":"Hinzufügen","remove":"Entfernen","import":"Importieren","save":"Speichern","collection":"IA-Sammlung","identifier":"IA-ID","creator":"Ersteller","workers":"Worker","depth":"Max. Tiefe","max_urls":"Max. URLs (0 = unbegrenzt)","delay":"Host-Verzögerung (Sek.)","max_file":"Max. Dateigröße (Bytes; -1 = unbegrenzt)","extensions":"Dateiendungen","fallback":"Fallback-Ordner","robots":"robots.txt beachten","download":"Passende Dateien herunterladen","custom":"Custom","logs":"Protokoll"},
 "Português":{"code":"pt","start":"Iniciar","stop":"Parar","settings":"Definições","sites":"Sites","files":"Ficheiros","dashboard":"Painel","language":"Idioma","add":"Adicionar","remove":"Remover","import":"Importar","save":"Guardar","collection":"Coleção IA","identifier":"ID IA","creator":"Criador","workers":"Workers","depth":"Profundidade máx.","max_urls":"Máx. URLs (0 = ilimitado)","delay":"Atraso por host (seg.)","max_file":"Tamanho máx. (bytes; -1 = ilimitado)","extensions":"Extensões","fallback":"Pasta de fallback","robots":"Respeitar robots.txt","download":"Descarregar ficheiros correspondentes","custom":"Custom","logs":"Registo"},
 "Italiano":{"code":"it","start":"Avvia","stop":"Ferma","settings":"Impostazioni","sites":"Siti","files":"File","dashboard":"Dashboard","language":"Lingua","add":"Aggiungi","remove":"Rimuovi","import":"Importa","save":"Salva","collection":"Collezione IA","identifier":"ID IA","creator":"Creatore","workers":"Worker","depth":"Profondità max","max_urls":"URL max (0 = illimitato)","delay":"Ritardo host (sec.)","max_file":"Dimensione max (byte; -1 = illimitata)","extensions":"Estensioni","fallback":"Cartella fallback","robots":"Rispetta robots.txt","download":"Scarica file corrispondenti","custom":"Custom","logs":"Log"},
 "中文":{"code":"zh","start":"开始","stop":"停止","settings":"设置","sites":"网站","files":"文件","dashboard":"仪表板","language":"语言","add":"添加","remove":"删除","import":"导入","save":"保存","collection":"IA 集合","identifier":"IA 标识符","creator":"创建者","workers":"工作线程","depth":"最大深度","max_urls":"最大 URL（0 = 不限）","delay":"每主机延迟（秒）","max_file":"最大文件大小（字节；-1 = 不限）","extensions":"文件扩展名","fallback":"备用文件夹","robots":"遵守 robots.txt","download":"下载匹配文件","custom":"Custom","logs":"日志"},
 "日本語":{"code":"ja","start":"開始","stop":"停止","settings":"設定","sites":"サイト","files":"ファイル","dashboard":"ダッシュボード","language":"言語","add":"追加","remove":"削除","import":"インポート","save":"保存","collection":"IA コレクション","identifier":"IA 識別子","creator":"作成者","workers":"ワーカー","depth":"最大深度","max_urls":"最大 URL（0 = 無制限）","delay":"ホスト間隔（秒）","max_file":"最大ファイルサイズ（バイト；-1 = 無制限）","extensions":"ファイル拡張子","fallback":"フォールバックフォルダー","robots":"robots.txt を尊重","download":"一致するファイルをダウンロード","custom":"Custom","logs":"ログ"}
}

@dataclass
class Config:
    collection:str=""; identifier:str=""; creator:str=""; title:str="AWEC Web Archive"; description:str="AWEC recursive web crawl dataset"; subject:str="web;archive;crawler"
    access_key:str=""; secret_key:str=""; endpoint:str="https://s3.us.archive.org"; seeds:list[str]=field(default_factory=list)
    workers:int=32; max_depth:int=8; max_urls:int=0; delay:float=.5; timeout:int=30; retries:int=3
    max_file_size:int=-1; extensions:list[str]=field(default_factory=lambda:["*"]); fallback_dir:str=str(APP_DIR/"fallback")
    respect_robots:bool=True; same_domain_only:bool=False; download_files:bool=True

class Engine(QObject):
    log=Signal(str); stats=Signal(dict); finished=Signal(str)
    def __init__(self,cfg:Config):
        super().__init__(); self.cfg=cfg; self.stop_event=threading.Event(); self.lock=threading.Lock(); APP_DIR.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(APP_DIR/"awec-index.db",check_same_thread=False); self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS urls(id INTEGER PRIMARY KEY,url TEXT UNIQUE,domain TEXT,depth INTEGER,source TEXT,status INTEGER,content_type TEXT,size INTEGER,created TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS files(global_id TEXT PRIMARY KEY,domain TEXT,site_name TEXT,url TEXT,filename TEXT,size INTEGER,content_type TEXT,ia_key TEXT,created TEXT)"); self.db.commit()
        self.enqueued=self.fetched=self.files_found=self.uploaded=self.errors=self.active=0
    def stop(self): self.stop_event.set()
    def emit(self): self.stats.emit({"queued":0,"enqueued":self.enqueued,"fetched":self.fetched,"files":self.files_found,"uploaded":self.uploaded,"errors":self.errors,"active":self.active})
    def save_url(self,u,d,s,status,ctype,size):
        with self.lock: self.db.execute("INSERT OR IGNORE INTO urls(url,domain,depth,source,status,content_type,size,created) VALUES(?,?,?,?,?,?,?,?)",(u,urlparse(u).netloc,d,s,status,ctype,size,datetime.now(timezone.utc).isoformat())); self.db.commit()
    def save_file(self,gid,domain,site,url,fn,size,ctype,key):
        with self.lock: self.db.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?)",(gid,domain,site,url,fn,size,ctype,key,datetime.now(timezone.utc).isoformat())); self.db.commit()
    def ext_ok(self,url,ctype=""):
        if "*" in self.cfg.extensions:return True
        ext=Path(urlparse(url).path.lower()).suffix
        return ext in self.cfg.extensions or any(x.startswith("mime:") and x[5:] in ctype.lower() for x in self.cfg.extensions)
    def site_name(self,url): return re.sub(r"[^a-zA-Z0-9._-]+","_",urlparse(url).netloc.lower().split(":")[0])[:100] or "site"
    def file_name(self,url,ctype):
        n=re.sub(r"[^\w.()\-]+","_",Path(urlparse(url).path).name or "index")[:180]
        if "." not in n: n += {"image/jpeg":".jpg","image/png":".png","image/gif":".gif","video/mp4":".mp4","application/pdf":".pdf","application/json":".json"}.get(ctype.split(";")[0],"")
        return n
    async def ia_put(self,data,key,ctype):
        if not(self.cfg.access_key and self.cfg.secret_key and self.cfg.identifier):return False
        def put():
            s3=boto3.client("s3",endpoint_url=self.cfg.endpoint,aws_access_key_id=self.cfg.access_key,aws_secret_access_key=self.cfg.secret_key,region_name="us-east-1")
            s3.put_object(Bucket=self.cfg.identifier,Key=key,Body=data,ContentType=ctype or "application/octet-stream")
        for attempt in range(self.cfg.retries+1):
            try: await asyncio.to_thread(put); return True
            except Exception as e:
                if attempt>=self.cfg.retries:self.log.emit(f"❌ IA upload failed: {key}: {e}"); return False
                await asyncio.sleep(min(60,2**attempt))
        return False
    async def process_file(self,url,response,body):
        ctype=response.headers.get("content-type","").split(";")[0].lower(); length=int(response.headers.get("content-length","-1") or -1)
        if not self.ext_ok(url,ctype) or (self.cfg.max_file_size>=0 and length>self.cfg.max_file_size):return
        if self.cfg.max_file_size>=0 and len(body)>self.cfg.max_file_size:return
        self.files_found+=1; gid=uuid.uuid4().hex; site=self.site_name(url); fn=self.file_name(url,ctype); key=f"files/{site}/{gid}_{fn}"
        ok=await self.ia_put(body,key,ctype)
        if ok:self.uploaded+=1
        else:
            folder=Path(self.cfg.fallback_dir)/site; folder.mkdir(parents=True,exist_ok=True); (folder/f"{gid}_{fn}").write_bytes(body); self.log.emit(f"💾 Fallback: {folder/(gid+'_'+fn)}")
        self.save_file(gid,urlparse(url).netloc,site,url,fn,len(body),ctype,key if ok else "")
    def normalize(self,base,raw):
        raw=raw.strip()
        if not raw or raw.startswith(("#","javascript:","mailto:","tel:","data:")):return None
        u=urldefrag(urljoin(base,raw))[0]; p=urlparse(u); return u[:4000] if p.scheme in ("http","https") and p.netloc else None
    async def fetch(self,session,item,q,seen,host_next,robots):
        url,depth,source=item; host=urlparse(url).netloc.lower(); wait=host_next.get(host,0)-time.monotonic()
        if wait>0:await asyncio.sleep(wait)
        host_next[host]=time.monotonic()+self.cfg.delay
        if self.cfg.respect_robots:
            if host not in robots:
                rp=RobotFileParser(); rp.set_url(f"{urlparse(url).scheme}://{host}/robots.txt")
                try:
                    async with session.get(rp.url,timeout=10) as rr: rp.parse((await rr.text(errors="ignore")).splitlines()) if rr.status==200 else rp.parse([])
                except Exception: rp=None
                robots[host]=rp
            if robots[host] is not None and not robots[host].can_fetch("AWEC/3.0",url):return
        for attempt in range(self.cfg.retries+1):
            try:
                self.active+=1
                async with session.get(url,allow_redirects=True,max_redirects=8,proxy=getattr(self, "proxy_url", None)) as r:
                    ctype=r.headers.get("content-type",""); body=await r.read(); final=str(r.url); self.fetched+=1; self.save_url(final,depth,source,r.status,ctype,len(body))
                    if "text/html" in ctype.lower():
                        text=body.decode(r.charset or "utf-8",errors="ignore"); links=[]
                        for raw in HREF_RE.findall(text)+URL_RE.findall(text):
                            u=self.normalize(final,raw)
                            if u:links.append(u)
                        for u in dict.fromkeys(links):
                            if depth<self.cfg.max_depth and u not in seen and (not self.cfg.max_urls or len(seen)<self.cfg.max_urls):
                                if self.cfg.same_domain_only and urlparse(u).netloc.lower() not in {urlparse(x).netloc.lower() for x in self.cfg.seeds}:continue
                                seen.add(u); await q.put((u,depth+1,final)); self.enqueued+=1
                        if self.cfg.download_files:
                            for u in dict.fromkeys(links):
                                if self.ext_ok(u):await self.fetch_file(session,u)
                    elif self.cfg.download_files: await self.process_file(final,r,body)
                    break
            except (aiohttp.ClientError,asyncio.TimeoutError) as e:
                if attempt>=self.cfg.retries:self.errors+=1; self.log.emit(f"❌ {url}: {e}")
                else: await asyncio.sleep(min(60,2**attempt))
            finally:self.active-=1
    async def fetch_file(self,session,url):
        for attempt in range(self.cfg.retries+1):
            try:
                async with session.get(url,allow_redirects=True,max_redirects=8) as r:
                    if r.status<400: await self.process_file(str(r.url),r,await r.read())
                    return
            except (aiohttp.ClientError,asyncio.TimeoutError) as e:
                if attempt>=self.cfg.retries:self.errors+=1; self.log.emit(f"⚠️ file {url}: {e}")
                else:await asyncio.sleep(min(60,2**attempt))
    async def run_async(self):
        q=asyncio.Queue(maxsize=max(1000,self.cfg.workers*50)); seen=set(); host_next={}; robots={}
        roots={urlparse(x).netloc.lower() for x in self.cfg.seeds}
        for s in self.cfg.seeds:
            u=self.normalize(s,s)
            if u and u not in seen:seen.add(u);await q.put((u,0,"seed"));self.enqueued+=1
        headers = {"User-Agent": getattr(self.cfg, "custom_user_agent", "AWEC/3.0 (+https://github.com/ARARAT33/AWEC)")}
        custom_headers_str = getattr(self.cfg, "custom_headers_json", "")
        if custom_headers_str:
            try:
                ch = json.loads(custom_headers_str)
                if isinstance(ch, dict):
                    headers.update({str(k): str(v) for k, v in ch.items()})
            except Exception:
                pass

        proxy_url = getattr(self.cfg, "proxy_url", "") or None
        self.proxy_url = proxy_url

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.cfg.timeout),headers=headers,connector=aiohttp.TCPConnector(limit=max(16,self.cfg.workers*2))) as session:
            async def worker():
                while not self.stop_event.is_set():
                    try:item=await asyncio.wait_for(q.get(),1)
                    except asyncio.TimeoutError:
                        if q.empty() and self.active==0:return
                        continue
                    try:await self.fetch(session,item,q,seen,host_next,robots)
                    finally:q.task_done();self.emit()
            tasks=[asyncio.create_task(worker()) for _ in range(self.cfg.workers)]
            while not self.stop_event.is_set():
                if q.empty() and self.active==0:break
                await asyncio.sleep(.25)
            await q.join();self.stop_event.set();await asyncio.gather(*tasks,return_exceptions=True)
        self.log.emit("🏁 Crawl completed")
    def start(self):
        try:asyncio.run(self.run_async())
        except Exception as e:self.log.emit(f"💥 Fatal: {e}")
        finally:
            with self.lock:self.db.close()
            self.finished.emit(json.dumps({"fetched":self.fetched,"files":self.files_found,"uploaded":self.uploaded,"errors":self.errors}))

class Main(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle("AWEC Desktop 3.0");self.resize(1250,850);self.fields={};self.custom={};self.engine=None;self.thread=None
        self.tabs=QTabWidget();self.setCentralWidget(self.tabs);self.tabs.addTab(self.config_tab(),"⚙ Settings");self.tabs.addTab(self.sites_tab(),"🌐 Sites");self.tabs.addTab(self.files_tab(),"📦 Files");self.tabs.addTab(self.dashboard_tab(),"📊 Dashboard");self.tabs.addTab(self.lang_tab(),"🌍 Language")
    def field(self,k,v="",pw=False):
        x=QLineEdit(v);x.setEchoMode(QLineEdit.Password if pw else QLineEdit.Normal);self.fields[k]=x;return x
    def config_tab(self):
        w=QWidget();l=QVBoxLayout(w);ia=QGroupBox("Internet Archive / S3");f=QFormLayout(ia)
        for k,label,v,pw in [("collection","Collection","",False),("identifier","Identifier","",False),("creator","Creator","",False),("title","Title","AWEC Web Archive",False),("description","Description","AWEC recursive web crawl dataset",False),("subject","Subject","web;archive;crawler",False),("access","S3 Access Key","",True),("secret","S3 Secret Key","",True),("endpoint","S3 Endpoint","https://s3.us.archive.org",False)]:f.addRow(label,self.field(k,v,pw))
        l.addWidget(ia);c=QGroupBox("Crawler");cf=QFormLayout(c);self.fields["workers"]=QSpinBox();self.fields["workers"].setRange(1,512);self.fields["workers"].setValue(32);cf.addRow("Workers",self.fields["workers"]);self.fields["depth"]=QSpinBox();self.fields["depth"].setRange(0,100);self.fields["depth"].setValue(8);cf.addRow("Max depth",self.fields["depth"]);self.fields["maxurls"]=QSpinBox();self.fields["maxurls"].setRange(0,2000000000);cf.addRow("Max URLs (0 = unlimited)",self.fields["maxurls"]);self.fields["delay"]=QDoubleSpinBox();self.fields["delay"].setRange(0,120);self.fields["delay"].setDecimals(3);self.fields["delay"].setValue(.5);cf.addRow("Per-host delay",self.fields["delay"]);self.fields["maxfile"]=QLineEdit("-1");cf.addRow("Max file size (-1 = unlimited)",self.fields["maxfile"]);self.robots=QCheckBox("Respect robots.txt");self.robots.setChecked(True);cf.addRow(self.robots);self.same=QCheckBox("Same seed domains only");cf.addRow(self.same);self.download=QCheckBox("Download matching files");self.download.setChecked(True);cf.addRow(self.download);l.addWidget(c);fb=QGroupBox("Fallback");ff=QFormLayout(fb);self.fields["fallback"]=self.field("fallback",str(APP_DIR/"fallback"));b=QPushButton("Browse");b.clicked.connect(self.pick);r=QHBoxLayout();r.addWidget(self.fields["fallback"]);r.addWidget(b);ff.addRow("Folder",r);l.addWidget(fb);return w
    def sites_tab(self):
        w=QWidget();l=QVBoxLayout(w);self.site_list=QListWidget();l.addWidget(self.site_list);r=QHBoxLayout();self.site=QLineEdit();r.addWidget(self.site);a=QPushButton("Add");a.clicked.connect(lambda:self.add(self.site.text()));rm=QPushButton("Remove");rm.clicked.connect(lambda:self.site_list.takeItem(self.site_list.currentRow()));imp=QPushButton("Import TXT/JSON/DOC/DOCX");imp.clicked.connect(self.import_sites);r.addWidget(a);r.addWidget(rm);r.addWidget(imp);l.addLayout(r);l.addWidget(QLabel("Կայքերը կարող են լինել TXT, JSON, DOC կամ DOCX ֆայլերում։"));return w
    def files_tab(self):
        w=QWidget();l=QVBoxLayout(w);l.addWidget(QLabel("Extensions: use * for every file type. Examples: .jpg .png .mp4 .pdf .zip .docx"));self.ext=QPlainTextEdit("*");self.ext.setMaximumHeight(100);l.addWidget(self.ext);return w
    def dashboard_tab(self):
        w=QWidget();l=QVBoxLayout(w);self.labels={};g=QGridLayout();
        for i,k in enumerate(["queued","enqueued","fetched","files","uploaded","errors","active"]):self.labels[k]=QLabel("0");g.addWidget(QLabel(k.title()),i,0);g.addWidget(self.labels[k],i,1)
        l.addLayout(g);self.logs=QPlainTextEdit();self.logs.setReadOnly(True);l.addWidget(self.logs);r=QHBoxLayout();self.start=QPushButton("Start");self.start.clicked.connect(self.run);self.stopb=QPushButton("Stop");self.stopb.clicked.connect(self.stop);r.addWidget(self.start);r.addWidget(self.stopb);l.addLayout(r);return w
    def lang_tab(self):
        w=QWidget();l=QVBoxLayout(w);self.lang=QComboBox();self.lang.addItems(list(LANGS)+["Custom"]);self.lang.currentTextChanged.connect(self.change_lang);l.addWidget(self.lang);self.editor=QPlainTextEdit();self.editor.setPlainText(json.dumps(LANGS["English"],ensure_ascii=False,indent=2));l.addWidget(self.editor);r=QHBoxLayout();sv=QPushButton("Save custom .awec.language");sv.clicked.connect(self.save_lang);im=QPushButton("Import .awec.language");im.clicked.connect(self.import_lang);r.addWidget(sv);r.addWidget(im);l.addLayout(r);l.addWidget(QLabel("Custom mode lets the user edit every UI string. Save/import JSON with extension .awec.language."));return w
    def pick(self):
        p=QFileDialog.getExistingDirectory(self,"Fallback folder");
        if p:self.fields["fallback"].setText(p)
    def add(self,u):
        u=u.strip()
        if u and u not in [self.site_list.item(i).text() for i in range(self.site_list.count())]:self.site_list.addItem(u)
        self.site.clear()
    def import_sites(self):
        p,_=QFileDialog.getOpenFileName(self,"Import sites",str(APP_DIR),"Sites (*.txt *.json *.doc *.docx);;All (*)")
        if not p:return
        try:
            if p.lower().endswith(".json"):text=json.dumps(json.loads(Path(p).read_text(encoding="utf-8")),ensure_ascii=False)
            elif p.lower().endswith(".docx") and Document:text="\n".join(x.text for x in Document(p).paragraphs)
            else:text=Path(p).read_text(encoding="utf-8",errors="ignore")
            for u in URL_RE.findall(text):self.add(u)
        except Exception as e:QMessageBox.warning(self,"AWEC",str(e))
    def change_lang(self,name):
        d=LANGS.get(name) or self.custom.get(name) or LANGS["English"];self.editor.setPlainText(json.dumps(d,ensure_ascii=False,indent=2));self.start.setText(d.get("start","Start"));self.stopb.setText(d.get("stop","Stop"))
    def save_lang(self):
        try:
            d=json.loads(self.editor.toPlainText());name=d.get("name") or d.get("code") or "custom";LANG_DIR.mkdir(exist_ok=True);fn=LANG_DIR/(re.sub(r"[^\w.-]+","_",name)+".awec.language");fn.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8");self.custom[name]=d;self.lang.addItem(name);self.lang.setCurrentText(name)
        except Exception as e:QMessageBox.warning(self,"AWEC",f"Invalid language: {e}")
    def import_lang(self):
        p,_=QFileDialog.getOpenFileName(self,"Import language",str(LANG_DIR),"AWEC language (*.awec.language);;JSON (*.json)")
        if not p:return
        try:
            d=json.loads(Path(p).read_text(encoding="utf-8"));name=d.get("name") or d.get("code") or Path(p).stem;self.custom[name]=d;self.lang.addItem(name);self.lang.setCurrentText(name)
        except Exception as e:QMessageBox.warning(self,"AWEC",str(e))
    def cfg(self):
        ex=[]
        for x in re.split(r"[\s,;]+",self.ext.toPlainText().strip()):
            if x:ex.append(x.lower() if x=="*" or x.startswith((".","mime:")) else "."+x.lower())
        try:mfs=int(self.fields["maxfile"].text())
        except:mfs=-1
        return Config(collection=self.fields["collection"].text(),identifier=self.fields["identifier"].text(),creator=self.fields["creator"].text(),title=self.fields["title"].text(),description=self.fields["description"].text(),subject=self.fields["subject"].text(),access_key=self.fields["access"].text(),secret_key=self.fields["secret"].text(),endpoint=self.fields["endpoint"].text(),seeds=[self.site_list.item(i).text() for i in range(self.site_list.count())],workers=self.fields["workers"].value(),max_depth=self.fields["depth"].value(),max_urls=self.fields["maxurls"].value(),delay=self.fields["delay"].value(),max_file_size=mfs,extensions=ex or ["*"],fallback_dir=self.fields["fallback"].text(),respect_robots=self.robots.isChecked(),same_domain_only=self.same.isChecked(),download_files=self.download.isChecked())
    def run(self):
        if not self.site_list.count():QMessageBox.warning(self,"AWEC","Add at least one seed site.");return
        self.engine=Engine(self.cfg());self.thread=QThread();self.engine.moveToThread(self.thread);self.thread.started.connect(self.engine.start);self.engine.log.connect(self.log);self.engine.stats.connect(self.update_stats);self.engine.finished.connect(self.done);self.thread.start();self.start.setEnabled(False)
    def stop(self):
        if self.engine:self.engine.stop();self.log("🛑 Stop requested")
    def update_stats(self,d):
        for k,v in d.items():
            if k in self.labels:self.labels[k].setText(f"{v:,}")
    def log(self,s):self.logs.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}] {s}")
    def done(self,s):self.start.setEnabled(True);self.log("✅ "+s);self.thread.quit();self.thread.wait();self.thread=None;self.engine=None

if __name__=="__main__":
    app=QApplication([]);app.setStyle("Fusion");w=Main();w.show();app.exec()
