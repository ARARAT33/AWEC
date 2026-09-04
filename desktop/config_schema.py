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

    # FANTI — advanced, configurable transport behavior.
    custom_user_agent: str = "AWEC/3.0 (+https://github.com/ARARAT33/AWEC; Archival Crawler)"
    ua_rotation_enabled: bool = True
    delay_jitter_sec: float = 0.25
    cookie_jar_enabled: bool = True
    verify_ssl: bool = True
    auto_headers_enabled: bool = True
    proxy_url: str = ""
    custom_headers_json: str = "{\n  \"Accept-Language\": \"en-US,en;q=0.9\",\n  \"Cache-Control\": \"no-cache\"\n}"

    fanti_user_agent_profile: str = "archive"
    fanti_header_profile: str = "Default Archive"
    fanti_min_delay: float = 0.05
    fanti_max_delay: float = 8.0
    fanti_initial_delay: float = 0.15
    fanti_adaptive_pacing: bool = True
    fanti_min_concurrency: int = 1
    fanti_max_concurrency: int = 32
    fanti_initial_concurrency: int = 8
    fanti_adaptive_concurrency: bool = True
    fanti_max_retries: int = 5
    fanti_backoff_strategy: str = "full_jitter"
    fanti_base_retry_delay: float = 1.0
    fanti_max_retry_delay: float = 60.0
    fanti_circuit_breaker_enabled: bool = True
    fanti_circuit_breaker_threshold: int = 5
    fanti_circuit_breaker_cooldown: float = 30.0
    fanti_max_connections: int = 160
    fanti_max_connections_per_host: int = 32
    fanti_keepalive_timeout: float = 30.0
    fanti_dns_timeout: float = 10.0
    fanti_connect_timeout: float = 10.0
    fanti_read_timeout: float = 30.0
    fanti_total_timeout: float = 60.0
    fanti_max_redirects: int = 10
    fanti_allow_cross_domain_redirects: bool = True
    fanti_cookie_policy: str = "per-job"
    fanti_bandwidth_limit_bytes_per_sec: int = 0
    fanti_enable_browser_rendering: bool = False
    fanti_browser_timeout: float = 30.0
    fanti_diagnostic_mode: bool = False

    # Zero / quota local storage management.
    max_local_storage_mb: int = 50
    purge_local_files_after_upload: bool = True

    # Storage & Internet Archive S3 settings.
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
