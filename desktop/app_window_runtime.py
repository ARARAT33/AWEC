"""Runtime bridge for AWEC Desktop UI v4.

The existing Engine constructs IAUploader from its config.  This bridge passes
interactive IA destination fields to that uploader without changing the engine
API, while keeping secrets out of the saved Git repository.
"""
from __future__ import annotations

import os

from desktop.app_window_v4 import AWECMainWindow as _AWECMainWindow


class AWECMainWindow(_AWECMainWindow):
    def start_crawl(self):
        os.environ["AWEC_IA_COLLECTION"] = self.ia_collection.text().strip()
        os.environ["AWEC_IA_TITLE"] = self.ia_title.text().strip()
        os.environ["AWEC_IA_CREATOR"] = self.ia_creator.text().strip()
        os.environ["AWEC_IA_DESCRIPTION"] = self.ia_desc.toPlainText().strip()
        return super().start_crawl()
