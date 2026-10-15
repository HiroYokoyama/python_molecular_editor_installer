# Installer 3.1.3 bug audit

Scope: executable discovery, manual paths, shortcut/file-association setup, Linux MIME cleanup, TUI worker lifecycle, macOS launcher generation, packaging, and the release workflow. The main MoleditPy application repository is outside this audit.

## Findings fixed

| Finding | Result |
| --- | --- |
| Requested association setup returned false but installation still returned success | Windows/Linux/macOS component failures now return a failure status; a failed macOS configuration leaves the previous bundle intact |
| System-wide Linux desktop-entry creation failed silently at the top level | Stop before association setup and report failure |
| Keyboard bindings bypassed disabled TUI buttons | Serialize actions, block quitting during work, and keep failed operations retryable |
| Background discovery redirected stdout for every thread | Use quiet discovery without changing process-wide stdout |
| Linux uninstall removed other applications' MIME handlers and matching comments | Remove only the `MoleditPy.desktop` handler and preserve other values |
| Resolving a venv's Python symlink searched the base interpreter's folder first | Preserve the active interpreter's directory during executable discovery |
| macOS executable paths were inside shell double quotes | Use AppleScript's `quoted form of` for both interpreter and executable; escape AppleScript backslashes and quotes |
| Manual release checked an unprefixed tag | Check the exact `refs/tags/vVERSION` ref before modifying the package |
| Tag name and built package version could disagree | Verify package metadata against the requested release version before building |

## Local validation

- Windows / Python 3.13: 212 tests passed, 2 symlink tests skipped because the host cannot create symbolic links. Linux/macOS CI exercises those tests without that Windows privilege limitation.
- Ruff syntax/import/name checks passed with a Python 3.9 target; Python 3.9 remains supported.
- Release-workflow checks cover a new patch version, an existing v-prefixed tag, a non-main manual dispatch, multiline input rejection, tag-triggered version selection, and mismatched package metadata.
- Wheel and source distribution built for 3.1.3.
- Static subprocess warnings were reviewed: calls use argument lists rather than `shell=True`; system tools depend on the OS PATH. Generated macOS shell commands now quote both launch arguments.

Cross-platform CI and smoke checks are required before publishing. This audit is scoped verification, not a guarantee that every platform-specific failure is eliminated.
