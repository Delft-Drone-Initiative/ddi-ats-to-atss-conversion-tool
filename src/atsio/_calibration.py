# SPDX-License-Identifier: Apache-2.0
"""Sensor calibration from a Metronix measurement XML (measdoc).

Mirrors MTHotel's ``read_cal::read_std_xml`` + ``ats2atss::convert_header``:

* every ``calibration_sensors/channel`` yields one entry per chopper table
  ("on" / "off"); rows without a `chopper` attribute count as "off";
* tables are only accepted in the old mtx units  f [Hz], a [V/(nT*Hz)], p [deg]
  and converted to the JSON units  a [mV/nT] = c2 * f * 1000;
* the table for an .ats file is picked by sensor + serial + chopper taken from
  the **ATS header**, not by XML channel id;
* sensors without data (electrodes) still give an entry with empty f/a/p.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET  # expat >= 2.4.1 rejects entity-expansion attacks
from functools import lru_cache
from pathlib import Path

import numpy as np

from ._errors import AtsFormatError, CalibrationError
from ._headers import ATS_HEADER_BYTES, header_from_bytes
from ._metadata import AtsHeader, Calibration, MIN_CAL_SIZE

log = logging.getLogger(__name__)

OLD_UNITS = ("Hz", "V/(nT*Hz)", "deg")  # mtx_old: a normalised by f, in V
_PHASE_UNITS = ("deg", "degrees")
_AMP_FACTOR = {
    "V/(nT*Hz)": lambda f: f * 1000.0,  # -> mV/nT
    "mV/nT": lambda f: 1.0,
}  # already new format
UNKNOWN_DATETIME = "1970-01-01T00:00:00"
_DUP_TOLERANCE = 0.01  # MTHotel: duplicates within 1 % are dropped, otherwise an error


# ----------------------------------------------------------------------------- names

_SENSOR_RE = re.compile(r"^(MFS|FGS|SHFT|SHF|EFP)-?0*(\d+)([a-z]*)$", re.IGNORECASE)


# copied from MTHotel cpp/data/info.db, table sensor_aliases (lower-case key -> official name)
SENSOR_ALIASES = {
    "mfs05": "MFS-05",
    "mfs-05": "MFS-05",
    "mfs5": "MFS-05",
    "mfs06": "MFS-06",
    "mfs-06": "MFS-06",
    "mfs6": "MFS-06",
    "mfs06e": "MFS-06e",
    "mfs-06e": "MFS-06e",
    "mfs6e": "MFS-06e",
    "mfs07": "MFS-07",
    "mfs-07": "MFS-07",
    "mfs7": "MFS-07",
    "mfs07e": "MFS-07e",
    "mfs-07e": "MFS-07e",
    "mfs7e": "MFS-07e",
    "mfs09u": "MFS-09u",
    "mfs-09u": "MFS-09u",
    "mfs9u": "MFS-09u",
    "mfs10e": "MFS-10e",
    "mfs-10e": "MFS-10e",
    "mfs11e": "MFS-11e",
    "mfs-11e": "MFS-11e",
    "mfs12e": "MFS-12e",
    "mfs-12e": "MFS-12e",
    "mfs14e": "MFS-14e",
    "mfs-14e": "MFS-14e",
    "fgs02": "FGS-02",
    "fgs-02": "FGS-02",
    "fgs2": "FGS-02",
    "fgs03": "FGS-03",
    "fgs-03": "FGS-03",
    "fgs3": "FGS-03",
    "fgs03e": "FGS-03e",
    "fgs-03e": "FGS-03e",
    "fgs3e": "FGS-03e",
    "fgs04e": "FGS-04e",
    "fgs-04e": "FGS-04e",
    "fgs05e": "FGS-05e",
    "fgs-05e": "FGS-05e",
    "shft02": "SHFT-02",
    "shft-02": "SHFT-02",
    "shft2": "SHFT-02",
    "shft02e": "SHFT-02e",
    "shft-02e": "SHFT-02e",
    "shft2e": "SHFT-02e",
    "shf02e": "SHFT-02e",
    "shft03": "SHFT-03e",
    "shft03e": "SHFT-03e",
    "shft-03e": "SHFT-03e",
    "shf03e": "SHFT-03e",
    "efp06": "EFP-06",
    "efp-06": "EFP-06",
    "efp07": "EFP-07",
    "efp-07": "EFP-07",
    "efp07e": "EFP-07e",
    "efp-07e": "EFP-07e",  # MTHotel maps efp07e to "EFP07e" (typo)
    "mtc50h": "MTC-50H",
    "mtc-50h": "MTC-50H",
    "mtc80h": "MTC-80H",
    "mtc-80h": "MTC-80H",
    "amtc30": "AMTC-30",
    "amtc-30": "AMTC-30",
    "strod": "SteelRod",
    "buf_5": "BufferCable_5m",
    "buf_10": "BufferCable_10m",
    "buf_25": "BufferCable_25m",
    "unkn_h": "Unknown-H",
    "unkn_e": "Unknown-E",
}


def normalize_sensor_name(name: str) -> str:
    """Official Metronix name: MTHotel's alias table first, then a pattern for unlisted variants."""
    name = name.strip()
    if name.lower() in SENSOR_ALIASES:
        return SENSOR_ALIASES[name.lower()]
    m = _SENSOR_RE.match(name)
    if not m:
        return name
    prefix, number, suffix = m.groups()
    prefix = "SHFT" if prefix.upper() in ("SHF", "SHFT") else prefix.upper()
    return f"{prefix}-{int(number):02d}{suffix.lower()}"


