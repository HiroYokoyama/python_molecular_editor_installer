# MoleditPy Installer

[![CI](https://github.com/HiroYokoyama/python_molecular_editor_installer/actions/workflows/ci.yml/badge.svg)](https://github.com/HiroYokoyama/python_molecular_editor_installer/actions/workflows/ci.yml)
[![PyPI Version](https://img.shields.io/pypi/v/moleditpy-installer.svg)](https://pypi.org/project/moleditpy-installer/)
[![Supported Python Versions](https://img.shields.io/pypi/pyversions/moleditpy-installer.svg)](https://pypi.org/project/moleditpy-installer/)

This package is a helper utility that automatically installs the correct version of `moleditpy` or `moleditpy-linux` for your OS, creates an application menu shortcut, and registers file associations (Windows and macOS).

## How to Use

1.  **Install**
    ```bash
    pip install moleditpy-installer
    ```
    This will automatically install the correct `moleditpy` package (for Windows/macOS) or `moleditpy-linux` (for Linux) as a dependency.

2.  **Create Shortcut**
    After installation, run the following command in your terminal to create the shortcut in your application menu (e.g., Start Menu on Windows, Applications on macOS) and register file associations for `.pmeprj` files (Windows and macOS).

    > **Security Note:** File associations for `.pmeraw` files have been intentionally removed. Opening `.pmeraw` files downloaded from the internet can be potentially unsecure, so they are no longer automatically associated with the application.

    ```bash
    moleditpy-installer
    ```

    You can also invoke it as a Python module (use an **underscore**, not a hyphen):

    ```bash
    python -m moleditpy_installer
    ```

    > **Note:** `python -m moleditpy-installer` (with a hyphen) is invalid Python syntax and will not work. Always use the underscore form (`moleditpy_installer`) with `-m`.

    > **Tip:** Run the installer from the Python environment where `moleditpy` is installed (e.g. after `conda activate <env>`). The installer verifies the launch command and warns you if the pairing cannot start MoleditPy.

3.  **Remove Shortcut**
    To remove the shortcut, unregister file associations, and clean up extracted icon files, run:

    ```bash
    moleditpy-installer --remove
    # or
    python -m moleditpy_installer --remove
    ```

4.  **Check Executable Location**
    To search for the `moleditpy` executable in the search paths and print the located path:

    ```bash
    moleditpy-installer --check
    ```
    This command returns exit code `0` if the executable is found, and `1` otherwise. On macOS it additionally verifies that the launcher's interpreter/script pairing can actually start MoleditPy.

    For the complete list of directories scanned on Windows, macOS, and Linux, see [docs/path.md](docs/path.md).

5.  **Print Version**
    To show the version of the installer:

    ```bash
    moleditpy-installer --version
    ```

6.  **Help**
    To see all available options, run:

    ```bash
    moleditpy-installer --help
    ```

## What the installer sets up

### Windows
- Start Menu and Desktop shortcuts (icon included).
- `.pmeprj` files open MoleditPy on double-click (per-user registry, no admin rights needed).
- Icons are stored under `%LOCALAPPDATA%\MoleditPy\installer` so they survive temp-folder cleanup.

### macOS
- A `MoleditPy.app` launcher in `~/Applications` and on the Desktop, with the MoleditPy icon.
- The launcher pairs the `moleditpy` script with the Python interpreter of **its own environment** (detected from the adjacent interpreter or the script's shebang), so it keeps working even when the installer runs from a different environment.
- MoleditPy always opens inside a **Terminal window**, so Python output and any errors stay visible. The first launch shows a one-time macOS consent prompt ("MoleditPy wants access to control Terminal") — click OK.
- Double-clicking `.pmeprj` files opens MoleditPy: the app bundle declares the `com.moleditpy.pmeprj` document type (exported UTI) and is registered with Launch Services.
- The bundle is ad-hoc code-signed after configuration; required on Apple Silicon.

### Linux
- Application-menu and Desktop `.desktop` entries (icon included).

`moleditpy-installer --remove` undoes all of the above for the current user.

## Version 2.0 highlights

- **Fixed:** silent launch failures on macOS caused by an invalidated app-bundle code signature (Apple Silicon refused to start the app and ignored its icon).
- **Fixed:** `ModuleNotFoundError: No module named 'moleditpy'` when the installer ran in a different Python environment than the one holding `moleditpy` — the launcher now uses the script's own interpreter and the command is verified at install time.
- **New:** MoleditPy launches in a visible Terminal window on macOS.
- **New:** `.pmeprj` double-click support on macOS via a proper exported UTI + Launch Services registration.
- **New:** `--check` verifies launchability on macOS; `--remove` also unregisters the bundle from Launch Services and removes extracted icons.
- Icons no longer live in the temp folder (Windows shortcut/registry icons no longer break after cleanup).