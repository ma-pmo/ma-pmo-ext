"""Stream documents out of a `mongodump --gzip --archive` file, without MongoDB.

The archive is gzip around: a magic number, a prelude (one BSON document, then one per
collection), a terminator, then blocks. Each block is a namespace header (`db`, `collection`,
`EOF`, `CRC`) followed by that collection's documents and a terminator; mongodump interleaves the
blocks of several collections. A terminator is the int32 -1.

Accepts the archive itself or the dataset's zip, which holds it as one member.
"""
from __future__ import annotations

import gzip
import struct
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

MAGIC = b"\x6d\xe2\x99\x81"
TERMINATOR = -1


class DumpError(ValueError):
    """The file is not a mongodump archive, or it ends mid-document."""


def _bson() -> Any:
    try:
        import bson
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise ImportError(
            'reading the dump needs pymongo\'s bson: pip install "ma-pmo[benchmark]"'
        ) from e
    return bson


def _open(path: Path) -> IO[bytes]:
    if zipfile.is_zipfile(path):
        z = zipfile.ZipFile(path)
        members = [n for n in z.namelist() if n.endswith(".archive")]
        if len(members) != 1:
            raise DumpError(f"{path}: expected one .archive member, found {len(members)}")
        return z.open(members[0])
    return open(path, "rb")


def _read(stream: gzip.GzipFile, n: int) -> bytes:
    data = stream.read(n)
    if len(data) != n:
        raise DumpError("archive ends mid-document (incomplete download?)")
    return data


def iter_documents(path: str | Path) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield `(collection, document)` for every document in the dump, in archive order."""
    bson = _bson()
    stream = gzip.GzipFile(fileobj=_open(Path(path)))
    try:
        if stream.read(4) != MAGIC:
            raise DumpError(f"{path}: not a mongodump archive")
        in_prelude, expect_header, collection = True, False, ""
        while True:
            head = stream.read(4)
            if not head:
                return
            if len(head) < 4:
                raise DumpError("archive ends mid-document (incomplete download?)")
            (size,) = struct.unpack("<i", head)
            if size == TERMINATOR:
                in_prelude, expect_header = False, True
                continue
            doc = bson.decode(head + _read(stream, size - 4))
            if in_prelude:
                continue
            if expect_header:
                collection, expect_header = doc["collection"], False
                continue
            yield collection, doc
    except (EOFError, gzip.BadGzipFile) as e:
        raise DumpError(f"archive is truncated or corrupt: {e}") from e
    finally:
        stream.close()
