# Contributing to PageTide

Thank you for being here. **Contributions of every kind are welcome**: bug reports, feature ideas, documentation and translation fixes, and pull requests. 欢迎任何形式的贡献：报告 bug、提建议、改文档与翻译、提 PR。

You do not need to be an expert, and small fixes are as welcome as new features. For a bigger change, please open an [issue](https://github.com/Chandery/PageTide/issues) first so we can agree on the direction. Then use the steps below to run and test the app.

## Run from source

Python 3.9+ and the standard library are enough for the backend and the tests.

```sh
python3 -m app.server        # web UI at http://127.0.0.1:8765
```

Set `PAGETIDE_DATA` to use a throwaway data directory.

## Test

```sh
python3 -m unittest discover -s tests -v
node --test tests/*.cjs
```

## Build the desktop app (macOS)

```sh
.local/desktop-build-env/bin/python scripts/build_desktop.py
cargo tauri build --bundles app
# Output: src-tauri/target/release/bundle/macos/PageTide.app
```

The Windows installer is built by GitHub Actions. Release steps are in [docs/RELEASE.md](docs/RELEASE.md).

## Before you open a PR

Please keep these project rules in mind (they are what reviews look for):

- **Privacy first.** No hosted backend, telemetry upload or cloud sync. Papers, notes and the profile stay on the user's machine.
- **One model gateway.** Every AI call goes through `app/gateway.py`, which enforces the budgets in `app/budget.json`. Do not call a provider SDK from the UI or from feature code, and do not add silent model fallbacks or retry loops.
- **Zero-token core.** Search, ranking, archiving and the profile must keep working offline without any model call.
- **No dislike inferred from silence.** Never treat no activity or no selection as a negative signal.
- **Source text is untrusted data**, never an instruction for the app to follow.
- Add or update a test for behavior you change, and make sure the test commands above pass.

For the product and architecture background, start with [docs/PRODUCT.md](docs/PRODUCT.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
