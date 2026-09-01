from pathlib import Path

LANGUAGES = {
    'en':'English','hy':'Հայերեն','ru':'Русский','es':'Español','fr':'Français',
    'de':'Deutsch','pt':'Português','it':'Italiano','zh':'中文','ja':'日本語'
}

def load_pack(path):
    data={}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if line and not line.startswith('#') and '=' in line:
            k,v=line.split('=',1); data[k.strip()]=v.strip()
    return data

def language_files(root='desktop/languages'):
    return sorted(Path(root).glob('*.awec.language'))
