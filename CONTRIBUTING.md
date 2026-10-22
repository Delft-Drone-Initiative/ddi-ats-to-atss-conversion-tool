<!--
SPDX-FileCopyrightText: 2026 Stichting Delft Drones Initiative

SPDX-License-Identifier: Apache-2.0
-->

# Contributing

Thanks for your interest in this project! Bug reports, documentation fixes
and code are all welcome. By participating, you agree to follow our
[Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting bugs and ideas

Open an issue. For bugs, include the version, your OS and the steps to
reproduce the problem. For larger changes, please open an issue to discuss
the idea before writing code.

Security problems should not be reported in public issues; see
[SECURITY.md](SECURITY.md).

## Development setup

```bash
git clone https://github.com/<owner>/ddi-ats-to-atss-conversion-tool.git
cd ddi-ats-to-atss-conversion-tool
uv sync
```

## Before opening a pull request

Run these checks; all of them should pass:

```bash
uv run ruff check --fix .
uv run ruff format .
uv run reuse lint
uv run pytest
```

New files need a license header. You can add one with:

```bash
uv run reuse annotate --license Apache-2.0 \
    --copyright "Stichting Delft Drones Initiative" --year 2026 <file>
```

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Keep each pull request focused on one change.
3. Write clear commit messages: a short summary line in the imperative
   ("Fix crash on empty header"), then a blank line and an explanation
   if needed.
4. Open the pull request and link the related issue (`Fixes #123`).

## License

By contributing, you agree that your contributions are licensed under the
Apache License 2.0, the same license as the project.