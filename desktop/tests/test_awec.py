"""Unit test suite for AWEC Desktop 3.0 configuration, i18n, visual language editor, anti-blocking, and storage sinks."""
import os
import json
import unittest
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from desktop.config_schema import AWECConfig
from desktop.i18n import LANGUAGES, TRANSLATIONS, get_translation, load_language_pack
from desktop.theme import apply_theme
from desktop.app_window_v2 import AWECMainWindow
from desktop.crawler_engine import AWECrawler, CrawlPolicy
from desktop.storage import LocalSink


class TestAWECDeep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def test_config_schema_deep_settings(self):
        cfg = AWECConfig(
            seeds=["https://example.org"],
            custom_user_agent="TestUserAgent/3.0",
            ua_rotation_enabled=True,
            delay_jitter_sec=0.5,
            cookie_jar_enabled=True,
            max_local_storage_mb=0,
            purge_local_files_after_upload=True
        )
        d = cfg.to_dict()
        self.assertEqual(d["custom_user_agent"], "TestUserAgent/3.0")
        self.assertTrue(d["ua_rotation_enabled"])
        self.assertEqual(d["max_local_storage_mb"], 0)

        tmp_path = Path("awec-state/test_config_deep.json")
        cfg.save(tmp_path)
        self.assertTrue(tmp_path.exists())

        loaded = AWECConfig.load(tmp_path)
        self.assertEqual(loaded.custom_user_agent, "TestUserAgent/3.0")
        self.assertEqual(loaded.max_local_storage_mb, 0)
        if tmp_path.exists():
            tmp_path.unlink()

    def test_i18n_and_language_pack(self):
        t_hy = get_translation("hy")
        self.assertIn("lang_editor", t_hy)
        self.assertIn("Խմբագրիչ", t_hy["lang_editor"])

    def test_visual_language_table_editor(self):
        win = AWECMainWindow()
        win.show()

        # Test dynamic translation re-render
        win.on_language_changed(1)  # hy
        self.assertIn("Վեբ", win.windowTitle())

        # Edit key in visual editor table
        item_val = win.table_lang.item(0, 1)
        if item_val:
            item_val.setText("Edited Custom Title")

        win.close()

    def test_dashboard_quick_seed_scan(self):
        win = AWECMainWindow()
        win.dash_seed_input.setText("https://example.org")
        cfg = win.build_config_from_ui()
        self.assertIn("https://example.org", cfg.seeds)
        win.close()

    def test_storage_sink_zero_quota(self):
        sink = LocalSink("fallback_test", max_storage_mb=0)
        res = sink.put("test.com", "https://test.com/img.png", b"1234")
        self.assertIsNone(res)

    def test_crawler_engine_header_generation(self):
        policy = CrawlPolicy(ua_rotation=True, auto_headers=True)
        crawler = AWECrawler([], policy)
        headers = crawler.get_headers()
        self.assertIn("User-Agent", headers)
        self.assertIn("Sec-Fetch-Dest", headers)


if __name__ == "__main__":
    unittest.main()
