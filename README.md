<!--
SPDX-FileCopyrightText: 2026 Stichting Delft Drones Initiative

SPDX-License-Identifier: Apache-2.0
-->

# DDI ats2atss converter

Turn Metronix `.ats` recordings into `.atss` files, using nothing but Python.

[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Metronix data loggers, such as the ADU-08e, save their measurements as `.ats` files.
That's a binary format most tools can't read directly. `ats2atss` converts each recording
into the open `.atss` format: one data file per channel, with a readable JSON header.

The output is based on the structure used by [MTHotel](https://github.com/bfrmtx/MTHotel):
the files follow the same layout and header structure, so they work with MTHotel and other
tools that read `.atss`.

> **Status:** early development. Commands and the Python API may still change.
### Why use it?

- **Easy to install.** It's pure Python with only NumPy as a dependency, so there's nothing to compile.
- **Fast.** It converts a whole file in one go, even long high-frequency recordings.
- **Safe.** It warns you about truncated or unusual files instead of writing bad data.
- **Flexible.** Run it from the command line, or import it in your own Python scripts.

## Installation
    uv tool install ats2atss
Requirements: Python => 3.11

## How to use it (CLI)
Command: 

    ats2atss path/to/ats_files path/to/output


## Contributing
Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and
our [Code of Conduct](CODE_OF_CONDUCT.md).

## Security
Please report vulnerabilities privately, see [SECURITY.md](SECURITY.md).

## License
Licensed under the Apache License, version 2.0. See [LICENSE](LICENSE).