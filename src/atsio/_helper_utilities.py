import json
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

from ._errors import AtsFormatError
from ._metadata import AtsHeader, AtssMeta
from ._headers import ATS_HEADER_BYTES

CHUNK = 1 << 20  # samples per write: ~8 MB of float64

log = logging.getLogger(__name__)


def is_electric(ct: str) -> bool:
    return ct in ("Ex", "Ey", "Ez")


def lsb_and_units(hdr: AtsHeader, ct: str) -> tuple[float, str]:
    """mV per count, and the units of the scaled data.

    E channels with a dipole length are scaled to mV/km (MTHotel can_and_want_scale).
    """
    length = hdr.dipole_length_from_positions
    if is_electric(ct) and length > 0.0:
        return hdr.lsbval * (1000.0 / length), "mV/km"  # same operation order as MTHotel
    return hdr.lsbval, "mV"


def azimuth(hdr: AtsHeader, ct: str) -> float:
    """Direction North -> East in degrees, from the positions (MTHotel pos2azimuth).

    Coils without positions get the MT defaults Hx = 0, Hy = 90, Hz = 0.
    Difference to MTHotel: negative angles are wrapped to [0, 360) (-90 -> 270).
    """
    tx, ty = hdr.x2 - hdr.x1, hdr.y2 - hdr.y1
    tx = 0.0 if abs(tx) < 0.001 else tx
    ty = 0.0 if abs(ty) < 0.001 else ty
    if hdr.dipole_length_from_positions == 0.0:
        return {"Hy": 90.0}.get(ct, 0.0)
    if tx == 0.0 and ty == 0.0:
        return 0.0
    ang = math.degrees(math.atan2(ty, tx)) % 360.0
    for snap in (0.0, 90.0, 180.0, 270.0, 360.0):
        if abs(ang - snap) < 0.01:
            return snap % 360.0
    return ang


def tilt(hdr: AtsHeader, ct: str) -> float:
    """Degrees from horizontal, positive down (MTHotel pos2tilt). Hz without positions = 90."""
    length = hdr.dipole_length_from_positions
    if length == 0.0:
        return 90.0 if ct == "Hz" else 0.0
    tz = hdr.z2 - hdr.z1
    if tz < 0.001:
        return 0.0
    ang = 90.0 - math.degrees(math.acos(tz / length))
    return 90.0 if abs(ang - 90.0) < 0.01 else ang


# ----------------------------------------------------------------------------- filters

# MTHotel set_filter_bank: bit values per system (mt_base.hpp enum ADU)
_LF_BITS = {
    "ADU-07e": {
        1: "LF-RF-1",
        2: "LF-RF-2",
        4: "LF-RF-3",
        8: "LF-RF-4",
        16: "LF-LP-4Hz",
        32: "MF-RF-1",
        64: "MF-RF-2",
    },
    "ADU-08e": {1: "LF-RF-1", 2: "LF-RF-2", 16: "LF-LP-4Hz"},
}
_HF_BITS = {"ADU-07e": {1: "HF-HP-1Hz"}, "ADU-08e": {2: "HF-HP-500Hz"}}
_GAINS = (1, 4, 8, 16, 32, 64)  # the gain tokens MTHotel's set_filter accepts


def _decode_bits(value: int, bits: dict[int, str]) -> list[str]:
    value &= 0xFF  # stored as a signed byte
    return [name for bit, name in sorted(bits.items()) if value & bit]


def filter_string(hdr: AtsHeader, system: str, *, extra: str = "") -> str:
    """The JSON 'filter' value, token order as MTHotel's channel::set_filter:

    board, radio filters, 4 Hz low-pass, high-pass, divider, gains, osr.
    ``extra`` is a comma-separated list from another source (e.g. the XML
    ``filter_type``) used when the header bits are empty.
    Difference to MTHotel: gain 16 is written as gain_x_16 (MTHotel's substring
    match turns it into gain_x_1).
    """
    lf = _decode_bits(hdr.LF_filters, _LF_BITS.get(system, {}))
    hf = _decode_bits(hdr.HF_filters, _HF_BITS.get(system, {}))
    if not lf and not hf and extra:
        lf = [t.strip().replace("_", "-") for t in extra.split(",") if t.strip()]

    tokens: list[str] = []
    if system != "ADU-11e" and hdr.ADB_board_type in ("LF", "HF", "MF"):
        tokens.append(f"ADB-{hdr.ADB_board_type}")
    tokens += [t for t in lf if "-RF-" in t]
    tokens += [t for t in lf if t == "LF-LP-4Hz"]
    tokens += hf
    tokens.append("div-8" if hdr.InputDivOn == 1 else "div-1")
    for stage, gain in ((1, hdr.gain_stage1), (2, hdr.gain_stage2)):
        if int(gain) in _GAINS:
            tokens.append(f"gain_{stage}_{int(gain)}")
    if hdr.orig_sample_rate > 0:
        tokens.append(f"osr_{hdr.orig_sample_rate:g}")
    return ",".join(tokens)


