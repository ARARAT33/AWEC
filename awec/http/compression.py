"""HTTP Client, Compression Decompressors, and Dual Hash Calculation Engine."""
from __future__ import annotations

import gzip
import hashlib
import zlib
from dataclasses import dataclass
from typing import Tuple

try:
    import brotli
    HAS_BROTLI = True
except ImportError:
    HAS_BROTLI = False


@dataclass
class DecodedPayload:
    wire_bytes: bytes
    decoded_bytes: bytes
    content_encoding: str
    sha256_wire: str
    sha256_decoded: str
    sha512_wire: str
    sha512_decoded: str


class CompressionDecoder:
    @staticmethod
    def supports_brotli() -> bool:
        return HAS_BROTLI

    @classmethod
    def get_supported_encodings(cls) -> str:
        codecs = ["gzip", "deflate"]
        if HAS_BROTLI:
            codecs.append("br")
        return ", ".join(codecs)

    @classmethod
    def decode(cls, wire_bytes: bytes, encoding_header: str) -> Tuple[bytes, str]:
        enc = (encoding_header or "").strip().lower()
        if not enc or enc == "identity":
            return wire_bytes, "identity"

        if "br" in enc or "brotli" in enc:
            if not HAS_BROTLI:
                raise ValueError("Can not decode content-encoding: brotli (br module missing)")
            try:
                return brotli.decompress(wire_bytes), "br"
            except Exception as e:
                raise ValueError(f"Brotli decompress error: {e}")

        if "gzip" in enc:
            try:
                return gzip.decompress(wire_bytes), "gzip"
            except Exception as e:
                raise ValueError(f"Gzip decompress error: {e}")

        if "deflate" in enc:
            try:
                return zlib.decompress(wire_bytes), "deflate"
            except Exception:
                try:
                    return zlib.decompress(wire_bytes, -zlib.MAX_WBITS), "deflate"
                except Exception as e:
                    raise ValueError(f"Deflate decompress error: {e}")

        return wire_bytes, enc


def process_payload(wire_bytes: bytes, encoding_header: str) -> DecodedPayload:
    decoded_bytes, enc = CompressionDecoder.decode(wire_bytes, encoding_header)

    sha256_wire = hashlib.sha256(wire_bytes).hexdigest()
    sha256_decoded = hashlib.sha256(decoded_bytes).hexdigest()
    sha512_wire = hashlib.sha512(wire_bytes).hexdigest()
    sha512_decoded = hashlib.sha512(decoded_bytes).hexdigest()

    return DecodedPayload(
        wire_bytes=wire_bytes,
        decoded_bytes=decoded_bytes,
        content_encoding=enc,
        sha256_wire=sha256_wire,
        sha256_decoded=sha256_decoded,
        sha512_wire=sha512_wire,
        sha512_decoded=sha512_decoded
    )
