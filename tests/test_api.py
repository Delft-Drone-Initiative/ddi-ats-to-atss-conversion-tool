# SPDX-FileCopyrightText: 2026 Stichting Delft Drones Initiative
#
# SPDX-License-Identifier: Apache-2.0
"""Public-API tests on a recording you point at:

    uv run pytest tests/test_api.py --data /path/to/recording -v

or set DATA_PATH in tests/conftest.py and run without --data (e.g. from PyCharm).

--data may be one .ats file, one recording folder, or a folder that contains
recordings (searched recursively). Every .ats file and every recording folder
becomes its own test. For a single file, the folder tests are skipped.
Without --data all tests are skipped.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

import atsio

JSON_KEYS = [
    "datetime",
    "latitude",
    "longitude",
    "elevation",
    "azimuth",
    "tilt",
    "resistance",
    "units",
    "id",
    "filter",
    "source",
    "sensor_calibration",
]
CHANNEL_TYPES = {"Ex", "Ey", "Ez", "Hx", "Hy", "Hz"}


# ============================================================================ discovery


def _data_path(config) -> Path | None:
    value = config.getoption("--data")
    if value is None:
        return None
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise pytest.UsageError(f"--data: {path} does not exist")
    return path


def _ats_files(path: Path) -> list[Path]:
    return [path] if path.is_file() else sorted(path.rglob("*.ats"))


def _label(p: Path, root: Path) -> str:
    return p.name if root.is_file() else str(p.relative_to(root)) or p.name


def pytest_generate_tests(metafunc):
    """One test per .ats file (ats) and per recording folder (recording)."""
    root = _data_path(metafunc.config)
    files = _ats_files(root) if root else []
    if root and not files:
        raise pytest.UsageError(f"--data: no .ats files in {root}")
    # a single file given: test that file only, not the rest of its folder
    folders = [] if root is None or root.is_file() else sorted({p.parent for p in files})
    for name, items in (("ats", files), ("recording", folders)):
        if name in metafunc.fixturenames:
            ids = [_label(p, root) for p in items] if items else ["no-data"]
            metafunc.parametrize(name, items or [None], ids=ids)


def _skip_reason(config) -> str:
    root = _data_path(config)
    return (
        "no recording given: set DATA_PATH in tests/conftest.py or pass --data"
        if root is None
        else "--data is a single file"
    )


@pytest.fixture(autouse=True)
def _skip_without_data(request):
    for name in ("ats", "recording"):
        if name in request.fixturenames and request.getfixturevalue(name) is None:
            pytest.skip(_skip_reason(request.config))


@pytest.fixture(scope="session")
def converted(request, tmp_path_factory) -> dict[Path, atsio.DirResult]:
    """Every recording converted once per session: {recording folder: DirResult}."""
    root = _data_path(request.config)
    if root is None:
        pytest.skip("no recording given: set DATA_PATH in tests/conftest.py or pass --data")
    out_root = tmp_path_factory.mktemp("atss")
    results = {}
    for d in sorted({p.parent for p in _ats_files(root)}):
        out = out_root / d.name
        files = [p for p in _ats_files(root) if p.parent == d]
        res, fail = [], {}
        for p in files:
            try:
                res.append(atsio.convert_ats_file(p, out, overwrite=True))
            except (atsio.Ats2AtssError, OSError) as e:
                fail[p] = e
        results[d] = atsio.DirResult(d, out, tuple(res), fail)
    return results


def result_for(converted, ats: Path) -> atsio.ConversionResult:
    d = converted[ats.parent]
    if ats in d.failures:
        pytest.fail(f"conversion failed: {d.failures[ats]}")
    return next(r for r in d.results if r.source == ats)


# ============================================================================ per file


def test_header_is_readable_and_consistent(ats):
    hdr = atsio.read_ats_header(ats)
    assert hdr.header_length == 1024, "sliced / CEA file"
    assert hdr.sample_rate > 0 and hdr.lsbval != 0
    data_bytes = ats.stat().st_size - 1024
    assert data_bytes in (hdr.n_samples * 4, hdr.n_samples * 8), "truncated or sliced"


def test_header_matches_filename(ats):
    """ADU names files ..._C02_..._THx_...: header and name should agree."""
    hdr = atsio.read_ats_header(ats)
    tags = ats.stem.split("_")
    assert f"T{hdr.channel_type}" in tags, f"header says {hdr.channel_type}, name is {ats.name}"
    assert f"C{hdr.channel_number:02d}" in tags


def test_converts_without_error(ats, converted):
    r = result_for(converted, ats)
    assert r.atss.is_file() and r.json.is_file()
    assert r.meta.channel_type in CHANNEL_TYPES


def test_atss_has_every_sample_scaled_by_lsb(ats, converted):
    r = result_for(converted, ats)
    hdr = atsio.read_ats_header(ats)
    n = hdr.n_samples
    assert r.atss.stat().st_size == n * 8
    dtype = "<i4" if ats.stat().st_size - 1024 == n * 4 else "<i8"
    counts = np.memmap(ats, dtype=dtype, mode="r", offset=1024, shape=(n,))
    atss = np.memmap(r.atss, dtype="<f8", mode="r", shape=(n,))
    if r.meta.units == "mV/km":
        lsb = hdr.lsbval * (1000.0 / hdr.dipole_length_from_positions)
    else:
        lsb = hdr.lsbval
    for part in (slice(0, 10_000), slice(max(0, n - 10_000), n)):  # start and end, not all GBs
        np.testing.assert_array_equal(atss[part], counts[part].astype("<f8") * lsb)


def test_json_header(ats, converted):
    r = result_for(converted, ats)
    meta = json.loads(r.json.read_text(encoding="utf-8"))
    hdr = atsio.read_ats_header(ats)
    assert list(meta) == JSON_KEYS
    assert meta["datetime"] == hdr.start_datetime.strftime("%Y-%m-%dT%H:%M:%S")
    electric = r.meta.channel_type.startswith("E") and hdr.dipole_length_from_positions > 0
    assert meta["units"] == ("mV/km" if electric else "mV")
    assert 0.0 <= meta["azimuth"] < 360.0


def test_calibration(ats, converted):
    """Coils with a measdoc get a usable table for the header's own sensor and chopper."""
    r = result_for(converted, ats)
    hdr = atsio.read_ats_header(ats)
    cal = r.meta.calibration
    assert cal.chopper == hdr.chopper
    if not r.meta.is_magnetic:
        return  # electrodes: name only, no table
    if not hdr.XmlHeader or not (ats.parent / hdr.XmlHeader).is_file():
        pytest.skip("no measdoc XML next to this file")
    assert cal.has_table, f"no calibration for {hdr.sensor_type} #{hdr.sensor_serial_number}"
    assert cal.serial == hdr.sensor_serial_number
    f, a = np.array(cal.f), np.array(cal.a)
    assert np.all(np.diff(f) > 0), "frequencies not strictly increasing"
    assert np.all(f > 0) and np.all(a > 0)


