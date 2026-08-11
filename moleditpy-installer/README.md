# MoleditPy Installer

[![CI](https://github.com/HiroYokoyama/python_molecular_editor_installer/actions/workflows/ci.yml/badge.svg)](https://github.com/HiroYokoyama/python_molecular_editor_installer/actions/workflows/ci.yml)
[![PyPI Version](https://img.shields.io/pypi/v/moleditpy-installer.svg)](https://pypi.org/project/moleditpy-installer/)
[![Supported Python Versions](https://img.shields.io/pypi/pyversions/moleditpy-installer.svg)](https://pypi.org/project/moleditpy-installer/)

This package is a helper utility that automatically installs the correct version of `moleditpy` or `moleditpy-linux` for your OS, creates an application menu shortcut, and registers the `.pmeprj` double-click file association on Windows, macOS, and Linux.

![installer](https://raw.githubusercontent.com/HiroYokoyama/python_molecular_editor_installer/main/img/installer.png)

## How to Use

1.  **Install**
    ```bash
    pip install moleditpy-installer
    ```
    This will automatically install the correct `moleditpy` package (for Windows/macOS) or `moleditpy-linux` (for Linux) as a dependency.

2.  **Run the interactive installer (TUI)**
    Run the following command in your terminal. In an interactive terminal this opens a TUI where you pick the components — Desktop shortcut, application-menu entry, `.pmeprj` file association — and the scope (per-user or system-wide), then press **Install**:

    ```bash
    moleditpy-installer
    ```

    Defaults: Desktop shortcut **off**, application menu **on**, file association **on**, per-user scope, executable **auto-detected**. The **Executable path** field at the bottom of the panel is optional — leave it empty to auto-detect, or type the path to the `moleditpy` executable (or the `Scripts`/`bin` folder holding it) when your installation lives somewhere the search does not cover. The **Install** button is focused on start, so pressing **Enter** immediately installs with the defaults. Move between widgets with **Tab** / **Shift+Tab** (the arrow keys also switch between the Install / Uninstall / Quit buttons). After a successful install or uninstall the TUI stays open for two seconds, then exits and replays the full log in the terminal.

    **Non-interactive / scripted use** (also what runs automatically when there is no terminal):

    ```bash
    moleditpy-installer --no-tui                 # install with the defaults
    moleditpy-installer --desktop                # also create a Desktop shortcut
    moleditpy-installer --no-file-assoc          # skip the .pmeprj association
    sudo moleditpy-installer --system            # system-wide (admin terminal on Windows)
    moleditpy-installer --exe-path /opt/env/bin/moleditpy   # point at the executable yourself
    ```

    Any explicit option skips the TUI.

    **Manual executable path.** If the automatic search cannot find your installation, pass `--exe-path` (or fill in the TUI field). It accepts the executable itself or the directory holding it, expands `~` and environment variables, and strips surrounding quotes:

    ```bash
    moleditpy-installer --exe-path "~/my envs/chem/bin"        # a Scripts/bin directory
    moleditpy-installer --check --exe-path C:\envs\chem\Scripts\moleditpy.exe
    ```

    A path given this way is never silently replaced by a search result: if it is wrong, the installer reports why and stops.

    > **Security Note:** File associations for `.pmeraw` files have been intentionally removed. Opening `.pmeraw` files downloaded from the internet can be potentially unsecure, so they are no longer automatically associated with the application.

    You can also invoke it as a Python module (use an **underscore**, not a hyphen):

    ```bash
    python -m moleditpy_installer
    ```

    > **Note:** `python -m moleditpy-installer` (with a hyphen) is invalid Python syntax and will not work. Always use the underscore form (`moleditpy_installer`) with `-m`.

    > **Tip:** Run the installer from the Python environment where `moleditpy` is installed (e.g. after `conda activate <env>`). The installer verifies the launch command and warns you if the pairing cannot start MoleditPy.

3.  **Uninstall**
    To remove the shortcuts, unregister file associations, and clean up extracted icon files, run (add `--system` for a system-wide install; `--remove` remains as a deprecated alias):

    ```bash
    moleditpy-installer --uninstall
    # or
    python -m moleditpy_installer --uninstall
    ```

    > **Note:** this removes the shortcuts and file associations only. To fully remove MoleditPy itself, also run `pip uninstall moleditpy` (or `pip uninstall moleditpy-linux` on Linux).

4.  **Check Executable Location**
    To search for the `moleditpy` executable in the search paths and print the located path:

    ```bash
    moleditpy-installer --check
    ```
    This command returns exit code `0` if the executable is found, and `1` otherwise. On macOS it additionally verifies that the launcher's interpreter/script pairing can actually start MoleditPy. Add `--exe-path <path>` to validate a specific location instead of searching.

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
- Start Menu shortcut (icon included); Desktop shortcut when enabled (`--desktop` or the TUI checkbox). With `--system` (admin) the shortcuts go to the all-users locations and the association to HKLM.
- `.pmeprj` files open MoleditPy on double-click (per-user registry, no admin rights needed).
- Icons are stored under `%LOCALAPPDATA%\MoleditPy\installer` so they survive temp-folder cleanup.

### macOS
- A `MoleditPy.app` launcher in `~/Applications` (or `/Applications` with `--system`), plus a Desktop copy when enabled, with the MoleditPy icon.
- The launcher pairs the `moleditpy` script with the Python interpreter of **its own environment** (detected from the adjacent interpreter or the script's shebang), so it keeps working even when the installer runs from a different environment.
- MoleditPy always opens inside a **Terminal window**, so Python output and any errors stay visible. The first launch shows a one-time macOS consent prompt ("MoleditPy wants access to control Terminal") — click OK.
- Double-clicking `.pmeprj` files opens MoleditPy: the app bundle declares the `com.moleditpy.pmeprj` document type (exported UTI) and is registered with Launch Services. `.pmeprj` documents get their own file icon, matching the Windows behavior.
- The bundle is ad-hoc code-signed after configuration; required on Apple Silicon.

### Linux
- Application-menu `.desktop` entry (icon included; Desktop copy when enabled), launched in a terminal so output stays visible (matching macOS). With `--system` the entry goes to `/usr/share/applications`.
- `.pmeprj` files open MoleditPy on double-click: a per-user `application/x-moleditpy-project` MIME type is registered (freedesktop shared-mime-info, no root needed) and set as the default handler.
- `.pmeprj` documents get their own file icon in file managers, matching Windows and macOS.

`moleditpy-installer --uninstall` undoes all of the above for the current user (add `--system` for system-wide installs).

## Version 3.1 highlights

- **New:** manual executable path — `--exe-path` on the command line and an **Executable path** field in the TUI, for installations the automatic search cannot find. Accepts the executable or the directory holding it; a wrong path is reported instead of being silently replaced by a search result.
- **Fixed:** `conda run` was applied to executables belonging to a *different* environment, producing a launcher that failed with `ModuleNotFoundError: No module named 'moleditpy'`. It is now used only when the executable really lives in the active `CONDA_PREFIX`.
- **Fixed:** system-wide installs referenced icons in the installing user's private directory (`%LOCALAPPDATA%`, or `/root/.moleditpy` under `sudo`), so other users saw a blank icon. Shared scopes now use `%PROGRAMDATA%`, `/usr/share`, and `/usr/local/share` (macOS).
- **Fixed:** on Windows, an earlier "Open with" choice pinned by Explorer kept overriding a freshly installed `.pmeprj` association.
- **Fixed:** `--check` named the same command twice in its failure message on Linux.

## Version 3.0 highlights

- **New:** interactive Textual TUI — pick components and scope, watch the log, press Install/Remove.
- **New:** component selection (`--desktop`, `--app-menu`, `--file-assoc`) with safer defaults (no Desktop shortcut unless requested).
- **New:** system-wide scope on Linux (`/usr/share`), macOS (`/Applications`), and Windows (HKLM + all-users Start Menu; admin terminal) — all requiring sudo/admin.
- Per-user Linux paths now honor `XDG_DATA_HOME`.
- End-to-end smoke tests on all three OSes in CI, including the sudo/system path.

## Version 2.0 highlights

- **Fixed:** silent launch failures on macOS caused by an invalidated app-bundle code signature (Apple Silicon refused to start the app and ignored its icon).
- **Fixed:** `ModuleNotFoundError: No module named 'moleditpy'` when the installer ran in a different Python environment than the one holding `moleditpy` — the launcher now uses the script's own interpreter and the command is verified at install time.
- **New:** MoleditPy launches in a visible Terminal window on macOS.
- **New:** `.pmeprj` double-click support on macOS via a proper exported UTI + Launch Services registration.
- **New:** `.pmeprj` double-click support and document icon on Linux (per-user MIME registration).
- **New:** `--check` verifies launchability on macOS; `--remove` also unregisters the bundle from Launch Services and removes extracted icons.
- Icons no longer live in the temp folder (Windows shortcut/registry icons no longer break after cleanup).
