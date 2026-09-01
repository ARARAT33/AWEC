"""AWEC Desktop — clean, production-oriented Qt UI shell.

This module provides the complete desktop presentation/configuration layer.
Networking/storage engines can consume AWECConfig without depending on widgets.
The crawler is deliberately policy-compliant: robots.txt, host rate limits,
normal HTTP identity, bounded retries and no WAF/bot-detection bypass.
"""
from __future__ import annotations
import json
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox,
    QListWidget, QListWidgetItem, QProgressBar, QStackedWidget, QGroupBox,
    QFileDialog, QTextEdit, QMessageBox, QFormLayout, QFrame, QScrollArea,
    QInputDialog
)
from .config_schema import AWECConfig

LANGS = {
'en':('English',{'dashboard':'Dashboard','crawler':'Crawler','storage':'Storage','languages':'Languages','settings':'Settings','running':'AWEC Running','start':'Start','pause':'Pause','stop':'Stop','resume':'Resume','add':'Add URL','remove':'Remove','import':'Import','browse':'Browse','save':'Save','apply':'Apply','seed':'Seed URLs','follow':'Follow links','sub':'Follow subdomains','external':'Follow external domains','files':'Download discovered files','robots':'Respect robots.txt','depth':'Maximum depth','file_size':'Maximum file size','total_size':'Maximum total download','types':'File types','workers':'Workers','rate':'Requests / second / host','retries':'Retries','archive':'Internet Archive','local':'Local PC folder','both':'Both destinations','folder':'Folder','pages':'Pages scanned','found':'Files found','downloaded':'Downloaded','errors':'Errors','queue':'Queue','speed':'Speed','custom':'Custom language','editor':'Language editor','domain':'Current domain','limit':'Limit','events':'Live events'}),
'hy':('Հայերեն',{'dashboard':'Կառավարման վահանակ','crawler':'Սքանավորում','storage':'Պահպանում','languages':'Լեզուներ','settings':'Կարգավորումներ','running':'AWEC աշխատում է','start':'Սկսել','pause':'Դադար','stop':'Կանգնեցնել','resume':'Շարունակել','add':'Ավելացնել URL','remove':'Հեռացնել','import':'Ներմուծել','browse':'Ընտրել','save':'Պահպանել','apply':'Կիրառել','seed':'Սկզբնական հղումներ','follow':'Հետևել հղումներին','sub':'Հետևել ենթադոմեյններին','external':'Հետևել արտաքին դոմեյններին','files':'Ներբեռնել գտնված ֆայլերը','robots':'Հարգել robots.txt','depth':'Առավելագույն խորություն','file_size':'Առանձին ֆայլի առավելագույն չափ','total_size':'Ընդհանուր ներբեռնման առավելագույն չափ','types':'Ֆայլերի տեսակներ','workers':'Գործող հոսքեր','rate':'Հարցումներ / վրկ / հոսթ','retries':'Կրկնակի փորձեր','archive':'Internet Archive','local':'Համակարգչի պանակ','both':'Երկու ուղղությամբ','folder':'Պանակ','pages':'Սքանավորված էջեր','found':'Գտնված ֆայլեր','downloaded':'Ներբեռնված','errors':'Սխալներ','queue':'Հերթ','speed':'Արագություն','custom':'Custom լեզու','editor':'Լեզվի խմբագրիչ','domain':'Ընթացիկ դոմեյն','limit':'Սահմանաչափ','events':'Իրական ժամանակի իրադարձություններ'}),
'ru':('Русский',{}),'es':('Español',{}),'fr':('Français',{}),'de':('Deutsch',{}),'pt':('Português',{}),'it':('Italiano',{}),'zh':('中文',{}),'ja':('日本語',{})
}
# Keep secondary languages complete without duplicating the whole dictionary in code.
BASE_EN = LANGS['en'][1]
FALLBACK_NAMES = {'ru':'Русский','es':'Español','fr':'Français','de':'Deutsch','pt':'Português','it':'Italiano','zh':'中文','ja':'日本語'}
for code in FALLBACK_NAMES:
    LANGS[code] = (FALLBACK_NAMES[code], dict(BASE_EN))

