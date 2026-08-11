# Testing Guide — moleditpy-installer

## Running the tests

```bash
# From the root directory of the repository:
python -m pytest tests/ -v

# With coverage:
python -m pytest tests/ -v --cov=moleditpy_installer --cov-report=term-missing
```

## Test structure

An orientation map, not an inventory — `tests/test_main.py` is the authoritative
list. Anything testable is expected to be tested, so assume a feature has
coverage and go look for it rather than inferring from this table.

| Test class / function | What it covers |
|---|---|
| `TestFindExecutable` | Path detection logic in `find_executable()` |
| `TestGetIconPath` | Icon file resolution per OS |
| `TestGetFileIconPath` | File association icon resolution (Windows only) |
| `TestRegisterFileAssociationsWindows` | File extension registration logic (Windows only) |
| `TestDeleteRegistryTree` / `TestUnregisterFileAssociationsWindows` | File extension unregistration logic (Windows only) |
| `TestRemoveShortcut` | Shortcut removal logic for Windows, Linux, and macOS |
| `TestInstall` | High-level `install()` routine and macOS bundle movement |
| `TestMainCLI` | CLI argument parsing (`--remove`, `--check`, `--version`, `--help`) |
| `test_package_runnable_as_module` | `python -m moleditpy_installer` works |
| `TestTui` / `TestTuiActions` | The Textual TUI: component and scope selection, focus order, arrow-key navigation between buttons, install/uninstall actions |
| `TestInstallOptions` / `TestMainDispatch` | Component flags (`--desktop`, `--app-menu`, `--file-assoc`), the all-disabled error, and which routine each CLI form dispatches to |
| `TestCodesignApp` / `TestCheckLaunchVerification` / `TestVerifyLaunchCommand` | macOS: re-signing the bundle after modification, and verifying it actually launches |
| `TestDarwinUTIDeclaration` / `TestDarwinDocTypeReplacement` / `TestDarwinDocumentIcon` / `TestDarwinAppIconOverride` | macOS `.pmeprj` UTI export, document type entries, and icon handling |
| `TestRegisterFileAssociationsDarwin` / `TestRefreshLaunchServices` | macOS Launch Services registration and refresh |
| `TestLinuxFileAssociations` / `TestCleanLinuxMimeapps` / `TestPatchLinuxDesktopEntry` | Linux MIME registration, desktop entry, and cleanup on removal |
| `TestLinuxDataHome` / `TestLinuxSystemDesktopEntry` | `XDG_DATA_HOME` for per-user paths, `/usr/share` for system scope |
| `TestWindowsAssocRefresh` / `TestComInitialized` | Windows association refresh (`SHChangeNotify`) and per-thread COM initialisation |
| `TestRemoveSystemScope` / `TestWindowsSystemRemove` | System-wide uninstall on each OS |
| `TestPythonForExecutable` / `TestSystemCondaSearch` | Resolving the interpreter that owns the installed command |
| `TestV301Fixes` | Regressions fixed in 3.0.1, kept as tests so they cannot come back |
| `TestResolveManualExecutable` / `TestInstallWithManualExePath` / `TestExePathCLI` / `TestTuiExePathField` | The manual executable path: validation (file, directory, quotes, env vars, bad input), `--exe-path` on install and `--check`, and the TUI field |
| `TestCondaPrefixMismatch` | `conda run` is only used when the executable really lives in the active `CONDA_PREFIX` |
| `TestSystemScopeDataDir` / `TestWindowsUserChoice` | System-scope icon location (shared, not the installing root's home) and clearing Explorer's pinned "open with" choice |

### `TestFindExecutable`

| Test | Scenario |
|---|---|
| `test_finds_exe_next_to_python_interpreter` | `Scripts/` sibling of `sys.executable` (venv/conda layout) |
| `test_finds_exe_in_python_dir` | Same dir as `sys.executable` (flat layouts) |
| `test_finds_exe_in_same_dir_as_python_unix` | Unix flat layout |
| `test_finds_exe_via_argv0_dir` | Direct console-script invocation (`sys.argv[0]` sibling) |
| `test_falls_back_to_shutil_which` | `shutil.which` fallback |
| `test_returns_none_when_not_found` | Graceful `None` return when executable is absent |
| `test_finds_exe_in_user_local_bin` | `~/.local/bin` user bin folder (Linux/macOS) |
| `test_finds_exe_in_macos_user_python_bin` | `~/Library/Python/*/bin` user packages (macOS) |
| `test_finds_exe_via_sysconfig_user_scheme_windows` | Windows `sysconfig` user scripts (`nt_user`) |
| `test_finds_exe_via_sysconfig_user_scheme_posix` | POSIX/macOS `sysconfig` user scripts (`posix_user` / `osx_framework_user`) |
| `test_finds_exe_in_localappdata_scripts` | Windows `%LOCALAPPDATA%\Programs\Python\Python*\Scripts` |
| `test_finds_exe_in_ms_store_python_scripts` | Windows Microsoft Store Python packages folder |
| `test_finds_exe_in_roaming_appdata_scripts` | Windows `%APPDATA%\Python\Python*\Scripts` |
| `test_finds_exe_in_user_conda_scripts` | Windows standard Conda user directory |
| `test_finds_exe_in_pyenv_versions` | User `~/.pyenv/versions/*/bin` directories |
| `test_finds_exe_in_custom_user_bin_directories` | Common `~/bin` or `~/.bin` directories |
| `test_finds_exe_in_unix_conda_envs` | Unix Conda environment directories |
| `test_finds_exe_in_pyenv_win` | Windows `~/.pyenv/pyenv-win/versions/*/Scripts` |
| `test_finds_exe_in_poetry_windows` | Windows Poetry environment scripts folder |
| `test_finds_exe_in_asdf` | ASDF Python installation directories |
| `test_finds_exe_in_mise` | Mise (RTX) Python installation directories |

## Why these tests exist

### Path detection (`find_executable`)

The installer searches many user-local Python package management layouts (including Microsoft Store, pyenv, ASDF, Mise, Poetry, and Conda). The tests mock environment configurations and filesystem lookups to guarantee accurate executable resolution across all platforms without requiring actual OS dependencies.

### Platform-Agnostic Execution

Every path resolution test mocks `platform.system()` and file check routines so that the entire test suite runs and passes on all platforms (Windows, macOS, and Linux) with **0 skipped tests** on CI.

### `python -m moleditpy_installer` support

`test_package_runnable_as_module` verifies the `__main__.py` module exists and is importable, which is the requirement for `python -m` to work.

## CI

`.github/workflows/ci.yml` runs four jobs:

| Job | Matrix | What it does |
|---|---|---|
| `test` | ubuntu / windows / macOS × Python 3.9, 3.11, 3.13 | the pytest suite |
| `smoke-macos` | macOS | a real end-to-end install and uninstall, per-user and system (sudo) |
| `smoke-windows` | Windows | the same, including the registry and Start Menu paths |
| `smoke-linux` | Ubuntu | the same, including `/usr/share` system scope |

The smoke jobs matter because most of this package's work happens *outside*
Python — code signing, registry writes, Launch Services, MIME databases. A unit
test can only assert that the right command was constructed; the smoke jobs
assert it actually worked on that OS.

## Invocation methods

```bash
# After pip install:
moleditpy-installer            # console_scripts entry point
python -m moleditpy_installer  # module invocation (also works)

# Check executable path:
moleditpy-installer --check
moleditpy-installer --check --exe-path /path/to/moleditpy   # validate a specific path

# Install using a manually specified executable (skips the search):
moleditpy-installer --exe-path /path/to/moleditpy

# Print version:
moleditpy-installer --version

# Remove shortcut and file associations:
moleditpy-installer --remove
python -m moleditpy_installer --remove
```

Note: `python -m moleditpy-installer` (with a hyphen) is **invalid** Python syntax. Always use the underscore form for `-m` invocation.