# ----------------------------------------------------------------------------- parsing


def _float(node: ET.Element, tag: str) -> tuple[float | None, str]:
    el = node.find(tag)
    if el is None or el.text is None:
        return None, ""
    try:
        return float(el.text), (el.get("unit") or "").strip()
    except ValueError:
        return None, ""


def _int(text: str | None, default: int = 0) -> int:
    try:
        return int((text or "").strip())
    except ValueError:
        return default


def _clean_table(f, a, p, label: str) -> tuple[list[float], list[float], list[float]]:
    """Sort by frequency, drop near-identical duplicates, refuse conflicting ones."""
    f, a, p = (np.asarray(v, dtype=float) for v in (f, a, p))
    order = np.argsort(f, kind="stable")
    f, a, p = f[order], a[order], p[order]
    keep = np.ones(f.size, dtype=bool)
    for i in range(1, f.size):
        if f[i] != f[i - 1]:
            continue

        def dev(x, y):
            s = max(abs(x), abs(y))
            return 0.0 if s == 0 else abs(x - y) / s

        da, dp = dev(a[i], a[i - 1]), dev(p[i], p[i - 1])
        if da > _DUP_TOLERANCE or dp > _DUP_TOLERANCE:
            raise CalibrationError(
                f"{label}: duplicate {f[i]} Hz with conflicting values "
                f"(a {a[i - 1]:g}/{a[i]:g}, p {p[i - 1]:g}/{p[i]:g})"
            )
        log.warning("%s: dropping duplicate calibration row at %g Hz", label, f[i])
        keep[i] = False
    return f[keep].tolist(), a[keep].tolist(), p[keep].tolist()


def read_ats_header(path: str | Path) -> AtsHeader:
    """Read the header of an .ats file."""
    path = Path(path)
    with open(path, "rb") as fh:
        raw = fh.read(ATS_HEADER_BYTES)
    try:
        return header_from_bytes(raw)
    except AtsFormatError as e:
        raise AtsFormatError(f"{path}: {e}") from None


def read_xml_calibrations(xml_path: str | Path) -> list[Calibration]:
    """All calibration tables in a measdoc XML, one per (channel, chopper)."""
    xml_path = Path(xml_path)
    root = ET.parse(xml_path).getroot()
    sensors = root.find("calibration_sensors")
    if sensors is None:
        raise CalibrationError(f"{xml_path.name}: no <calibration_sensors> section")

    result: list[Calibration] = []
    for ch in sensors.findall("channel"):
        cid = _int(ch.get("id"), default=-1)
        try:
            result.extend(_read_channel(ch, cid, xml_path))
        except CalibrationError as e:  # MTHotel: log and continue with the next channel
            log.error("%s", e)
    return result


