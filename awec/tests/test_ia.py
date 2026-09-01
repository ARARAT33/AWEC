import unittest
import tempfile
import os
from pathlib import Path
from awec.archive.ia import generate_ia_identifier, IAUploader

class TestIA(unittest.TestCase):
    def test_identifier_generator(self):
        ident = generate_ia_identifier("example.com", "20260901-120000")
        self.assertEqual(ident, "awecrawl-example-com-20260901-120000")

    def test_local_file_not_found(self):
        uploader = IAUploader("key", "secret", "itemid")
        ok, msg = uploader.upload_file_s3("non_existent_file.txt", "key")
        self.assertFalse(ok)
        self.assertEqual(msg, "LOCAL_FILE_NOT_FOUND")

if __name__ == "__main__":
    unittest.main()
