# SPDX-FileCopyrightText: 2026 Stichting Delft Drones Initiative
#
# SPDX-License-Identifier: Apache-2.0

"""
read_magnetic.py -- load only the MAGNETIC (H) channels from a converted atss survey.

An .atss channel is a raw float64 stream; its sibling .json holds the metadata; and
the channel TYPE lives in the filename tags (serial_system_Cxx_Txx_rate), e.g.
    084_ADU-08e_C02_THx_2Hz.atss   ->  channel_type "Hx"
"Magnetic" = Hx / Hy / Hz (the induction-coil field), as opposed to E (electric)
or J (currents). We filter on that type.

Only needs numpy + stdlib. Returns numpy float64 arrays ready for FFT scripts.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np
import pandas as pd
from _helper_utilities import *

from ._headers import ATS_HEADER_BYTES
from ._metadata import AtssMeta
from ._reader import *

log = logging.getLogger(__name__)


def parse_atss_name(base: Path) -> AtssMeta:
    """Pull the tags encoded in the filename: serial, system, channel_no, channel_type, sample_rate."""
    tags = base.name.split("_")
    info = AtssMeta(serial=int(tags[0]), system=tags[1])
    for tag in tags[2:]:
        if tag.startswith("C") and tag[1:].isdigit():
            info.channel_no = int(tag[1:])
        elif tag.startswith("T"):
            info.channel_type = tag[1:]  # "THx" -> "Hx"
        elif tag[0].isdigit() and tag.endswith("Hz"):
            info.sample_rate = float(tag[:-2])  # "2Hz" -> 2.0
        elif tag[0].isdigit() and tag.endswith("s"):
            info.sample_rate = 1.0 / float(tag[:-1])  # "4s" -> 0.25 Hz (period form)
    return info


# def read_magnetic(run_dir, mmap: bool = False) -> dict:
#     """
#     Load every MAGNETIC channel in a run directory.
#     Returns {channel_type: (data, meta)}, e.g. {"Hx": (arr, {...}), "Hy": (...), "Hz": (...)}.
#     Non-magnetic channels (E, J, ...) are skipped.
#     """
#     run_dir = Path(run_dir)
#     out = {}
#     for atss_path in sorted(run_dir.glob("*.atss")):
#         base = atss_path.with_suffix("")
#         ctype = _parse_atss_name(base).get("channel_type", "")
#         if is_magnetic(ctype):
#             out[ctype] = read_atss(atss_path, mmap=mmap)
#     return out


def time_index(meta: AtssMeta, n: int, index: str) -> pd.Index:
    fs = meta.sample_rate
    if index == "samples":
        return pd.RangeIndex(n, name="sample")
    if index == "seconds":
        return pd.Index(np.arange(n) / fs, name="seconds")
    if index == "datetime":
        start = pd.to_datetime(meta.datetime)
        # arange/fs in float64 seconds is accurate to ns over these lengths; safer than an
        # integer-ns freq (1/524288 s is not a whole number of nanoseconds).
        return pd.DatetimeIndex(start + pd.to_timedelta(np.arange(n) / fs, unit="s"), name="time")
    raise ValueError(f"index must be samples|seconds|datetime, got {index!r}")


def atss_to_frame(path, index: str = "datetime") -> pd.DataFrame:
    """One .atss channel -> a 1-column DataFrame (column named by channel type, e.g. 'Hx')."""
    data, meta = read_atss(path)
    df = pd.DataFrame(
        {meta.get("channel_type", "ch"): np.asarray(data)},
        index=time_index(meta, data.size, index),
    )
    df.attrs["meta"] = meta
    return df

