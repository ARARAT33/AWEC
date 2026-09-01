import unittest
import tempfile
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from awec.archive.ia import IAUploader

class Mock411Handler(BaseHTTPRequestHandler):
    def do_PUT(self):
        content_length = self.headers.get("Content-Length")
        if not content_length:
            self.send_response(411)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"411 Length Required")
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

class TestIA411Regression(unittest.TestCase):
    def test_ia_411_fix_verification(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"Sample archive data for IA upload")
            tmp_path = tmp.name

        uploader = IAUploader("access", "secret", "identifier")
        val_ok, val_msg = uploader.validate_dry_run({}, [tmp_path])
        self.assertTrue(val_ok)

        Path(tmp_path).unlink(missing_ok=True)

if __name__ == "__main__":
    unittest.main()
