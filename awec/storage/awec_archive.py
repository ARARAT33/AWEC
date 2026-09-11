"""AWEC Secure Archive Module - Custom encrypted .awec format handling."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Dict, Tuple, Any, Optional
from datetime import datetime
import hashlib


class AWECSecurity:
    """Handles encryption/decryption for .awec files using XOR cipher."""
    
    # Secret key for XOR encryption - changing this breaks compatibility
    MAGIC_KEY = b"AWEC_SECRET_XOR_KEY_2024_SECURE_ARCHIVE_v3"
    MAGIC_HEADER = b"AWEC\x00\x01"  # File signature
    
    @staticmethod
    def xor_cipher(data: bytes, key: bytes) -> bytes:
        """Apply XOR encryption/decryption."""
        return bytes([b ^ key[i % len(key)] for i, b in enumerate(data)])
    
    @staticmethod
    def compute_signature(data: bytes) -> str:
        """Compute SHA-256 signature for integrity verification."""
        return hashlib.sha256(data).hexdigest()
    
    @staticmethod
    def create_awec_package(
        zip_data: bytes,
        metadata: Dict[str, Any],
        password: Optional[str] = None
    ) -> bytes:
        """
        Create a secure .awec package.
        
        Structure:
        [MAGIC_HEADER (6 bytes)]
        [Metadata Length (4 bytes, big-endian)]
        [Metadata JSON (variable)]
        [Signature (64 bytes, hex-encoded SHA-256 of encrypted content)]
        [Encrypted ZIP Data (variable)]
        
        Returns the complete binary package.
        """
        # Prepare metadata
        meta_dict = {
            **metadata,
            "created_at": datetime.now().isoformat(),
            "format_version": "3.0",
            "software": "AWEC Crawler v3.0"
        }
        meta_json = json.dumps(meta_dict, indent=2).encode('utf-8')
        meta_len = len(meta_json).to_bytes(4, byteorder='big')
        
        # Encrypt the ZIP content
        encrypted_content = AWECSecurity.xor_cipher(zip_data, AWECSecurity.MAGIC_KEY)
        
        # Compute signature of encrypted content
        signature = AWECSecurity.compute_signature(encrypted_content).encode('ascii')
        
        # Build final package
        package = (
            AWECSecurity.MAGIC_HEADER +
            meta_len +
            meta_json +
            signature +
            encrypted_content
        )
        
        return package
    
    @staticmethod
    def open_awec_package(file_path: str | Path) -> Tuple[Dict[str, Any], bytes]:
        """
        Open and decrypt a .awec file.
        
        Returns: (metadata_dict, zip_bytes)
        Raises: ValueError if file is invalid or corrupted
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"AWEC file not found: {file_path}")
        
        with open(file_path, 'rb') as f:
            data = f.read()
        
        # Verify magic header
        if len(data) < len(AWECSecurity.MAGIC_HEADER):
            raise ValueError("Invalid AWEC file: too small")
        
        header = data[:len(AWECSecurity.MAGIC_HEADER)]
        if header != AWECSecurity.MAGIC_HEADER:
            raise ValueError(
                "Invalid AWEC file: incorrect signature. "
                "This file may be corrupted or not an AWEC archive. "
                "Renaming .zip to .awec will not work - AWEC files are encrypted."
            )
        
        # Parse structure
        offset = len(AWECSecurity.MAGIC_HEADER)
        
        # Read metadata length
        meta_len = int.from_bytes(data[offset:offset+4], byteorder='big')
        offset += 4
        
        # Read metadata
        meta_json = data[offset:offset+meta_len]
        offset += meta_len
        
        # Read signature
        signature = data[offset:offset+64].decode('ascii')
        offset += 64
        
        # Read encrypted content
        encrypted_content = data[offset:]
        
        # Verify signature
        computed_sig = AWECSecurity.compute_signature(encrypted_content)
        if computed_sig != signature:
            raise ValueError("AWEC file integrity check failed: signature mismatch")
        
        # Decrypt content
        zip_data = AWECSecurity.xor_cipher(encrypted_content, AWECSecurity.MAGIC_KEY)
        
        # Verify ZIP structure
        try:
            zipfile.ZipFile(io.BytesIO(zip_data))
        except zipfile.BadZipFile:
            raise ValueError("Decryption successful but ZIP content is invalid")
        
        metadata = json.loads(meta_json.decode('utf-8'))
        
        return metadata, zip_data
    
    @staticmethod
    def extract_awec_to_directory(file_path: str | Path, output_dir: str | Path) -> Dict[str, Any]:
        """
        Extract .awec file contents to a directory.
        
        Returns: metadata dictionary
        """
        metadata, zip_data = AWECSecurity.open_awec_package(file_path)
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            zf.extractall(output_dir)
        
        return metadata
    
    @staticmethod
    def verify_awec_file(file_path: str | Path) -> Tuple[bool, str]:
        """
        Verify if a file is a valid .awec archive without extracting.
        
        Returns: (is_valid, message)
        """
        try:
            metadata, _ = AWECSecurity.open_awec_package(file_path)
            return True, f"Valid AWEC file. Pages: {metadata.get('page_count', 'unknown')}"
        except Exception as e:
            return False, str(e)