def _read_channel(ch: ET.Element, cid: int, xml_path: Path) -> list[Calibration]:
    result: list[Calibration] = []
    cal = ch.find("calibration")
    item = cal.find("calibrated_item") if cal is not None else None
    if item is None:
        return result
    sensor = normalize_sensor_name(item.findtext("ci") or "")
    serial = _int(item.findtext("ci_serial_number"))
    date = (item.findtext("ci_date") or "").strip()
    time = (item.findtext("ci_time") or "").strip() or "00:00:00"
    stamp = f"{date}T{time}" if date else UNKNOWN_DATETIME

    tables: dict[str, tuple[list, list, list]] = {}
    for row in cal.findall("caldata"):
        freq, fu = _float(row, "c1")
        amp, au = _float(row, "c2")
        pha, pu = _float(row, "c3")
        if freq is None or amp is None or pha is None:
            continue  # incomplete row: MTHotel skips it too
        if fu != "Hz" or au not in _AMP_FACTOR or pu not in _PHASE_UNITS:
            raise CalibrationError(
                f"{xml_path.name} channel {cid}: unexpected units {fu!r}, {au!r}, {pu!r}; "
                f"expected Hz, V/(nT*Hz) or mV/nT, deg"
            )
        chop = "on" if (row.get("chopper") or "").strip().lower() == "on" else "off"
        t = tables.setdefault(chop, ([], [], []))
        t[0].append(freq)
        t[1].append(amp * _AMP_FACTOR[au](freq))  # -> mV/nT
        t[2].append(pha)

    if not tables:  # electrode / sensor without data: keep name + serial
        result.append(Calibration(sensor, serial, 0, cid, stamp))
        return result
    for chop, (f, a, p) in tables.items():
        label = f"{xml_path.name} ch{cid} {sensor} #{serial} chopper {chop}"
        f, a, p = _clean_table(f, a, p, label)
        if len(f) < MIN_CAL_SIZE:
            log.warning(
                "%s: only %d points; MTHotel ignores tables shorter than %d",
                label,
                len(f),
                MIN_CAL_SIZE,
            )
        result.append(Calibration(sensor, serial, int(chop == "on"), cid, stamp, "", f, a, p))
    return result


def select_calibration(
    cals: list[Calibration], sensor: str, serial: int, chopper: int
) -> Calibration:
    """The table matching an ATS header (sensor_type, sensor_serial_number, chopper).
    Falls back to an empty calibration (sensor name + serial only), as MTHotel does.
    """
    sensor = normalize_sensor_name(sensor)
    for c in cals:
        if c.sensor == sensor and c.serial == serial and c.chopper == chopper and c.f:
            return c
    other = [c for c in cals if c.sensor == sensor and c.serial == serial and c.f]
    if other:
        log.warning(
            "%s #%d: XML has only chopper=%d data but the recording used chopper=%d; "
            "no calibration attached",
            sensor,
            serial,
            other[0].chopper,
            chopper,
        )
    return Calibration(sensor, serial, chopper)


# ----------------------------------------------------------------------------- automatic


@lru_cache(maxsize=64)
def _cached_xml(xml_path: Path) -> tuple[Calibration, ...]:
    return tuple(read_xml_calibrations(xml_path))


def xml_path_for(ats_path: str | Path, hdr: AtsHeader) -> Path | None:
    """The measdoc XML named in the header, if it exists next to the .ats file."""
    name = (hdr.XmlHeader or "").strip()
    if not name:
        return None
    path = Path(ats_path).parent / Path(name).name  # .name: no "../" escapes
    return path if path.is_file() else None


def calibration_for_header(
    cals: list[Calibration] | tuple[Calibration, ...], hdr: AtsHeader
) -> Calibration:
    """select_calibration with sensor, serial and chopper taken from the ATS header."""
    serial = hdr.sensor_serial_number
    if hdr.channel_type in ("Ex", "Ey") and serial == 0:  # MTHotel convention
        serial = 1 if hdr.channel_type == "Ex" else 2
    return select_calibration(list(cals), hdr.sensor_type, serial, hdr.chopper)


def calibration_for_ats(ats_path: str | Path, hdr: AtsHeader | None = None) -> Calibration:
    """Everything automatic: header -> XML -> matching table.

    Pass ``hdr`` if you already read the header, to avoid reading it twice.
    Returns an empty calibration (sensor + serial, no f/a/p) when there is no XML.
    """
    if hdr is None:
        hdr = read_ats_header(ats_path)
    xml = xml_path_for(ats_path, hdr)
    if xml is None:
        log.warning("%s: no measdoc XML found, no calibration attached", Path(ats_path).name)
        return Calibration(
            normalize_sensor_name(hdr.sensor_type), hdr.sensor_serial_number, hdr.chopper
        )
    try:
        cals = _cached_xml(xml.resolve())
    except (CalibrationError, ET.ParseError) as e:
        log.error(
            "%s: unusable XML %s (%s), no calibration attached", Path(ats_path).name, xml.name, e
        )
        return Calibration(
            normalize_sensor_name(hdr.sensor_type), hdr.sensor_serial_number, hdr.chopper
        )
    return calibration_for_header(cals, hdr)
