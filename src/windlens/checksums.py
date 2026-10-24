"""Shared file-checksum helper."""

from __future__ import annotations

import hashlib
from pathlib import Path


def file_md5(path: Path) -> str:
    """MD5 hex digest of a file's contents, read in fixed-size chunks."""

    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
