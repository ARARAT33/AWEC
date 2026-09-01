import unittest
import asyncio
import tempfile
import os
from pathlib import Path
from awec.resources.downloader import DownloadManager

class MockStreamReader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    async def read(self, chunk_size: int) -> bytes:
        if self.offset >= len(self.data):
            return b""
        chunk = self.data[self.offset : self.offset + chunk_size]
        self.offset += chunk_size
        return chunk

class TestLargeFile(unittest.TestCase):
    def test_streaming_download(self):
        async def run():
            with tempfile.TemporaryDirectory() as tmpdir:
                dm = DownloadManager(tmpdir)
                data = b"Large binary payload test for streaming disk safety" * 100
                stream = MockStreamReader(data)
                res = await dm.save_stream(stream, "files/test.bin", chunk_size=32)

                self.assertTrue(res.local_path.exists())
                self.assertEqual(res.file_size, len(data))
                self.assertEqual(res.local_path.read_bytes(), data)
        asyncio.run(run())

if __name__ == "__main__":
    unittest.main()
