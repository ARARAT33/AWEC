"""Central AWEC configuration model used by the desktop UI and crawler."""
from dataclasses import dataclass, field, asdict
import json
from pathlib import Path

FILE_TYPES = ['*']

@dataclass
class AWECConfig:
    network_mode: str = "standard"  # standard or fanti
    seeds: list[str] = field(default_factory=list)
    follow_links: bool = True
    follow_subdomains: bool = True
    follow_external_domains: bool = False
    download_discovered_files: bool = True
    file_types: list[str] = field(default_factory=lambda: ['*'])
    max_depth: int = 8
    max_urls: int = 0
    max_file_size: int = -1
    max_total_size: int = 10 * 1024**3
    workers: int = 32
    requests_per_second: float = 2.0
    per_host_delay: float = 0.5
    respect_robots: bool = True
    same_domain_only: bool = False
    max_retries: int = 3
    request_timeout: int = 30
    retry_backoff_factor: float = 2.0

    # Deep Anti-Blocking & Advanced Crawler Settings
    custom_user_agent: str = "AWEC/3.0 (+https://github.com/ARARAT33/AWEC; Archival Crawler)"
    ua_rotation_enabled: bool = True
    delay_jitter_sec: float = 0.25
    cookie_jar_enabled: bool = True
    verify_ssl: bool = True
    auto_headers_enabled: bool = True
    proxy_url: str = ""
    custom_headers_json: str = "{\n  \"Accept-Language\": \"en-US,en;q=0.9\",\n  \"Cache-Control\": \"no-cache\"\n}"

    # Zero / Quota Local Storage Management
    max_local_storage_mb: int = 50  # 0 means store nothing locally (zero local footprint)
    purge_local_files_after_upload: bool = True

    # Storage & Internet Archive S3 Settings
    destination_archive: bool = True
    destination_local: bool = False
    ia_collection: str = ""
    ia_identifier: str = ""
    ia_creator: str = ""
    ia_title: str = "AWEC Web Archive"
    ia_description: str = "AWEC recursive web crawl dataset"
    ia_subject: str = "web;archive;crawler"
    ia_access_key: str = ""
    ia_secret_key: str = ""
    ia_endpoint: str = "https://s3.us.archive.org"
    fallback_dir: str = "fallback"

    checkpoint_path: str = "awec-state/checkpoint.json"
    language: str = "en"
    custom_language_file: str = ""

    def to_dict(self):
        return asdict(self)

    def save(self, path: str | Path):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path):
        p = Path(path)
        if not p.exists():
            return cls()
        data = json.loads(p.read_text(encoding="utf-8"))
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
