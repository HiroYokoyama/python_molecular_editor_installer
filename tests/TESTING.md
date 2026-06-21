# Testing Guide — moleditpy-installer

## Running the tests

```bash
# From the moleditpy-installer/ directory:
python -m pytest tests/ -v

# With coverage:
python -m pytest tests/ -v --cov=moleditpy_installer --cov-report=term-missing
```

## Test structure

| Test class / function | What it covers |
|---|---|
| `TestFindExecutable` | Path detection logic in `find_executable()` |
| `TestGetIconPath` | Icon file resolution per OS |
| `TestInstall` | High-level `install()` smoke tests |
| `TestMainCLI` | CLI argument parsing (`--remove` flag) |
| `test_package_runnable_as_module` | `python -m moleditpy_installer` works |

### `TestFindExecutable`

| Test | Scenario |
|---|---|
| `test_finds_exe_next_to_python_interpreter` | `Scripts/` sibling of `sys.executable` — the primary path used under `python -m` |
| `test_finds_exe_in_python_dir` | Same dir as `sys.executable` (Windows without a Scripts subdir, or env with flat layout) |
| `test_finds_exe_in_same_dir_as_python_unix` | Unix flat layout — skipped on Windows |
| `test_finds_exe_via_argv0_dir` | Direct console-script invocation (`sys.argv[0]` sibling) |
| `test_falls_back_to_shutil_which` | `shutil.which` fallback when nothing found locally |
| `test_returns_none_when_not_found` | Graceful `None` return when executable is absent |

## Why these tests exist

### Path detection (`find_executable`)

The old code used only `sys.argv[0]` to derive the Scripts directory. When the installer
is invoked as `python -m moleditpy_installer`, `sys.argv[0]` points inside the package
directory — not the environment's `Scripts/` folder. The new implementation checks
`sys.executable`'s sibling directories first, which is reliable regardless of invocation
style. The tests confirm all three code paths work independently.

### `python -m moleditpy_installer` support

`test_package_runnable_as_module` verifies the `__main__.py` module exists and is
importable, which is the only requirement for `python -m` to work.

## Invocation methods

```bash
# After pip install:
moleditpy-installer            # console_scripts entry point
python -m moleditpy_installer  # module invocation (also works)

# Remove shortcut and file associations:
moleditpy-installer --remove
python -m moleditpy_installer --remove
```

Note: `python -m moleditpy-installer` (with a hyphen) is **invalid** Python syntax.
Always use the underscore form for `-m` invocation.
