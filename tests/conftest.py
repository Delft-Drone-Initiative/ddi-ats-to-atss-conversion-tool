# SPDX-FileCopyrightText: 2026 Stichting Delft Drones Initiative
#
# SPDX-License-Identifier: Apache-2.0
"""Test settings. pytest only reads command-line options from conftest.py."""

from pathlib import Path

# Recording(s) the tests use when you run pytest without --data, e.g. from PyCharm.
# An .ats file, a recording folder, or a folder of recordings. Keep None in commits.

DATA_PATH = "path/to/test/data"


def pytest_addoption(parser):
    parser.addoption(
        "--data",
        action="store",
        default=DATA_PATH,
        help="an .ats file, a recording folder, or a folder of recordings "
        f"(default: DATA_PATH in tests/conftest.py, now {DATA_PATH!r})",
    )
