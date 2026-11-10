"""Artifact & input ingestion: validation, size quotas, SHA-256, content-addressed
immutable storage, and provenance metadata."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import config
from contracts import Artifact

MAGIC = {
    b"\x7fELF": "application/x-elf",
    b"MZ": "application/x-dosexec",
    b"\xcf\xfa\xed\xfe": "application/x-mach-binary",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_media_type(data: bytes) -> str:
    for magic, mt in MAGIC.items():
        if data.startswith(magic):
            return mt
    # crude text vs binary heuristic for sample data (CSV, etc.)
    try:
        data[:4096].decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        return "application/octet-stream"


class IngestError(ValueError):
    pass


def ingest_artifact(data: bytes, filename: str) -> Artifact:
    if not data:
        raise IngestError("empty artifact")
    if len(data) > config.MAX_ARTIFACT_BYTES:
        raise IngestError(f"artifact exceeds quota ({len(data)} > {config.MAX_ARTIFACT_BYTES} bytes)")
    config.ensure_dirs()
    digest = sha256_bytes(data)
    stored = config.ARTIFACT_STORE / digest  # content-addressed, immutable
    if not stored.exists():
        stored.write_bytes(data)
    # read + execute, no write: immutable but runnable by the sandbox (as nobody)
    stored.chmod(0o555)
    return Artifact(
        id=f"art_{uuid.uuid4().hex[:12]}",
        filename=filename,
        sha256=digest,
        size_bytes=len(data),
        media_type=detect_media_type(data),
        stored_path=str(stored),
    )


def ingest_input(data: bytes) -> tuple[str, str]:
    """Store an execution input immutably. Returns (sha256, stored_path)."""
    if len(data) > config.MAX_INPUT_BYTES:
        raise IngestError(f"input exceeds quota ({len(data)} > {config.MAX_INPUT_BYTES} bytes)")
    config.ensure_dirs()
    digest = sha256_bytes(data)
    stored = config.INPUT_STORE / f"{digest}.input"
    if not stored.exists():
        stored.write_bytes(data)
        stored.chmod(0o444)
    return digest, str(stored)
