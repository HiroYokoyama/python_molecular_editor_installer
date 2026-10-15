# Changelog

## [3.1.3] - 2026-10-15

### Fixed

- Report installation failure when a requested Windows, macOS, or Linux file association cannot be configured, or when a system-wide Linux desktop entry cannot be written. The macOS failure path leaves an existing app bundle intact.
- Prevent keyboard shortcuts from starting overlapping TUI install/uninstall operations or quitting while an operation is running. Failed operations remain retryable.
- Keep background executable discovery from redirecting process-wide stdout and interfering with installation logs from another thread.
- Preserve other applications' handlers and comments when removing MoleditPy from Linux `mimeapps.list` files.
- Search the active virtual environment before the base installation when its Python interpreter is a symbolic link.
- Detect existing `v`-prefixed release tags correctly and verify that the release version matches package metadata before building. Pass manual version inputs through environment variables instead of shell-source interpolation.

### Tests

- Add regressions for component failure reporting, macOS bundle preservation, TUI action serialization, MIME-handler preservation, and virtual-environment discovery.

### Security

- Shell-quote the macOS launcher executable as well as its Python interpreter, and escape backslashes in AppleScript literals. Paths containing shell expansions, quotes, or backslashes are kept literal when passed to Terminal.
