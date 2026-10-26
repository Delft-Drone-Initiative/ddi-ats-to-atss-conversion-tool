# SPDX-FileCopyrightText: 2026 Stichting Delft Drones Initiative
#
# SPDX-License-Identifier: Apache-2.0
from importlib.metadata import version

from ._api import (
    convert_ats_file,
    convert_atss_to_frames,
    convert_dir_to_atss,
    convert_measurement_to_frames,
    convert_survey,
    convert_survey_to_frames,
    read_ats_header,
    read_atss,
    read_atss_info,
    read_calibration,
)

__version__ = version("ats2atss")


__all__ = [
    "convert_dir_to_atss",
    "convert_ats_file",
    "read_ats_header",
    "read_calibration",
    "convert_atss_to_frames",
    "convert_survey",
    "convert_measurement_to_frames",
    "convert_survey_to_frames",
    "read_atss",
    "read_atss_info",
]


def main() -> None:
    print("Hello from ats2atss!")


for _name in __all__:
    if not _name.startswith("__"):
        globals()[_name].__module__ = "ats2atss"

del _name
