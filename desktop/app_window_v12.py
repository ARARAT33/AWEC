"""AWEC Desktop v12 — Ultimate Secure Crawler with .AWEC encrypted archives.

v12 adds:
- High-performance async crawler with anti-bot protection
- Secure .awec file format (XOR encrypted, signed)
- Cannot be opened by renaming - requires AWEC App
- Modern dark UI with real-time crawl visualization
- Smart URL discovery and depth-limited crawling
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import random
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse, urljoin

import aiohttp
from bs4 import BeautifulSoup
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QFont, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QSpinBox, QTextEdit, QFileDialog,
    QMessageBox, QProgressBar, QGroupBox, QComboBox, QSplitter,
    QFrame, QScrollArea, QStatusBar, QToolBar
)

from awec.storage.awec_archive import AWECSecurity


class CrawlerWorker(QThread):
    """Async crawler worker thread."""
    
    log_signal = Signal(str)
    progress_signal = Signal(int, int)
    finished_signal = Signal(dict, dict)
    error_signal = Signal(str)
    
    def __init__(self, start_url: str, max_pages: int, max_depth: int = 2):
        super().__init__()
        self.start_url = start_url
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.visited: Set[str] = set()
        self.crawled_data: Dict[str, dict] = {}
        self.stop_flag = False
    
    @Slot()
    def run(self):
        """Run the crawler."""
        try:
            asyncio.run(self._crawl())
        except Exception as e:
            self.error_signal.emit(str(e))
    
    async def _crawl(self):
        """Main crawl logic."""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        
        connector = aiohttp.TCPConnector(limit=10, ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            queue = asyncio.Queue()
            await queue.put((self.start_url, 0))
            
            while not queue.empty() and len(self.crawled_data) < self.max_pages and not self.stop_flag:
                url, depth = await queue.get()
                
                if url in self.visited or depth > self.max_depth:
                    queue.task_done()
                    continue
                
                self.visited.add(url)
                self.log_signal.emit(f"[CRAWLING] {url} (depth={depth})")
                
                # Anti-bot: random delay
                await asyncio.sleep(random.uniform(1.0, 2.5))
                
                headers = {
                    "User-Agent": random.choice(user_agents),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                }
                
                try:
                    async with session.get(url, headers=headers, allow_redirects=True) as response:
                        html = await response.text()
                        status = response.status
                        
                        if status == 200:
                            filename = hashlib.md5(url.encode()).hexdigest() + ".html"
                            self.crawled_data[filename] = {
                                "url": url,
                                "content": html,
                                "status": status,
                                "timestamp": datetime.now().isoformat(),
                                "size": len(html)
                            }
                            
                            self.log_signal.emit(f"[SUCCESS] {url} ({len(html)} bytes)")
                            self.progress_signal.emit(len(self.crawled_data), self.max_pages)
                            
                            # Extract links for next depth
                            if depth < self.max_depth:
                                links = self._extract_links(html, url)
                                for link in links:
                                    if link not in self.visited:
                                        await queue.put((link, depth + 1))
                        else:
                            self.log_signal.emit(f"[WARN] HTTP {status} for {url}")
                
                except Exception as e:
                    self.log_signal.emit(f"[ERROR] {url}: {str(e)}")
                
                queue.task_done()
        
        metadata = {
            "source_url": self.start_url,
            "crawl_date": datetime.now().isoformat(),
            "page_count": len(self.crawled_data),
            "software": "AWEC Desktop v12.0",
            "max_depth": self.max_depth
        }
        
        self.finished_signal.emit(self.crawled_data, metadata)
    
    def _extract_links(self, html: str, base_url: str) -> List[str]:
        """Extract links from HTML."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            links = []
            base_parsed = urlparse(base_url)
            base_domain = base_parsed.netloc
            
            for tag in soup.find_all('a', href=True):
                href = tag['href'].strip()
                
                # Skip anchors, javascript, mailto
                if href.startswith(('#', 'javascript:', 'mailto:', 'data:')):
                    continue
                
                # Absolute URL
                if href.startswith('http://') or href.startswith('https://'):
                    parsed = urlparse(href)
                    if parsed.netloc == base_domain:
                        links.append(href)
                # Relative URL
                elif href.startswith('/'):
                    links.append(f"{base_parsed.scheme}://{base_domain}{href}")
                else:
                    links.append(urljoin(base_url, href))
            
            return list(set(links))
        except Exception:
            return []
    
    def stop(self):
        """Stop the crawler."""
        self.stop_flag = True