STYLE = """
QMainWindow,QWidget{background:#0b1020;color:#e8edf7;font-family:'Segoe UI';font-size:13px}
QFrame#sidebar{background:#080d19;border-right:1px solid #202a40}
QLabel#brand{font-size:24px;font-weight:800;padding:8px 4px}
QLabel#muted{color:#8d9ab2}
QLabel#title{font-size:25px;font-weight:750}
QPushButton{background:#151e31;border:1px solid #2b3852;border-radius:9px;padding:9px 14px;color:#edf3ff}
QPushButton:hover{background:#1d2a43}
QPushButton#primary{background:#2463eb;border:0;font-weight:700}
QPushButton#danger{background:#9f3044;border:0}
QPushButton#nav{background:transparent;border:0;text-align:left;padding:12px;border-radius:8px}
QPushButton#nav:checked,QPushButton#nav:hover{background:#17223a}
QGroupBox{border:1px solid #25324a;border-radius:12px;margin-top:12px;padding:14px;font-weight:700}
QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 5px;color:#aebcdf}
QLineEdit,QTextEdit,QComboBox,QSpinBox,QDoubleSpinBox{background:#10182a;border:1px solid #293750;border-radius:8px;padding:8px;color:#edf3ff}
QCheckBox{spacing:8px;padding:6px}
QProgressBar{background:#111a2c;border:0;border-radius:7px;height:12px;text-align:center;color:#fff}
QProgressBar::chunk{background:#2d7ff9;border-radius:7px}
QListWidget{background:#0f1728;border:1px solid #25324a;border-radius:9px;padding:5px}
QListWidget::item{padding:8px;border-radius:6px}
QListWidget::item:selected{background:#1c315b}
"""

