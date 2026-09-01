"""Crash-safe AWEC state persistence and restart recovery."""
from pathlib import Path
import json, os

class RecoveryStore:
    def __init__(self, path='awec-state/checkpoint.json'):
        self.path=Path(path)
    def save(self,state):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(tmp,self.path)
    def load(self):
        if not self.path.exists(): return None
        return json.loads(self.path.read_text(encoding='utf-8'))
