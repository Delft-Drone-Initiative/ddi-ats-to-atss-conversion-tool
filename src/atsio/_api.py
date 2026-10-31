import logging
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from ._calibration import (
    _cached_xml,
    calibration_for_header,
    normalize_sensor_name,
    read_ats_header,
    xml_path_for,
)
from ._errors import Ats2AtssError, CalibrationError, ConversionError
from ._helper_utilities import (
    ats_files,
    atss_basename,
    azimuth,
    channel_type,
    filter_string,
    lsb_and_units,
    sample_dtype,
    system_name,
    tilt,
    write_atss_data,
    write_atss_json,
)
from ._metadata import AtsHeader, AtssMeta, Calibration, ConversionResult, DirResult, SurveyResult

log = logging.getLogger(__name__)


def convert_ats_file(
    ats_path: str | Path,
    save_dir: str | Path,
    *,
    calibration: bool = True,
    overwrite: bool = False,
) -> ConversionResult:
    """Convert one .ats file into ``save_dir/<serial>_<system>_C<nnn>_T<type>_<rate>.atss + .json``.

    Args:
        ats_path: the .ats file.
        save_dir: output folder, created if needed.
        calibration: embed the sensor calibration from the measdoc XML.
        overwrite: replace existing output; otherwise existing output is skipped.

    Raises:
        AtsFormatError: unreadable, truncated or sliced file.
    """
    ats_path, save_dir = Path(ats_path), Path(save_dir)

    # 1. read and interpret the header
    hdr = read_ats_header(ats_path)
    system = system_name(hdr)
    ct = channel_type(hdr)  # from the header, never from the channel number
    lsb, units = lsb_and_units(hdr, ct)
    sample_dtype(ats_path, hdr)  # fail early on truncated / sliced files

    # 2. output paths; skip existing output
    base = save_dir / atss_basename(hdr, system, ct)
    atss, jsn = base.with_suffix(".atss"), base.with_suffix(".json")

    # 3. calibration: matched on the header's sensor + serial + chopper
    if calibration:
        cal = read_calibration(ats_path, replace(hdr, channel_type=ct))
    else:
        cal = Calibration(
            normalize_sensor_name(hdr.sensor_type), hdr.sensor_serial_number, hdr.chopper
        )

    meta = AtssMeta(
        serial=hdr.serial_number,
        system=system,
        channel_number=hdr.channel_number,
        channel_type=ct,
        sample_rate=hdr.sample_rate,
        datetime=hdr.start_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
        latitude=hdr.latitude,
        longitude=hdr.longitude,
        elevation=hdr.elevation,
        azimuth=azimuth(hdr, ct),
        tilt=tilt(hdr, ct),
        resistance=hdr.rho_probe_ohm,
        units=units,
        filter=filter_string(hdr, system),
        calibration=cal,
        samples=hdr.n_samples,
    )

    if not overwrite and (atss.exists() or jsn.exists()):
        log.info("%s: output exists, skipped", ats_path.name)
        return ConversionResult(ats_path, atss, jsn, meta, skipped=True)

    # 4. write data, then the header (a .json only appears next to a complete .atss)
    save_dir.mkdir(parents=True, exist_ok=True)
    write_atss_data(ats_path, hdr, lsb, atss)
    write_atss_json(meta, jsn)

    log.info(
        "%s -> %s (%d samples, %s, calibration %d points)",
        ats_path.name,
        atss.name,
        meta.samples,
        units,
        len(cal.f),
    )
    return ConversionResult(ats_path, atss, jsn, meta)


def _convert_dir(
    measurement_dir: Path, out_dir: Path, *, calibration: bool, overwrite: bool
) -> DirResult:
    """Convert one folder without raising: every outcome ends up in the DirResult."""
    files = ats_files(measurement_dir)
    if not files:
        return DirResult(
            measurement_dir,
            out_dir,
            error=FileNotFoundError(f"no .ats files in {measurement_dir}"),
        )
    log.info("converting %d file(s) from %s -> %s", len(files), measurement_dir, out_dir)
    results: list[ConversionResult] = []
    failures: dict[Path, Exception] = {}
    for p in files:
        try:
            results.append(
                convert_ats_file(p, out_dir, calibration=calibration, overwrite=overwrite)
            )
        except (
            Ats2AtssError,
            OSError,
        ) as e:  # bad, truncated or unreadable file: record, continue
            log.error("%s", e)
            failures[p] = e
    return DirResult(measurement_dir, out_dir, tuple(results), failures)