#
# def convert_ats_file(ats_path: Path, run_dir: Path, cals: dict) -> Path:
#     h = read_ats_header(ats_path)
#     lsb, units = lsb_units(h)
#
#     # Decide sample width from arithmetic, not header flags (unreliable in old V01 files).
#     data_bytes = ats_path.stat().st_size - ATS_HEADER_BYTES
#     n = h["samples"]
#     if n and data_bytes == n * 4:
#         dtype = np.int32
#     elif n and data_bytes == n * 8:
#         dtype = np.int64
#     else:
#         raise ValueError(
#             f"{ats_path.name}: {data_bytes} data bytes != samples({n})*4 or *8; "
#             f"file may be sliced or truncated."
#         )
#     counts = np.fromfile(ats_path, dtype=dtype, offset=ATS_HEADER_BYTES)
#     data = counts.astype(np.float64) * lsb
#     run_dir.mkdir(parents=True, exist_ok=True)
#     field_channel_ntag = {0: "Ex", 1: "Ey", 2: "Hx", 3: "Hy", 4: "Hz"}
#     name = (
#         f"{h['serial_number']:03d}_{h['SystemType']}_C{h['channel_number']:02d}"
#         f"_T{field_channel_ntag[h['channel_number']]}_{sr_str(h['sample_rate'])}"
#     )
#     base = run_dir / name
#     data.tofile(str(base) + ".atss")
#
#     start_iso = np.datetime64(int(h["start"]), "s").astype("datetime64[ms]").astype(str) + "Z"
#     cal = (cals or {}).get(h["channel_number"])
#     sc = {
#         "sensor": h["sensor_type"],
#         "serial": h["sensor_serial_number"],
#         "chopper": h["chopper"],
#         "units_frequency": "Hz",
#         "units_amplitude": "mV/nT",
#         "units_phase": "degrees",
#         "f": [],
#         "a": [],
#         "p": [],
#     }
#     if cal:
#         sc.update(
#             sensor=cal["sensor"],
#             serial=cal["serial"],
#             chopper=cal["chopper"],
#             f=cal["f"],
#             a=cal["a"],
#             p=cal["p"],
#         )
#
#     meta = {
#         "datetime": start_iso,
#         "latitude": h["iLat_ms"] / 3.6e6,
#         "longitude": h["iLong_ms"] / 3.6e6,
#         "elevation": h["iElev_cm"] / 100.0,
#         "azimuth": 0.0,
#         "tilt": 0.0,
#         "resistance": h["rho_probe_ohm"],
#         "units": units,
#         "filter": h["ADB_board_type"],
#         "source": "",
#         "sensor_calibration": sc,
#     }
#     with open(str(base) + ".json", "w", encoding="utf-8") as f:
#         json.dump(meta, f, indent=2, ensure_ascii=False)
#     print(f"  {ats_path.name} -> {base.name}.atss ({data.size} samples, {units})")
#     return base


# def convert_all_ats_dir_to_atss(root_dir: Path, savedir: Path, experiment_table: dict):
#     measurement_folders = root_dir.glob("ADU_*")
#     savedir.mkdir(parents=True, exist_ok=True)
#     calc_dict = {}
#     for d in measurement_folders:
#         if not d.is_dir():
#             continue
#         tags = d.name.split("_")
#         matched = [t for t in tags if t in experiment_table]
#         if not matched:
#             continue
#         out = savedir / f"ADU-{experiment_table[matched[0]]}"
#         out.mkdir(parents=True, exist_ok=True)
#         calc = read_one_ats_dir_to_atss(d, out)
#         calc_dict[f"ADU-{experiment_table[matched[0]]}"] = calc
#     return calc_dict


# ---------------------------------------------------------------- the converter
# def convert_ats_file(ats_path: Path, run_dir: Path, *, overwrite: bool = False) -> Path:
#     h = read_ats_header(ats_path)
#     system = system_name(h["SystemType"])
#     ct = channel_type(h["channel_type"])  # from the header, never from the channel number
#     lsb, units = _lsb_units(h, ct)
#
#     data_bytes = ats_path.stat().st_size - ATS_HEADER_BYTES
#     n = h["samples_64bit"] if h["samples"] == 0xFFFFFFFF else h["samples"]
#     if n and data_bytes == n * 4:
#         dtype = "<i4"
#     elif n and data_bytes == n * 8:
#         dtype = "<i8"
#     else:
#         raise ValueError(
#             f"{ats_path.name}: {data_bytes} data bytes != samples({n})*4 or *8; "
#             f"file may be sliced or truncated."
#         )
#
#     name = f"{h['serial_number']:03d}_{system}_C{h['channel_number']:03d}_T{ct}_{_sr_str(h['sample_rate'])}"
#     base = run_dir / name
#     atss, jsn = base.with_suffix(".atss"), base.with_suffix(".json")
#     if not overwrite and (atss.exists() or jsn.exists()):
#         raise FileExistsError(f"{atss} exists; use overwrite=True")
#     run_dir.mkdir(parents=True, exist_ok=True)
#
#     counts = np.memmap(ats_path, dtype=dtype, mode="r", offset=ATS_HEADER_BYTES, shape=(n,))
#     with open(atss, "wb") as out:  # stream in chunks: no full copy in RAM
#         for i in range(0, n, 1 << 20):
#             (counts[i : i + (1 << 20)].astype("<f8") * lsb).tofile(out)
#
#     hdr = SimpleNamespace(
#         channel_type=ct,
#         sensor_type=h["sensor_type"],
#         sensor_serial_number=h["sensor_serial_number"],
#         chopper=h["chopper"],
#         XmlHeader=h["XmlHeader"],
#     )
#     cal = calibration_for_ats(ats_path, hdr)  # matched on header sensor + serial + chopper
#
#     meta = {
#         "datetime": np.datetime64(int(h["start"]), "s").astype(str),
#         "latitude": h["iLat_ms"] / 3.6e6,
#         "longitude": h["iLong_ms"] / 3.6e6,
#         "elevation": h["iElev_cm"] / 100.0,
#         "azimuth": 0.0,
#         "tilt": 0.0,  # TODO: from x1..z2
#         "resistance": h["rho_probe_ohm"],
#         "units": units,
#         "id": "",
#         "filter": filter_string(h, system),
#         "source": "",
#         "sensor_calibration": cal.to_json(),
#     }
#     jsn.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
#     log.info(
#         "%s -> %s (%d samples, %s, cal %d points)", ats_path.name, atss.name, n, units, len(cal.f)
#     )
#     return base
#



