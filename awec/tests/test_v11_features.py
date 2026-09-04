from pathlib import Path

from awec.resources.site_mirror import SiteMirror


def test_site_mirror_preserves_host_and_path(tmp_path: Path):
    mirror = SiteMirror(tmp_path)
    target = mirror.save("https://example.com/assets/app.js?v=1", b"console.log(1)", "application/javascript")
    assert target.exists()
    assert "example.com" in str(target)
    assert target.suffix == ".js"
    assert mirror.manifest["https://example.com/assets/app.js?v=1"]["sha256"]


def test_site_mirror_discovers_html_assets(tmp_path: Path):
    mirror = SiteMirror(tmp_path)
    html = b'<html><img src="/img/a.png"><script src="/app.js"></script><link rel="stylesheet" href="/site.css"></html>'
    found = mirror.discover("https://example.com/", html, "text/html")
    urls = {item[0] for item in found}
    assert "https://example.com/img/a.png" in urls
    assert "https://example.com/app.js" in urls
    assert "https://example.com/site.css" in urls