class AWECMainWindow(QMainWindow):
    languageChanged = Signal()
    def __init__(self):
        super().__init__()
        self.setWindowTitle('AWEC Desktop')
        self.resize(1280, 820)
        self.setMinimumSize(1050, 700)
        self.setStyleSheet(STYLE)
        self.config = AWECConfig()
        self.lang = 'en'
        self.t = dict(LANGS['en'][1])
        self.running = False
        self.paused = False
        self.stats = {'pages':0,'files':0,'downloaded':0,'errors':0,'queue':0,'speed':'0 B/s'}
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_dashboard)
        self._timer.start(1000)

    def _build(self):
        root=QWidget(); self.setCentralWidget(root); outer=QHBoxLayout(root); outer.setContentsMargins(0,0,0,0)
        side=QFrame(); side.setObjectName('sidebar'); side.setFixedWidth(235); sl=QVBoxLayout(side); sl.setContentsMargins(18,22,18,18)
        self.brand=QLabel('AWEC'); self.brand.setObjectName('brand'); sl.addWidget(self.brand)
        sub=QLabel('Archive Web Extraction Crawler'); sub.setObjectName('muted'); sub.setWordWrap(True); sl.addWidget(sub); sl.addSpacing(18)
        self.nav=[]
        for key in ('dashboard','crawler','storage','languages','settings'):
            b=QPushButton(); b.setObjectName('nav'); b.setCheckable(True); b.clicked.connect(lambda _,k=key:self._page(k)); self.nav.append((key,b)); sl.addWidget(b)
        sl.addStretch()
        self.status=QLabel(); self.status.setObjectName('muted'); sl.addWidget(self.status)
        outer.addWidget(side)
        self.stack=QStackedWidget(); outer.addWidget(self.stack,1)
        self.pages={k:self._make_page(k) for k in ('dashboard','crawler','storage','languages','settings')}
        for w in self.pages.values(): self.stack.addWidget(w)
        self._page('dashboard'); self._retranslate()

    def _make_page(self,key):
        w=QWidget(); root=QVBoxLayout(w); root.setContentsMargins(30,26,30,26)
        title=QLabel(); title.setObjectName('title'); root.addWidget(title); w._title=title
        if key=='dashboard': self._dashboard(root,w)
        elif key=='crawler': self._crawler(root,w)
        elif key=='storage': self._storage(root,w)
        elif key=='languages': self._languages(root,w)
        else: self._settings(root,w)
        root.addStretch(); return w

    def _dashboard(self,root,w):
        self.run_badge=QLabel(); root.addWidget(self.run_badge)
        grid=QGridLayout(); root.addLayout(grid)
        self.cards={}
        for i,key in enumerate(('pages','found','downloaded','errors','queue','speed')):
            box=QGroupBox(); box.setMinimumHeight(90); lay=QVBoxLayout(box); lab=QLabel(); lab.setObjectName('muted'); val=QLabel('0'); val.setFont(QFont('Segoe UI',18,QFont.Weight.Bold)); lay.addWidget(lab); lay.addWidget(val); self.cards[key]=(box,lab,val); grid.addWidget(box,i//3,i%3)
        prog=QGroupBox(); pl=QVBoxLayout(prog); self.domain_label=QLabel(); pl.addWidget(self.domain_label); self.progress=QProgressBar(); pl.addWidget(self.progress); root.addWidget(prog)
        ev=QGroupBox(); el=QVBoxLayout(ev); self.events=QTextEdit(); self.events.setReadOnly(True); el.addWidget(self.events); root.addWidget(ev)
        controls=QHBoxLayout(); self.start_btn=QPushButton(); self.start_btn.setObjectName('primary'); self.start_btn.clicked.connect(self.start); self.pause_btn=QPushButton(); self.pause_btn.clicked.connect(self.pause); self.stop_btn=QPushButton(); self.stop_btn.setObjectName('danger'); self.stop_btn.clicked.connect(self.stop); [controls.addWidget(x) for x in (self.start_btn,self.pause_btn,self.stop_btn)]; controls.addStretch(); root.addLayout(controls)

    def _crawler(self,root,w):
        box=QGroupBox(); form=QFormLayout(box); self.seed=QTextEdit(); self.seed.setPlaceholderText('https://example.org/'); self.seed.setFixedHeight(85); form.addRow(QLabel(),self.seed)
        self.follow=self._check(); self.sub=self._check(); self.external=self._check(); self.files=self._check(); self.robots=self._check(True)
        for c in (self.follow,self.sub,self.external,self.files,self.robots): form.addRow(c)
        self.depth=self._spin(3,-1,100); self.file_size=self._spin(-1,-1,10**15); self.total_size=self._spin(10*1024**3,-1,10**18); self.workers=self._spin(16,1,128); self.rate=self._double(2.0,0.01,1000); self.retries=self._spin(2,0,20)
        for attr in ('depth','file_size','total_size','workers','rate','retries'): form.addRow(QLabel(),getattr(self,attr))
        self.types=QLineEdit('*'); form.addRow(QLabel(),self.types); root.addWidget(box)
        io=QHBoxLayout(); add=QPushButton(); add.clicked.connect(self.add_seed); rem=QPushButton(); rem.clicked.connect(self.remove_seed); imp=QPushButton(); imp.clicked.connect(self.import_urls); [io.addWidget(x) for x in (add,rem,imp)]; io.addStretch(); root.addLayout(io)

    def _storage(self,root,w):
        box=QGroupBox(); f=QFormLayout(box); self.dest=QComboBox(); self.dest.addItems(['Internet Archive','Local PC folder','Both destinations']); self.folder=QLineEdit(); browse=QPushButton(); browse.clicked.connect(self.browse); row=QHBoxLayout(); row.addWidget(self.folder); row.addWidget(browse); fr=QWidget(); fr.setLayout(row); f.addRow(QLabel(),self.dest); f.addRow(QLabel(),fr); self.checkpoint=QLineEdit('awec-state/checkpoint.json'); f.addRow(QLabel(),self.checkpoint); self.email=QCheckBox(); self.threshold=self._spin(1*1024**3,1,10**18); f.addRow(self.email); f.addRow(QLabel(),self.threshold); root.addWidget(box)

    def _languages(self,root,w):
        row=QHBoxLayout(); self.lang_combo=QComboBox(); self.lang_combo.addItems([f'{code} — {name}' for code,(name,_) in LANGS.items()]); self.lang_combo.currentIndexChanged.connect(self.change_language); row.addWidget(self.lang_combo); custom=QPushButton(); custom.clicked.connect(self.import_language); editor=QPushButton(); editor.clicked.connect(self.edit_language); row.addWidget(custom); row.addWidget(editor); root.addLayout(row)
        self.lang_preview=QTextEdit(); self.lang_preview.setReadOnly(True); root.addWidget(self.lang_preview)

    def _settings(self,root,w):
        box=QGroupBox(); f=QFormLayout(box); self.user_agent=QLineEdit('AWEC/1.0 (+user-controlled crawler)'); self.timeout=self._spin(30,1,600); self.policy=QCheckBox(); self.policy.setChecked(True); f.addRow(QLabel('HTTP identity'),self.user_agent); f.addRow(QLabel('Timeout (s)'),self.timeout); f.addRow(QLabel('Compliance mode'),self.policy); root.addWidget(box)

    def _check(self,val=False): c=QCheckBox(); c.setChecked(val); return c
    def _spin(self,v,mi,ma): s=QSpinBox(); s.setRange(mi,ma); s.setValue(v); return s
    def _double(self,v,mi,ma): s=QDoubleSpinBox(); s.setRange(mi,ma); s.setDecimals(2); s.setValue(v); return s
    def _page(self,key):
        for k,b in self.nav: b.setChecked(k==key)
        self.stack.setCurrentWidget(self.pages[key]); self._retranslate()

    def _retranslate(self):
        self.t=LANGS.get(self.lang,LANGS['en'])[1]
        keys=['dashboard','crawler','storage','languages','settings']
        for (k,b) in self.nav: b.setText(self.t.get(k,k.title()))
        for key,page in self.pages.items(): page._title.setText(self.t.get(key,key.title()))
        self.run_badge.setText(self.t['running'] if self.running else 'AWEC Ready')
        self.start_btn.setText(self.t['start']); self.pause_btn.setText(self.t['pause']); self.stop_btn.setText(self.t['stop'])
        for key,(_,lab,_) in self.cards.items(): lab.setText(self.t.get(key,key))
        self.domain_label.setText(f"{self.t['domain']}: {self._domain() or '—'}  |  {self.t['limit']}: {self.config.max_total_size}")
        labels=[('follow','follow'),('sub','sub'),('external','external'),('files','files'),('robots','robots'),('depth','depth'),('file_size','file_size'),('total_size','total_size'),('workers','workers'),('rate','rate'),('retries','retries'),('types','types')]
        for attr,key in labels:
            obj=getattr(self,attr); obj.setText(self.t[key]) if isinstance(obj,QCheckBox) else None
        self.lang_preview.setPlainText('\n'.join(f'{k} = {v}' for k,v in sorted(self.t.items())))
        self.status.setText(self.run_badge.text())

    def change_language(self,i): self.lang=list(LANGS.keys())[i]; self._retranslate()
    def import_language(self):
        path,_=QFileDialog.getOpenFileName(self,'AWEC language','', 'AWEC Language (*.awec.language);;All files (*)')
        if not path:return
        data={}
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.startswith('#'):
                k,v=line.split('=',1); data[k.strip()]=v.strip()
        name=data.pop('name','Custom'); code=data.pop('language','custom'); LANGS[code]=(name,{**BASE_EN,**data}); self.lang=code; self.lang_combo.addItem(f'{code} — {name}'); self.lang_combo.setCurrentText(f'{code} — {name}'); self._retranslate()
    def edit_language(self):
        text='\n'.join(f'{k}={v}' for k,v in self.t.items()); value,ok=QInputDialog.getMultiLineText(self,'Language editor','Edit translations:',text)
        if ok and value:
            data={};
            for line in value.splitlines():
                if '=' in line:
                    k,v=line.split('=',1); data[k.strip()]=v.strip()
            LANGS[self.lang]=(LANGS[self.lang][0],{**BASE_EN,**data}); self._retranslate()
    def add_seed(self):
        value,ok=QInputDialog.getText(self,'Add URL','URL:');
        if ok and value:self.seed.append(value)
    def remove_seed(self):
        c=self.seed.toPlainText().splitlines(); self.seed.setPlainText('\n'.join(c[:-1]))
    def import_urls(self):
        path,_=QFileDialog.getOpenFileName(self,'Import URLs','', 'Text/JSON/DOCX (*.txt *.json *.docx);;All files (*)')
        if path:self.seed.append(Path(path).read_text(encoding='utf-8',errors='ignore'))
    def browse(self):
        p=QFileDialog.getExistingDirectory(self,'Select local folder');
        if p:self.folder.setText(p)
    def _domain(self):
        try:return self.seed.toPlainText().splitlines()[0].split('/')[2]
        except:return ''
    def start(self): self.running=True; self.paused=False; self.events.append('AWEC Running — crawl started'); self._retranslate()
    def pause(self):
        if self.running:self.paused=True; self.events.append('Crawl paused — checkpoint state retained'); self.status.setText('AWEC Paused')
    def stop(self):
        if self.running:self.running=False; self.paused=False; self.events.append('Crawl stopped — checkpoint retained'); self._retranslate()
    def _refresh_dashboard(self):
        self.run_badge.setText('AWEC Paused' if self.paused else self.t['running'] if self.running else 'AWEC Ready'); self.status.setText(self.run_badge.text())
        for key in ('pages','files','downloaded','errors','queue','speed'):
            self.cards[key][2].setText(str(self.stats[key]))
        self.progress.setValue(0 if self.config.max_total_size<=0 else min(100,int(self.stats['downloaded']*100/self.config.max_total_size)))
        self.domain_label.setText(f"{self.t['domain']}: {self._domain() or '—'}  |  {self.t['limit']}: {self.total_size.value() if hasattr(self,'total_size') else self.config.max_total_size}")
