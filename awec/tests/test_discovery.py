import unittest
from awec.discovery.parsers import ContentExtractor

class TestDiscovery(unittest.TestCase):
    def test_extract_html_links(self):
        html = """
        <html>
        <head>
            <link rel="stylesheet" href="/style.css">
            <script src="app.js"></script>
        </head>
        <body>
            <a href="https://example.com/about">About</a>
            <img src="logo.png" srcset="logo-2x.png 2x">
        </body>
        </html>
        """
        links = ContentExtractor.extract_html_links("https://example.com/page", html)
        urls = [u for u, _, _ in links]
        self.assertIn("https://example.com/style.css", urls)
        self.assertIn("https://example.com/app.js", urls)
        self.assertIn("https://example.com/about", urls)
        self.assertIn("https://example.com/logo.png", urls)

    def test_extract_css_links(self):
        css = """
        @import url('extra.css');
        body { background: url("/bg.png"); }
        """
        links = ContentExtractor.extract_css_links("https://example.com/css/main.css", css)
        urls = [u for u, _, _ in links]
        self.assertIn("https://example.com/css/extra.css", urls)
        self.assertIn("https://example.com/bg.png", urls)

    def test_parse_sitemap(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/page1</loc></url>
            <url><loc>https://example.com/page2</loc></url>
        </urlset>
        """
        urls = ContentExtractor.parse_sitemap(xml.encode("utf-8"))
        self.assertEqual(urls, ["https://example.com/page1", "https://example.com/page2"])

if __name__ == "__main__":
    unittest.main()
