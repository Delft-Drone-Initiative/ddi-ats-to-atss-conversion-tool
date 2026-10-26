import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from ._calibration import (
    _cached_xml,
    calibration_for_header,
    normalize_sensor_name,
    xml_path_for,
)
from ._errors import AtsFormatError, CalibrationError
from ._headers import ATS_HEADER_BYTES, header_from_bytes
from ._metadata import AtsHeader, Calibration

log = logging.getLogger(__name__)


# function for converting one folder of ats files to atss files
def convert_dir_to_atss(meas_dir: Path, savedir: Path, *, experiment_table: dict): ...


# converting one whole survey


def convert_survey(survey_dir: Path, savedir: Path): ...


def convert_ats_file(ats_path: Path, save_dir: Path, *, overwrite: bool = False): ...


""" Convert one .ats file ->  .atss + JSON file
    args;
    ats_path => path to .ats file
    save_dir => path to save location

"""


def read_ats_header(path: str | Path) -> AtsHeader:
    """Read the header of an .ats file."""
    path = Path(path)
    with open(path, "rb") as fh:
        raw = fh.read(ATS_HEADER_BYTES)
    try:
        return header_from_bytes(raw)
    except AtsFormatError as e:
        raise AtsFormatError(f"{path}: {e}") from None


# gives the metadata for one atss file
def read_atss_info(path: Path): ...


# gives one atss file ( one channel) as pandas frame with/without metadata
def read_atss(atss_path: Path, metadata: bool = False): ...


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


def convert_atss_to_frames(ats_file: Path, savedir: Path, mmap: bool = True):
    """
    Read ONE .atss channel. `path` may point at the .atss, the .json, or the base name.
    Returns pandas dataFrame(data, meta): data is a float64 numpy array, meta merges the filename tags
    with the json header. Set mmap=True to avoid loading huge files fully into RAM.
    """
    ...


def convert_measurement_to_frames(folder_path: Path, savedir: Path, mmap: bool = True):
    """
    Convert one measurement folder to dataFrames. `path` may point at the .atss, the .json, or the base name.
    Returns (data, meta): data is a float64 numpy array, meta merges the filename tags
    with the json header. Set mmap=True to avoid loading huge files fully into RAM.
    """
    ...


def convert_survey_to_frames(folder_path: Path, savedir: Path, mmap: bool = True):
    """
    Convert one entire survey to dataFrames. `path` may point at the .atss, the .json, or the base name.
    Returns (data, meta): data is a float64 numpy array, meta merges the filename tags
    with the json header. Set mmap=True to avoid loading huge files fully into RAM.
    """
    ...


__all__ = [
    "convert_dir_to_atss",
    "convert_ats_file",
    "read_ats_header",
    "read_atss_info",
    "read_calibration",
    "convert_atss_to_frames",
    "convert_ats_file",
    "convert_measurement_to_frames",
    "convert_survey",
    "convert_survey_to_frames",
    "read_atss",
]
