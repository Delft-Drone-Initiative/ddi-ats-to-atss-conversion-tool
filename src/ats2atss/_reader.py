import json
import struct
from pathlib import Path

import numpy as np
import pandas as pd

from ._headers import _FMT, ATS_HEADER_BYTES, ATS_HEADER_FIELDS
from ._converter import  convert_ats_file

#
# def read_ats_header(path: Path) -> dict:
#     with open(path, "rb") as f:
#         raw = f.read(ATS_HEADER_BYTES)
#     if len(raw) < ATS_HEADER_BYTES:
#         raise ValueError(f"{path}: shorter than the 1024-byte header")
#     values = struct.unpack(_FMT, raw)
#     h = {}
#     for (name, code), val in zip(ATS_HEADER_FIELDS, values, strict=False):
#         if code.endswith("s"):  # bytes -> str, cut at first NUL, trim
#             val = val.split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
#         h[name] = val
#     return h
#
#
# def read_atss(path, mmap: bool = True):
#     """
#     Read ONE .atss channel. `path` may point at the .atss, the .json, or the base name.
#     Returns (data, meta): data is a float64 numpy array, meta merges the filename tags
#     with the json header. Set mmap=True to avoid loading huge files fully into RAM.
#     """
#     base = Path(str(path))
#     for ext in (".atss", ".json"):
#         if base.name.endswith(ext):
#             base = base.with_name(base.name[: -len(ext)])
#     atss_path, json_path = Path(f"{base}.atss"), Path(f"{base}.json")
#     if not atss_path.exists():
#         raise FileNotFoundError(atss_path)
#     if not json_path.exists():
#         raise FileNotFoundError(json_path)
#
#     if mmap:
#         data = np.memmap(atss_path, dtype=np.float64, mode="r")
#     else:
#         data = np.fromfile(atss_path, dtype=np.float64)
#
#     m = _parse_atss_name(base)  # tags from the filename
#     h = json.load(open(json_path, encoding="utf-8"))
#     m.datetime = h.get("datetime")
#     m.latitude = h.get("latitude", 0.0)
#     m.longitude = h.get("longitude", 0.0)
#     m.elevation = h.get("elevation", 0.0)
#     m.units = h.get("units", "")
#     sc = h.get("sensor_calibration", {})
#     m.sensor = sc.get("sensor", "")
#     m.sensor_serial = sc.get("serial", 0)
#     m.chopper = sc.get("chopper", 0)
#     m.cal_f, m.cal_a, m.cal_p = sc.get("f", []), sc.get("a", []), sc.get("p", [])
#     m.samples = data.size  # = filesize / 8
#     return data, m


def read_one_ats_dir_to_atss(measurement_dir: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    files = (
        [measurement_dir] if measurement_dir.is_file() else sorted(measurement_dir.glob("*.ats"))
    )
    if not files:
        raise SystemExit(f"no .ats files in {measurement_dir}")
    # run_dir = savedir / f"run_{experiment_code}"
    print(f"Reading calibration file in {measurement_dir}")
    xml_pathj = find_calibration_xml(measurement_dir)
    calc = load_calibrations(xml_pathj)
    # print(calc)
    if any(out_dir.glob("*.atss")):
        return calc

    print(f"Converting {len(files)} file(s) -> {out_dir}")
    for p in files:
        convert_ats_file(p, out_dir, calc)
    print("done.")
    return calc


# only uses magnetic field data
def read_all_channels(atss_dir: Path) -> pd.DataFrame:
    df = run_to_frame(atss_dir)
    # print(df)
    return df


def read_all_data(data_dir: Path) -> list:
    frames = []
    for dir_item in data_dir.iterdir():
        if dir_item.is_dir():
            frame = read_all_channels(dir_item)
            frames.append(frame)

    return frames


