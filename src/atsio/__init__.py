# SPDX-FileCopyrightText: 2026 Stichting Delft Drones Initiative
#
# SPDX-License-Identifier: Apache-2.0
from importlib.metadata import version

from ._api import (
    convert_ats_file,
    convert_atss_to_frames,
    convert_dir_to_atss,
    convert_measurement_to_frames,
    convert_survey_to_atss,
    convert_survey_to_frames,
    read_ats_header,
    read_calibration,
)
from ._errors import Ats2AtssError
from ._metadata import ConversionResult, DirResult, SurveyResult

__version__ = version("atsio")


__all__ = [
    "convert_dir_to_atss",
    "convert_ats_file",
    "read_ats_header",
    "read_calibration",
    "convert_atss_to_frames",
    "convert_survey_to_atss",
    "convert_measurement_to_frames",
    "convert_survey_to_frames",
    "ConversionResult",
    "SurveyResult",
    "DirResult",
    "Ats2AtssError"
]


def main() -> None:
    print("Hello from ats2atss!")


for _name in __all__:
    if not _name.startswith("__"):
        globals()[_name].__module__ = "ats2atss"

del _name
