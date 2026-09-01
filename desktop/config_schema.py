"""Central AWEC configuration model used by the desktop UI and crawler."""
from dataclasses import dataclass, field, asdict
import json
from pathlib import Path

FILE_TYPES = ['*']

@dataclass
class AWECConfig:
    seeds: list[str] = field(default_factory=list)
    follow_links: bool = True
    follow_subdomains: bool = True
    follow_external_domains: bool = False
    download_discovered_files: bool = True
    file_types: list[str] = field(default_factory=lambda: ['*'])
    max_depth: int = 3
    max_file_size: int = -1
    max_total_size: int = 10 * 1024**3
    workers: int = 16
    requests_per_second: float = 2.0
    respect_robots: bool = True
    retry_count: int = 2
    retry_delays: list[int] = field(default_factory=lambda: [10, 20])
    destination_archive: bool = True
    destination_local: bool = False
    local_folder: str = ''
    checkpoint_path: str = 'awec-state/checkpoint.json'
    email_enabled: bool = False
    email_threshold_bytes: int = 1024**3
    language: str = 'en'
    custom_language_file: str = ''

    def to_dict(self): return asdict(self)
    def save(self, path):
        p=Path(path); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
    @classmethod
    def load(cls,path):
        return cls(**json.loads(Path(path).read_text(encoding='utf-8')))
