"""Custom AWEC language editor backend."""
from pathlib import Path

def load_language(path: str) -> dict[str,str]:
    out={}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v=line.split('=',1); out[k.strip()]=v.strip()
    return out

def save_language(path: str, values: dict[str,str], language: str, name: str):
    lines=[f'language={language}',f'name={name}']+[f'{k}={v}' for k,v in sorted(values.items())]
    Path(path).write_text('\n'.join(lines)+'\n',encoding='utf-8')
