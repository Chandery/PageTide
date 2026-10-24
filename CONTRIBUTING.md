# Contributing to PageTide

Thanks for your interest. Issues and pull requests are welcome. 欢迎提 Issue 和 PR。

## Run from source

Python 3.9+ and the standard library are enough for the backend and the tests.

```sh
python3 -m app.server        # web UI at http://127.0.0.1:8765
```

Set `PAGETIDE_DATA` to use a throwaway data directory.

## Test

```sh
python3 scripts/budget.py --check
python3 scripts/harness.py check
python3 -m unittest discover -s tests -v
```

## Build the desktop app (macOS)

```sh
.local/desktop-build-env/bin/python scripts/build_desktop.py
cargo tauri build --bundles app
# Output: src-tauri/target/release/bundle/macos/PageTide.app
```

The Windows installer is built by GitHub Actions. Release steps are in [docs/RELEASE.md](docs/RELEASE.md).

## Before you open a PR

Read [AGENTS.md](AGENTS.md) for the project rules (privacy boundaries, the single model gateway, no silent fallbacks) and browse the `docs/` folder (start with [docs/PRODUCT.md](docs/PRODUCT.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)) for the product and architecture notes.
