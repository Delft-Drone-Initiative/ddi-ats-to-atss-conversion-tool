import math
from pathlib import Path

import numpy as np
import pandas as pd



def sr_str(sr: float) -> str:
    return f"{round(sr):g}Hz" if sr >= 0.99 else f"{round(1.0 / sr):g}s"


def lsb_units(h: dict):
    length = math.sqrt(
        (h["x2"] - h["x1"]) ** 2 + (h["y2"] - h["y1"]) ** 2 + (h["z2"] - h["z1"]) ** 2
    )
    if h["channel_type"] in ("Ex", "Ey", "Ez") and length > 0:
        return h["lsbval"] * 1000.0 / length, "mV/km"  # E -> normalise by dipole length
    return h["lsbval"], "mV"  # H stays mV


def rename_adu(root_dir: Path, rename: dict, sep="_", dry_run=True):
    measurement_folders = root_dir.glob("meas_*")
    for d in measurement_folders:
        if not d.is_dir():
            continue
        tags = d.name.split(sep)
        new_name = "_".join(rename.get(t, t) for t in tags)
        # print(new_name)
        if new_name == d.name:
            continue
        target = d.with_name(new_name)
        if not dry_run:
            d.rename(target)


def is_magnetic(channel_type: str) -> bool:
    """True for Hx/Hy/Hz. Adjust here if your systems label magnetic channels differently."""
    return channel_type.startswith("H")


def add_absolute_field(df: pd.DataFrame) -> pd.DataFrame:
    name = "|B|"
    df[name] = np.sqrt((df**2).sum(axis=1))
    return df
