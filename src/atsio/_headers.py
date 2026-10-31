# SPDX-FileCopyrightText: 2026 Stichting Delft Drones Initiative
#
# SPDX-License-Identifier: Apache-2.0
"""The 1024-byte binary header of a Metronix .ats file.

``AtsHeader`` is the single source of truth for the layout: every field carries its
``struct`` code, and ``ATS_HEADER_FIELDS`` / ``_FMT`` are derived from the class.
Fields are declared in byte order. Do NOT reorder, insert or remove fields.
"""

from __future__ import annotations

import dataclasses
import json
import struct
from dataclasses import astuple, fields
from pathlib import Path

from ._errors import AtsFormatError
from ._metadata import AtsHeader

# Derived from the class: the class is the layout.
ATS_HEADER_FIELDS: list[tuple[str, str]] = [
    (fl.name, fl.metadata["fmt"]) for fl in fields(AtsHeader)
]
_FMT = "<" + "".join(code for _, code in ATS_HEADER_FIELDS)
ATS_HEADER_BYTES = struct.calcsize(_FMT)
if ATS_HEADER_BYTES != 1024:
    raise RuntimeError(f"ATS header layout is {ATS_HEADER_BYTES} bytes, expected 1024")


def header_from_bytes(raw: bytes) -> AtsHeader:
    """Decode the first 1024 bytes of an .ats file."""
    if len(raw) < ATS_HEADER_BYTES:
        raise AtsFormatError(f"header is {len(raw)} bytes, expected {ATS_HEADER_BYTES}")
    values = []
    for (_, code), value in zip(
        ATS_HEADER_FIELDS, struct.unpack(_FMT, raw[:ATS_HEADER_BYTES]), strict=False
    ):
        if code.endswith("s"):
            value = value.split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
        values.append(value)
    return AtsHeader(*values)


def header_to_bytes(hdr: AtsHeader) -> bytes:
    """Encode back to 1024 bytes (strings NUL-padded), e.g. for writing test files."""
    values = [v.encode("utf-8") if isinstance(v, str) else v for v in astuple(hdr)]
    return struct.pack(_FMT, *values)

def header_to_dict(hdr: AtsHeader) -> dict:
    """All fields, with float32 fields shown at their real precision (7 significant digits)."""
    codes = dict(ATS_HEADER_FIELDS)
    return {k: (float(f"{v:.7g}") if codes[k] == "f" else v)
            for k, v in dataclasses.asdict(hdr).items()}


def header_from_dict(d: dict) -> AtsHeader:
    """Inverse of header_to_dict; unknown keys are ignored, missing keys raise."""
    names = {f.name for f in dataclasses.fields(AtsHeader)}
    return AtsHeader(**{k: v for k, v in d.items() if k in names})


def write_header_json(hdr: AtsHeader, path: str | Path) -> None:
    Path(path).write_text(json.dumps(header_to_dict(hdr), indent=2, ensure_ascii=False),
                          encoding="utf-8")