def convert_dir_to_atss(
    measurement_dir: str | Path,
    out_dir: str | Path,
    *,
    calibration: bool = True,
    overwrite: bool = False,
) -> list[ConversionResult]:
    """Convert every .ats file in one measurement folder (or one .ats file) into out_dir.

    Converts every file it can; existing output is skipped (``result.skipped``)
    unless overwrite=True.

    Raises:
        FileNotFoundError: no .ats files found.
        ConversionError: some files failed; ``.results`` holds the files that did convert,
            ``.failures`` maps each failed file to its error.
    """

    d = _convert_dir(
        Path(measurement_dir), Path(out_dir), calibration=calibration, overwrite=overwrite
    )
    if d.error is not None:
        raise d.error
    if d.failures:
        names = [p.name for p in d.failures]
        raise ConversionError(
            f"{d.failed} of {d.failed + len(d.results)} file(s) failed in {d.source}: {names}",
            list(d.results),
            dict(d.failures),
        )
    return list(d.results)


# converting one whole survey


def convert_survey_to_atss(
    survey_dir: str | Path,
    savedir: str | Path,
    *,
    calibration: bool = True,
    overwrite: bool = False,
) -> SurveyResult:
    """Convert every measurement folder in survey_dir into savedir/<folder name>.

    Never stops at a bad file or folder: every outcome is in the returned
    SurveyResult. Check ``result.ok``, print ``result.summary()``, or inspect
    ``result.failures``.

    Raises:
        FileNotFoundError: survey_dir does not exist or contains no folder with .ats files.
    """
    survey_dir, savedir = Path(survey_dir), Path(savedir)
    if not survey_dir.is_dir():
        raise FileNotFoundError(f"survey folder does not exist: {survey_dir}")

    folders = sorted(d for d in survey_dir.iterdir() if d.is_dir())
    with_ats = [d for d in folders if any(d.glob("*.ats"))]
    for d in folders:
        if d not in with_ats:
            log.info("%s: no .ats files, skipped", d.name)
    if not with_ats:
        raise FileNotFoundError(f"no folder with .ats files in {survey_dir}")

    dirs = tuple(
        _convert_dir(d, savedir / d.name, calibration=calibration, overwrite=overwrite)
        for d in with_ats
    )
    result = SurveyResult(survey_dir, savedir, dirs)
    (log.info if result.ok else log.warning)(
        "survey %s done:\n%s", survey_dir.name, result.summary()
    )
    return result


# read calibration of a single measurement
def read_calibration(ats_path: str | Path, hdr: AtsHeader | None = None) -> Calibration:
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


def _convert_atss_to_frames(ats_file: Path, savedir: Path, mmap: bool = True):
    """
    Read ONE .atss channel. `path` may point at the .atss, the .json, or the base name.
    Returns pandas dataFrame(data, meta): data is a float64 numpy array, meta merges the filename tags
    with the json header. Set mmap=True to avoid loading huge files fully into RAM.
    """
    ...


def _convert_measurement_to_frames(folder_path: Path, savedir: Path, mmap: bool = True):
    """
    Convert one measurement folder to dataFrames. `path` may point at the .atss, the .json, or the base name.
    Returns (data, meta): data is a float64 numpy array, meta merges the filename tags
    with the json header. Set mmap=True to avoid loading huge files fully into RAM.
    """
    ...


def _convert_survey_to_frames(folder_path: Path, savedir: Path, mmap: bool = True):
    """
    Convert one entire survey to dataFrames. `path` may point at the .atss, the .json, or the base name.
    Returns (data, meta): data is a float64 numpy array, meta merges the filename tags
    with the JSON header. Set mmap=True to avoid loading huge files fully into RAM.
    """
    ...


__all__ = [
    "convert_dir_to_atss",
    "convert_ats_file",
    "read_ats_header",
    "read_calibration",
    "convert_ats_file",
    "convert_survey_to_atss",
]