def test_rerun_skips_existing_output(ats, converted):
    r = result_for(converted, ats)
    assert atsio.convert_ats_file(ats, r.atss.parent).skipped


# ============================================================================ per recording


def test_measdoc_lists_every_ats_file(recording):
    """The XML's <ats_data_file> list and the files on disk agree."""
    xmls = sorted(recording.glob("*.xml"))
    if not xmls:
        pytest.skip("no measdoc XML in this folder")
    listed = {
        e.text.strip() for x in xmls for e in ET.parse(x).getroot().iter("ats_data_file") if e.text
    }
    on_disk = {p.name for p in recording.glob("*.ats")}
    assert on_disk <= listed, f"not in measdoc: {sorted(on_disk - listed)}"
    assert listed <= on_disk, f"listed but missing: {sorted(listed - on_disk)}"


def test_convert_dir(recording, tmp_path):
    results = atsio.convert_dir_to_atss(recording, tmp_path)
    assert len(results) == len(list(recording.glob("*.ats")))


def test_convert_survey(recording, converted, tmp_path):
    """convert_survey on a survey folder that contains only this recording (via a link,
    so neighbouring folders are never touched). Its output already exists, so nothing is rewritten."""
    d = converted[recording]
    (tmp_path / recording.name).symlink_to(recording, target_is_directory=True)
    result = atsio.convert_survey_to_atss(tmp_path, d.out_dir.parent)
    assert [x.source.name for x in result.dirs] == [recording.name]
    assert result.ok and result.dirs[0].skipped == len(d.results), result.summary()