# ------------------------------------------------------------- 1. find (library)
def find_measurement_dirs(root_dir: Path, pattern: str = "meas_*") -> list[Path]:
    """Measurement folders under root_dir that contain at least one .ats file, sorted."""
    dirs = sorted(d for d in Path(root_dir).glob(pattern) if d.is_dir())
    empty = [d for d in dirs if not any(d.glob("*.ats"))]
    for d in empty:
        log.warning("%s: no .ats files, skipped", d.name)
    return [d for d in dirs if d not in empty]


# ------------------------------------------------------------- 3. convert one (library)
def read_one_ats_dir_to_atss(ats_dir: Path, out_dir: Path):
    """ """
    out_dir.mkdir(parents=True, exist_ok=True)
    return f"converted {ats_dir.name}"  # stand-in for the test


# ------------------------------------------------------------- 4. glue (library, naming injected)
def convert_dirs(
    dirs: Iterable[Path], savedir: Path, name_for: Callable[[Path], str | None] = lambda d: d.name
) -> dict[str, object]:
    """Convert each folder into savedir/<name_for(folder)>; folders named None are skipped."""
    results: dict[str, object] = {}
    sources: dict[str, Path] = {}
    for d in dirs:
        name = name_for(d)
        if name is None:
            log.info("%s: no matching experiment, skipped", d.name)
            continue
        if name in sources:
            raise ValueError(f"{d.name} and {sources[name].name} both map to {name!r}")
        sources[name] = d
        results[name] = read_one_ats_dir_to_atss(d, Path(savedir) / name)
    return results


# ------------------------------------------------------------- your old function, now 3 lines
def convert_all_ats_dir_to_atss(root_dir: Path, savedir: Path) -> dict:
    dirs = find_measurement_dirs(root_dir)
    return convert_dirs(dirs, savedir)

class ConversionError(RuntimeError):
    """One or more .ats files in a folder could not be converted."""


def convert_measurement_dir(measurement_dir: Path, out_dir: Path, *,
                            overwrite: bool = False) -> list[Path]:
    """Convert every .ats file in one measurement folder (or one .ats file) into out_dir.

    Returns the output base paths of the files written. Files whose .atss + .json
    already exist are skipped unless overwrite=True.
    """
    measurement_dir, out_dir = Path(measurement_dir), Path(out_dir)
    files = [measurement_dir] if measurement_dir.is_file() else sorted(measurement_dir.glob("*.ats"))
    if not files:
        raise FileNotFoundError(f"no .ats files in {measurement_dir}")

    log.info("converting %d file(s) from %s -> %s", len(files), measurement_dir, out_dir)
    written, failed = [], []
    for p in files:
        try:
            written.append(convert_ats_file(p, out_dir, overwrite=overwrite))
        except FileExistsError:
            log.info("%s: output exists, skipped", p.name)
        except (ValueError, OSError) as e:          # bad or truncated file: report, continue
            log.error("%s: %s", p.name, e)
            failed.append(p.name)
    if failed:
        raise ConversionError(
            f"{len(failed)} of {len(files)} file(s) failed in {measurement_dir}: {failed}")
    return written