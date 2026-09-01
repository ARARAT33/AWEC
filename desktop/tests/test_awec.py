"""Unit test suite for AWEC Desktop 3.0 configuration, i18n, theme, and UI components."""
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
from desktop.awec_desktop import Engine, Config


class TestAWEC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def test_config_schema_serialization(self):
        cfg = AWECConfig(
            seeds=["https://example.org"],
            custom_user_agent="TestUserAgent/1.0",
            proxy_url="http://127.0.0.1:8080",
            workers=64,
            max_depth=5
        )
        d = cfg.to_dict()
        self.assertEqual(d["seeds"], ["https://example.org"])
        self.assertEqual(d["custom_user_agent"], "TestUserAgent/1.0")
        self.assertEqual(d["workers"], 64)

        tmp_path = Path("awec-state/test_config.json")
        cfg.save(tmp_path)
        self.assertTrue(tmp_path.exists())

        loaded = AWECConfig.load(tmp_path)
        self.assertEqual(loaded.custom_user_agent, "TestUserAgent/1.0")
        self.assertEqual(loaded.workers, 64)
        if tmp_path.exists():
            tmp_path.unlink()

    def test_i18n_translations(self):
        self.assertIn("en", LANGUAGES)
        self.assertIn("hy", LANGUAGES)

        t_en = get_translation("en")
        t_hy = get_translation("hy")

        self.assertIn("title", t_en)
        self.assertIn("title", t_hy)
        self.assertIn("Վեբ", t_hy["title"])

    def test_ui_window_instantiation(self):
        win = AWECMainWindow()
        self.assertIsNotNone(win)
        win.show()

        # Test language change
        win.on_language_changed(1) # hy
        self.assertIn("Վեբ", win.windowTitle())

        # Test site addition
        win.site_input.setText("https://testdomain.org")
        win.add_seed_site()
        self.assertEqual(win.site_list_widget.count(), 1)
        self.assertEqual(win.site_list_widget.item(0).text(), "https://testdomain.org")

        # Test config generation from UI
        cfg = win.build_config_from_ui()
        self.assertIn("https://testdomain.org", cfg.seeds)
        win.close()

    def test_engine_initialization(self):
        cfg = Config(seeds=["https://example.com"], workers=4, max_depth=2)
        engine = Engine(cfg)
        self.assertIsNotNone(engine)
        self.assertEqual(engine.cfg.workers, 4)


if __name__ == "__main__":
    unittest.main()
