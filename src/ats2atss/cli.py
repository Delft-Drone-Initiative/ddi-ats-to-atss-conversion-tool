from pathlib import Path
import pandas as pd

from _converter import *
from _reader import *
from _helper_utilities import *


def run_to_frame(
    run_dir: Path, index: str = "datetime", channels=None, magnetic_only: bool = False
) -> pd.DataFrame:
    """
    All channels in a run directory -> one DataFrame, columns = channel types, aligned on time.
    channels: optional list to keep, e.g. ["Hx","Hy","Hz"].  magnetic_only: keep only H*.
    Channels must share length + sample rate to align (they do within a normal run).
    """
    if channels is None:
        channels = ["Hx", "Hy", "Hz"]
    cols = {}
    ref_meta, ref_len = None, None
    for p in sorted(run_dir.glob("*.atss")):
        data, meta = read_atss(p)
        ct = meta.channel_type
        if magnetic_only and not is_magnetic(ct):
            continue
        if channels and ct not in channels:
            continue
        if ref_meta is None:  # first kept channel sets the axis
            ref_meta, ref_len = meta, data.size
        elif data.size != ref_len or meta.sample_rate != ref_meta.sample_rate:
            raise ValueError(
                f"{ct}: length/rate differs from the others; can't share one frame"
            )
        cols[ct] = np.asarray(data)
    if ref_meta is None or ref_len is None:
        raise ValueError("no matching channels found")
    df = pd.DataFrame(cols, index=_time_index(ref_meta, ref_len, index))
    df.attrs["atss-meta"] = ref_meta
    df.attrs["meta"] = parse_source(run_dir.name)
    return df
