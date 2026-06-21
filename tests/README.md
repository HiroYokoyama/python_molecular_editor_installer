# Testing Guide — moleditpy-installer

## Running the tests

```bash
# From the root directory of the repository:
python -m pytest tests/ -v

# With coverage:
python -m pytest tests/ -v --cov=moleditpy_installer --cov-report=term-missing
```

## Test structure

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

## Invocation methods

```bash
# After pip install:
moleditpy-installer            # console_scripts entry point
python -m moleditpy_installer  # module invocation (also works)

# Check executable path:
moleditpy-installer --check

# Print version:
moleditpy-installer --version

# Remove shortcut and file associations:
moleditpy-installer --remove
python -m moleditpy_installer --remove
```

Note: `python -m moleditpy-installer` (with a hyphen) is **invalid** Python syntax. Always use the underscore form for `-m` invocation.