class AWECDesktopV12(QMainWindow):
    """AWEC Desktop v12 - Ultimate Secure Crawler."""
    
    def __init__(self):
        super().__init__()
        self.worker: Optional[CrawlerWorker] = None
        self.current_zip_buffer: Optional[bytes] = None
        self.last_metadata: Optional[dict] = None
        
        self._setup_ui()
        self._apply_styles()
    
    def _setup_ui(self):
        """Setup the user interface."""
        self.setWindowTitle("AWEC Desktop v12 - Ultimate Secure Crawler")
        self.setGeometry(100, 100, 1100, 800)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 15)
        
        title_label = QLabel("🔒 AWEC v12 SECURE CRAWLER")
        title_label.setObjectName("titleLabel")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        subtitle_label = QLabel("Encrypted .awec Archive Format")
        subtitle_label.setObjectName("subtitleLabel")
        header_layout.addWidget(subtitle_label)
        
        main_layout.addWidget(header_frame)
        
        # Input section
        input_group = QGroupBox("🎯 Target Configuration")
        input_group.setObjectName("inputGroup")
        input_layout = QVBoxLayout(input_group)
        
        # URL input
        url_layout = QHBoxLayout()
        url_label = QLabel("Target URL:")
        url_label.setMinimumWidth(80)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com")
        self.url_input.setText("https://example.com")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input, 1)
        input_layout.addLayout(url_layout)
        
        # Options row
        options_layout = QHBoxLayout()
        
        # Max pages
        pages_label = QLabel("Max Pages:")
        self.pages_spin = QSpinBox()
        self.pages_spin.setRange(1, 1000)
        self.pages_spin.setValue(10)
        self.pages_spin.setFixedWidth(80)
        options_layout.addWidget(pages_label)
        options_layout.addWidget(self.pages_spin)
        
        # Max depth
        depth_label = QLabel("Crawl Depth:")
        self.depth_spin = QSpinBox()
        self.depth_spin.setRange(0, 5)
        self.depth_spin.setValue(2)
        self.depth_spin.setFixedWidth(60)
        options_layout.addWidget(depth_label)
        options_layout.addWidget(self.depth_spin)
        
        options_layout.addStretch()
        input_layout.addLayout(options_layout)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("🚀 START CRAWL")
        self.start_btn.setObjectName("startButton")
        self.start_btn.setFixedHeight(45)
        self.start_btn.clicked.connect(self._start_crawl)
        btn_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("⏹ STOP")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setFixedHeight(45)
        self.stop_btn.clicked.connect(self._stop_crawl)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)
        
        btn_layout.addStretch()
        input_layout.addLayout(btn_layout)
        
        main_layout.addWidget(input_group)
        
        # Progress section
        progress_group = QGroupBox("📊 Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setObjectName("progressBar")
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ready to crawl")
        self.status_label.setObjectName("statusLabel")
        progress_layout.addWidget(self.status_label)
        
        main_layout.addWidget(progress_group)
        
        # Actions section
        actions_group = QGroupBox("📦 Archive Actions")
        actions_layout = QHBoxLayout(actions_group)
        
        self.save_btn = QPushButton("💾 SAVE AS .AWEC")
        self.save_btn.setObjectName("saveButton")
        self.save_btn.clicked.connect(self._save_awec)
        self.save_btn.setEnabled(False)
        actions_layout.addWidget(self.save_btn)
        
        self.open_btn = QPushButton("📂 OPEN .AWEC FILE")
        self.open_btn.setObjectName("openButton")
        self.open_btn.clicked.connect(self._open_awec)
        actions_layout.addWidget(self.open_btn)
        
        self.verify_btn = QPushButton("✓ VERIFY .AWEC")
        self.verify_btn.clicked.connect(self._verify_awec)
        actions_layout.addWidget(self.verify_btn)
        
        actions_layout.addStretch()
        main_layout.addWidget(actions_group)
        
        # Log section
        log_group = QGroupBox("📝 Crawl Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setObjectName("logText")
        self.log_text.setFont(QFont("Consolas", 10))
        log_layout.addWidget(self.log_text)
        
        main_layout.addWidget(log_group, 1)
        
        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("AWEC v12 Ready | Secure .awec format enabled")
    
    def _apply_styles(self):
        """Apply modern dark theme styles."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QFrame#headerFrame {
                background-color: #2d2d2d;
                border-radius: 10px;
                padding: 10px;
            }
            QLabel#titleLabel {
                font-size: 24px;
                font-weight: bold;
                color: #007acc;
            }
            QLabel#subtitleLabel {
                font-size: 12px;
                color: #888888;
            }
            QGroupBox {
                font-weight: bold;
                color: #ffffff;
                border: 2px solid #3d3d3d;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: #007acc;
            }
            QLineEdit, QSpinBox {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #3d3d3d;
                border-radius: 5px;
                padding: 8px;
                font-size: 13px;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #007acc;
            }
            QPushButton#startButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 30px;
            }
            QPushButton#startButton:hover {
                background-color: #005f9e;
            }
            QPushButton#stopButton {
                background-color: #c0392b;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 30px;
            }
            QPushButton#stopButton:hover {
                background-color: #a93226;
            }
            QPushButton#saveButton, QPushButton#openButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
                padding: 10px 20px;
            }
            QPushButton#saveButton:hover, QPushButton#openButton:hover {
                background-color: #219a52;
            }
            QPushButton#saveButton:disabled, QPushButton#openButton:disabled {
                background-color: #555555;
                color: #888888;
            }
            QProgressBar#progressBar {
                border: 1px solid #3d3d3d;
                border-radius: 5px;
                text-align: center;
                background-color: #2d2d2d;
                height: 25px;
            }
            QProgressBar#progressBar::chunk {
                background-color: #007acc;
                border-radius: 4px;
            }
            QLabel#statusLabel {
                color: #cccccc;
                font-size: 13px;
                padding: 5px;
            }
            QTextEdit#logText {
                background-color: #1a1a1a;
                color: #00ff00;
                border: 1px solid #3d3d3d;
                border-radius: 5px;
                padding: 10px;
            }
            QScrollBar:vertical {
                background-color: #2d2d2d;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #555555;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
    
    def _log(self, message: str):
        """Add message to log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
        QApplication.processEvents()
    
    def _start_crawl(self):
        """Start crawling."""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a URL")
            return
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            self.url_input.setText(url)
        
        max_pages = self.pages_spin.value()
        max_depth = self.depth_spin.value()
        
        self._log(f"Starting crawl: {url} (max_pages={max_pages}, depth={max_depth})")
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.save_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Crawling in progress...")
        
        self.worker = CrawlerWorker(url, max_pages, max_depth)
        self.worker.log_signal.connect(self._log)
        self.worker.progress_signal.connect(self._update_progress)
        self.worker.finished_signal.connect(self._on_crawl_finished)
        self.worker.error_signal.connect(self._on_crawl_error)
        self.worker.start()
    
    def _stop_crawl(self):
        """Stop crawling."""
        if self.worker:
            self.worker.stop()
            self._log("Stopping crawler...")
            self.stop_btn.setEnabled(False)
    
    def _update_progress(self, current: int, total: int):
        """Update progress bar."""
        percent = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(percent)
        self.status_label.setText(f"Crawled {current}/{total} pages")
    
    def _on_crawl_finished(self, data: dict, metadata: dict):
        """Handle crawl completion."""
        self._log(f"Crawl finished! {len(data)} pages captured.")
        self.status_label.setText(f"Complete: {len(data)} pages")
        self.progress_bar.setValue(100)
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.save_btn.setEnabled(True)
        
        # Create ZIP buffer
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for filename, info in data.items():
                zf.writestr(filename, info['content'])
                # Also save metadata JSON
                meta_filename = filename.replace('.html', '.meta.json')
                zf.writestr(meta_filename, json.dumps(info, indent=2))
        
        self.current_zip_buffer = buffer.getvalue()
        self.last_metadata = metadata
        
        self.statusBar.showMessage(f"Crawl complete: {len(data)} pages ready to save")
    
    def _on_crawl_error(self, error: str):
        """Handle crawl error."""
        self._log(f"ERROR: {error}")
        self.status_label.setText("Error occurred")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.statusBar.showMessage("Crawl failed")
    
    def _save_awec(self):
        """Save as encrypted .awec file."""
        if not self.current_zip_buffer:
            QMessageBox.warning(self, "Error", "No data to save")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save AWEC Archive",
            "",
            "AWEC Secure Archive (*.awec)"
        )
        
        if not file_path:
            return
        
        if not file_path.endswith('.awec'):
            file_path += '.awec'
        
        try:
            # Create encrypted package
            package = AWECSecurity.create_awec_package(
                self.current_zip_buffer,
                self.last_metadata or {}
            )
            
            # Write to file
            with open(file_path, 'wb') as f:
                f.write(package)
            
            self._log(f"Saved encrypted archive: {file_path}")
            self._log(f"Package size: {len(package):,} bytes")
            
            QMessageBox.information(
                self,
                "Success",
                f"Archive saved successfully!\n\n"
                f"📁 File: {file_path}\n"
                f"📊 Size: {len(package):,} bytes\n"
                f"🔒 Encrypted with AWEC security\n\n"
                f"⚠️ IMPORTANT: This file CANNOT be opened by renaming to .zip\n"
                f"   It must be opened with AWEC Desktop app."
            )
            
            self.statusBar.showMessage(f"Saved: {Path(file_path).name}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {str(e)}")
            self._log(f"Save error: {str(e)}")
    
    def _open_awec(self):
        """Open .awec file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open AWEC Archive",
            "",
            "AWEC Files (*.awec)"
        )
        
        if not file_path:
            return
        
        try:
            # Decrypt and extract
            metadata, zip_data = AWECSecurity.open_awec_package(file_path)
            
            self._log(f"Opened: {file_path}")
            self._log(f"Metadata: {json.dumps(metadata, indent=2)}")
            
            # Ask where to extract
            output_dir = QFileDialog.getExistingDirectory(
                self,
                "Select Extraction Directory"
            )
            
            if output_dir:
                AWECSecurity.extract_awec_to_directory(file_path, output_dir)
                self._log(f"Extracted to: {output_dir}")
                
                QMessageBox.information(
                    self,
                    "Success",
                    f"Archive decrypted and extracted!\n\n"
                    f"📂 Location: {output_dir}\n"
                    f"📄 Pages: {metadata.get('page_count', 'unknown')}\n"
                    f"🌐 Source: {metadata.get('source_url', 'unknown')}"
                )
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Decryption Failed",
                f"Cannot open this file:\n\n{str(e)}\n\n"
                f"This might not be a valid .awec file, or it may be corrupted.\n"
                f"Remember: Simply renaming a .zip file to .awec will NOT work."
            )
            self._log(f"Open error: {str(e)}")
    
    def _verify_awec(self):
        """Verify .awec file integrity."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Verify AWEC File",
            "",
            "AWEC Files (*.awec)"
        )
        
        if not file_path:
            return
        
        is_valid, message = AWECSecurity.verify_awec_file(file_path)
        
        if is_valid:
            QMessageBox.information(self, "Valid", f"✓ Valid AWEC file\n\n{message}")
            self._log(f"Verified: {file_path} - VALID")
        else:
            QMessageBox.warning(self, "Invalid", f"✗ Invalid AWEC file\n\n{message}")
            self._log(f"Verified: {file_path} - INVALID: {message}")


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Set dark palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.Base, QColor(45, 45, 45))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.BrightText, QColor(0, 122, 204))
    palette.setColor(QPalette.Highlight, QColor(0, 122, 204))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    
    window = AWECDesktopV12()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