# ----------------------------------------------------------------------------- naming


def sample_rate_str(sample_rate: float) -> str:
    """524288 -> '524288Hz', 0.25 -> '4s' (MTHotel filename convention)."""
    if sample_rate > 0.999999:
        return f"{round(sample_rate)}Hz"
    return f"{round(1.0 / sample_rate)}s"


def atss_basename(hdr: AtsHeader, system: str, ct: str) -> str:
    """'217_ADU-08e_C002_THx_524288Hz' (no extension)."""
    return (
        f"{hdr.serial_number:03d}_{system}_C{hdr.channel_number:03d}"
        f"_T{ct}_{sample_rate_str(hdr.sample_rate)}"
    )


# MTHotel atsfile.hpp: ats_sys_names (keys compared lower-case)
SYSTEM_NAMES = {
    "adu06": "ADU-06",
    "adu07": "ADU-07e",
    "adu08": "ADU-08e",
    "adu09": "ADU-09u",
    "adu10": "ADU-10e",
    "adu11": "ADU-11e",
    "adu12": "ADU-12e",
    "adu07e": "ADU-07e",
    "adu08e": "ADU-08e",
    "adu10e": "ADU-10e",
    "adu11e": "ADU-11e",
    "adu12e": "ADU-12e",
}


def system_name(hdr: AtsHeader) -> str:
    """'ADU08e' -> 'ADU-08e'. Unknown names are kept (MTHotel writes 'unknown')."""
    raw = hdr.SystemType.strip()
    name = SYSTEM_NAMES.get(raw.lower().replace("-", ""))
    if name is None:
        log.warning("unknown SystemType %r: filter bits cannot be decoded", raw)
        return raw or "unknown"
    return name


def channel_type(hdr: AtsHeader) -> str:
    """'EX' -> 'Ex'; single letters (x, y, z, T) unchanged."""
    raw = hdr.channel_type.strip()
    return raw if len(raw) <= 1 else raw[0].upper() + raw[1:].lower()


def sample_dtype(ats_path: Path, hdr: AtsHeader) -> str:
    """'<i4' or '<i8', decided from the file size (header flags are unreliable in old files)."""
    data_bytes = ats_path.stat().st_size - ATS_HEADER_BYTES
    n = hdr.n_samples
    if n and data_bytes == n * 4:
        return "<i4"
    if n and data_bytes == n * 8:
        return "<i8"
    raise AtsFormatError(
        f"{ats_path.name}: {data_bytes} data bytes != samples ({n}) x 4 or x 8; "
        f"file may be sliced or truncated"
    )


def ats_files(path: Path) -> list[Path]:
    """The .ats file itself, or the .ats files directly inside a folder, sorted."""
    return [path] if path.is_file() else sorted(path.glob("*.ats"))


def write_atss_data(ats_path: Path, hdr: AtsHeader, lsb: float, atss_path: Path) -> int:
    """Scale the counts to float64 and stream them into ``atss_path``. Returns the sample count."""
    dtype = sample_dtype(ats_path, hdr)
    n = hdr.n_samples
    counts = np.memmap(ats_path, dtype=dtype, mode="r", offset=ATS_HEADER_BYTES, shape=(n,))
    tmp = atss_path.with_suffix(".atss.part")
    with open(tmp, "wb") as out:
        for i in range(0, n, CHUNK):
            (counts[i : i + CHUNK].astype("<f8") * lsb).tofile(out)
    tmp.replace(atss_path)  # only a complete file gets the final name
    return n


def write_atss_json(meta: AtssMeta, json_path: Path) -> None:
    json_path.write_text(json.dumps(meta.to_json(), indent=2, ensure_ascii=False), encoding="utf-8")
