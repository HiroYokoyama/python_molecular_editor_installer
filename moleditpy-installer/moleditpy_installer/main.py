"""
MoleditPy Installer Script
==========================

This script creates a shortcut for the moleditpy application and registers file
associations on Windows. It is designed to be run after installing the
'moleditpy-installer' package.
"""

import argparse
import contextlib
import importlib.resources
import io
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import winreg
except ImportError:
    winreg = None

# pyshortcuts prints conda diagnostics ("No conda env active, ...") at
# import time; keep that noise out of every CLI/TUI invocation.
with contextlib.redirect_stdout(io.StringIO()):
    from pyshortcuts import make_shortcut

# System-wide conda locations on Linux/macOS (home-dir installs are handled
# separately). /opt/miniconda3 is the macOS pkg-installer default; /opt/conda
# is the docker/miniforge convention. Module-level so tests can patch it.
_SYSTEM_CONDA_ROOTS = [
    Path("/opt/miniconda3"),
    Path("/opt/anaconda3"),
    Path("/opt/conda"),
    Path("/opt/homebrew/Caskroom/miniconda/base"),
    Path("/usr/local/miniconda3"),
    Path("/usr/local/anaconda3"),
]

# MIME type registered for .pmeprj on Linux; the icon name is derived from
# it per the freedesktop spec ('/' -> '-').
LINUX_MIME_TYPE = "application/x-moleditpy-project"
_LINUX_MIME_ICON_NAME = "application-x-moleditpy-project"
_LINUX_MIME_ICON_SIZES = (16, 22, 24, 32, 48, 64, 128, 256)


@dataclass
class InstallOptions:
    """
    What to install and at which level.

    Defaults: no Desktop shortcut, application-menu entry on, .pmeprj
    file association on, per-user scope.
    """

    desktop: bool = False
    app_menu: bool = True
    file_assoc: bool = True
    system: bool = False  # system-wide (sudo/admin) instead of per-user


@contextlib.contextmanager
def _com_initialized():
    """
    Initialize COM for the current thread on Windows.

    pyshortcuts creates .lnk files through COM, which must be initialized
    per-thread. The TUI runs install() in a worker thread, where shortcut
    creation otherwise fails with CO_E_NOTINITIALIZED
    ("CoInitialize has not been called").
    """
    initialized = False
    if platform.system() == "Windows":
        try:
            import pythoncom

            pythoncom.CoInitialize()
            initialized = True
        except ImportError:
            pass
    try:
        yield
    finally:
        if initialized:
            import pythoncom

            pythoncom.CoUninitialize()


def is_root() -> bool:
    """True when running with root (POSIX) or admin (Windows) privileges."""
    if platform.system() == "Windows":
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (OSError, AttributeError):
            return False
    geteuid = getattr(os, "geteuid", None)
    return geteuid is not None and geteuid() == 0


def linux_data_home(system: bool = False) -> Path:
    """freedesktop data dir: per-user ~/.local/share or system /usr/share."""
    if system:
        return Path("/usr/share")
    xdg = os.environ.get("XDG_DATA_HOME")
    return Path(xdg) if xdg else Path.home() / ".local" / "share"


def get_persistent_data_dir(system: bool = False) -> Path:
    """
    Per-user directory for extracted installer assets (icons).

    Shortcuts and registry entries reference these files long after the
    installer exits, so they must not live in the system temp directory
    (which is periodically cleaned, silently breaking the icons).
    """
    if platform.system() == "Windows":
        if system:
            # all users must be able to read icons referenced from HKLM
            base = os.environ.get("PROGRAMDATA") or "C:/ProgramData"
        else:
            base = os.environ.get("LOCALAPPDATA") or str(
                Path.home() / "AppData" / "Local"
            )
        data_dir = Path(base) / "MoleditPy" / "installer"
    else:
        data_dir = Path.home() / ".moleditpy" / "installer"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _extract_data_file(file_name: str, system: bool = False) -> Optional[str]:
    """Extract a packaged data file to the persistent data dir and return its path."""
    try:
        ref = importlib.resources.files("moleditpy_installer") / "data" / file_name
        content = ref.read_bytes()
        out_path = get_persistent_data_dir(system) / file_name
        out_path.write_bytes(content)
        return str(out_path)
    except (OSError, ModuleNotFoundError, ValueError) as e:
        print(f"Error extracting data file {file_name}: {e}")
        return None


def get_icon_path() -> Optional[str]:
    """
    Gets the absolute path to the correct icon file based on the OS.

    Returns:
        Optional[str]: The path to the icon file, or None if not found or OS unsupported.
    """
    system = platform.system()

    if system == "Windows":
        icon_name = "icon.ico"
    elif system == "Darwin":  # macOS
        icon_name = "icon.icns"
    elif system == "Linux":
        icon_name = "icon.png"
    else:
        print(f"Warning: Unsupported operating system for icon selection: {system}")
        return None

    return _extract_data_file(icon_name)


def find_executable(name: str) -> Optional[str]:
    """
    Finds the path to the specified executable.

    Search order:
      1. Scripts/bin directory next to sys.executable (handles venv/conda layout).
      2. Same directory as sys.executable.
      3. Same directory as sys.argv[0] (direct script invocation).
      4. User-local install dirs (~/.local/bin on Linux/macOS; user-level Scripts on Windows).
      5. System PATH via shutil.which.

    Args:
        name (str): The name of the executable (e.g., 'moleditpy').

    Returns:
        Optional[str]: The absolute path to the executable, or None if not found.
    """
    system = platform.system()

    def _check(path: Path) -> Optional[str]:
        candidate = path / name
        if system == "Windows" and not candidate.suffix:
            candidate = candidate.with_suffix(".exe")
        if candidate.is_file() and os.access(candidate, os.X_OK):
            result = str(candidate)
            print(f"Found executable: {result}")
            return result
        return None

    # 1 & 2. Dirs relative to the Python interpreter (reliable even under `python -m`)
    python_dir = Path(sys.executable).resolve().parent
    for scripts_dir in (
        python_dir / "Scripts",
        python_dir,
    ):  # Windows first, Unix second
        found = _check(scripts_dir)
        if found:
            return found

    # 3. Same directory as the entry-point script (pip-installed console_scripts wrapper)
    script_dir = Path(sys.argv[0]).resolve().parent
    found = _check(script_dir)
    if found:
        return found

    # 4. User-local installation directories (pip install --user)
    if system == "Windows":
        # Check sysconfig's nt_user scheme first
        try:
            nt_user_scripts = Path(sysconfig.get_path("scripts", "nt_user"))
            found = _check(nt_user_scripts)
            if found:
                return found
        except (KeyError, ValueError, OSError):
            pass

        # Check standard user Python installer paths
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            # %LOCALAPPDATA%\Programs\Python\PythonXY\Scripts  (user-level installer)
            for scripts_dir in sorted(
                (Path(local_app_data) / "Programs").glob("Python*/Scripts"),
                reverse=True,  # prefer the newest Python version
            ):
                found = _check(scripts_dir)
                if found:
                    return found

            # Microsoft Store Python user packages
            for scripts_dir in sorted(
                (Path(local_app_data) / "Packages").glob(
                    "PythonSoftwareFoundation.Python.*/LocalCache/local-packages/Python*/Scripts"
                ),
                reverse=True,  # prefer the newest Python version
            ):
                found = _check(scripts_dir)
                if found:
                    return found

        # %APPDATA%\Python\PythonXY\Scripts (alternative user-site path)
        app_data = os.environ.get("APPDATA")
        if app_data:
            for scripts_dir in sorted(
                (Path(app_data) / "Python").glob("Python*/Scripts"),
                reverse=True,
            ):
                found = _check(scripts_dir)
                if found:
                    return found

        # Common user-local Conda installations on Windows
        user_home = Path.home()
        conda_search_paths = [
            user_home / "miniconda3" / "Scripts",
            user_home / "anaconda3" / "Scripts",
            user_home / "AppData" / "Local" / "miniconda3" / "Scripts",
            user_home / "AppData" / "Local" / "anaconda3" / "Scripts",
        ]
        for path in conda_search_paths:
            found = _check(path)
            if found:
                return found

        # pyenv-win versions on Windows (e.g., ~/.pyenv/pyenv-win/versions/X.Y.Z/Scripts)
        for scripts_dir in sorted(
            (Path.home() / ".pyenv" / "pyenv-win" / "versions").glob("*/Scripts"),
            reverse=True,
        ):
            found = _check(scripts_dir)
            if found:
                return found

        # Poetry global binaries on Windows
        poetry_paths = []
        if app_data:
            poetry_paths.append(Path(app_data) / "pypoetry" / "venv" / "Scripts")
        poetry_paths.append(Path.home() / ".poetry" / "bin")
        for path in poetry_paths:
            found = _check(path)
            if found:
                return found

    else:
        # Check standard user directories via sysconfig schemes
        # (e.g. posix_user, osx_framework_user)
        for scheme in ("posix_user", "osx_framework_user"):
            if scheme in sysconfig.get_scheme_names():
                try:
                    found = _check(Path(sysconfig.get_path("scripts", scheme)))
                    if found:
                        return found
                except (KeyError, ValueError, OSError):
                    pass

        # ~/.local/bin is the standard target for `pip install --user` on Linux/macOS
        found = _check(Path.home() / ".local" / "bin")
        if found:
            return found

        # On macOS, user-local binaries might also go to ~/Library/Python/X.Y/bin
        if system == "Darwin":
            for scripts_dir in sorted(
                (Path.home() / "Library" / "Python").glob("*/bin"),
                reverse=True,  # prefer the newest Python version
            ):
                found = _check(scripts_dir)
                if found:
                    return found

        # pyenv version binaries (e.g., ~/.pyenv/versions/3.x.x/bin)
        for scripts_dir in sorted(
            (Path.home() / ".pyenv" / "versions").glob("*/bin"),
            reverse=True,
        ):
            found = _check(scripts_dir)
            if found:
                return found

        # ASDF python installations (e.g., ~/.asdf/installs/python/X.Y.Z/bin)
        for scripts_dir in sorted(
            (Path.home() / ".asdf" / "installs" / "python").glob("*/bin"),
            reverse=True,
        ):
            found = _check(scripts_dir)
            if found:
                return found

        # Mise (formerly RTX) python installations
        # (e.g., ~/.local/share/mise/installs/python/X.Y.Z/bin)
        for scripts_dir in sorted(
            (Path.home() / ".local" / "share" / "mise" / "installs" / "python").glob(
                "*/bin"
            ),
            reverse=True,
        ):
            found = _check(scripts_dir)
            if found:
                return found

        # Common user Conda installations and environment folders
        conda_globs = [
            (Path.home() / "miniconda3" / "envs").glob("*/bin"),
            (Path.home() / "anaconda3" / "envs").glob("*/bin"),
            (Path.home() / ".conda" / "envs").glob("*/bin"),
        ]
        for g in conda_globs:
            for scripts_dir in sorted(g, reverse=True):
                found = _check(scripts_dir)
                if found:
                    return found

        # System-wide Conda installations (e.g. /opt/miniconda3 — the macOS
        # pkg-installer default) and their environments
        for conda_root in _SYSTEM_CONDA_ROOTS:
            found = _check(conda_root / "bin")
            if found:
                return found
            for scripts_dir in sorted(
                (conda_root / "envs").glob("*/bin"), reverse=True
            ):
                found = _check(scripts_dir)
                if found:
                    return found

        # Other Unix-like package manager and user directories
        unix_search_paths = [
            Path.home() / "miniconda3" / "bin",
            Path.home() / "anaconda3" / "bin",
            Path.home() / ".linuxbrew" / "bin",
            Path.home() / ".nix-profile" / "bin",
            Path.home() / ".guix-profile" / "bin",
            Path.home() / ".asdf" / "shims",
            Path.home() / ".poetry" / "bin",
            Path.home() / "bin",
            Path.home() / ".bin",
        ]
        for path in unix_search_paths:
            found = _check(path)
            if found:
                return found

    # 5. Fallback: system PATH
    path_from_shutil = shutil.which(name)
    if path_from_shutil:
        print(f"Found executable in system PATH: {path_from_shutil}")
        return path_from_shutil

    return None


def _notify_windows_assoc_changed() -> None:
    """
    Tell Explorer the file associations changed.

    Without SHChangeNotify(SHCNE_ASSOCCHANGED) Explorer keeps showing the
    old association/icon from its cache until the next logon.
    """
    try:
        import ctypes

        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0
        ctypes.windll.shell32.SHChangeNotify(
            SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None
        )
    except (OSError, AttributeError):
        pass  # not on Windows / shell32 unavailable


def register_file_associations_windows(
    exe_path: str, icon_path: Optional[str], system: bool = False
) -> bool:
    """
    Register file associations for .pmeprj files on Windows.

    Args:
        exe_path (str): Path to the executable to associate.
        icon_path (Optional[str]): Path to the icon file for the association.
        system (bool): Register machine-wide under HKLM (requires admin)
            instead of per-user under HKCU.

    Returns:
        bool: True if successful, False otherwise.
    """
    if platform.system() != "Windows":
        return False

    root = winreg.HKEY_LOCAL_MACHINE if system else winreg.HKEY_CURRENT_USER

    try:
        extensions = [".pmeprj"]
        prog_id = "MoleditPy.File"
        app_name = "MoleditPy"

        print("Registering file associations...")

        # Create ProgID
        with winreg.CreateKey(root, f"Software\\Classes\\{prog_id}") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, f"{app_name} File")

        # Set default icon
        if icon_path and os.path.exists(icon_path):
            with winreg.CreateKey(
                root, f"Software\\Classes\\{prog_id}\\DefaultIcon"
            ) as key:
                winreg.SetValue(key, "", winreg.REG_SZ, icon_path)

        # Friendly context-menu label for the open verb
        with winreg.CreateKey(
            root, f"Software\\Classes\\{prog_id}\\shell\\open"
        ) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, f"Open with {app_name}")

        # Set open command
        # Quote paths to handle spaces
        command = f'"{exe_path}" "%1"'
        with winreg.CreateKey(
            root,
            f"Software\\Classes\\{prog_id}\\shell\\open\\command",
        ) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, command)

        # Associate extensions
        for ext in extensions:
            with winreg.CreateKey(root, f"Software\\Classes\\{ext}") as key:
                winreg.SetValue(key, "", winreg.REG_SZ, prog_id)
            print(f"  Associated {ext} with {app_name}")

        _notify_windows_assoc_changed()
        print("File associations registered successfully.")
        return True

    except OSError as e:
        print(f"Failed to register file associations: {e}")
        return False


def register_file_associations_darwin(app_path: Path) -> bool:
    """
    Register file associations for .pmeprj files in the Info.plist of the macOS app bundle.

    Args:
        app_path (Path): Path to the .app bundle directory.

    Returns:
        bool: True if successful, False otherwise.
    """
    if platform.system() != "Darwin":
        return False

    plist_path = app_path / "Contents" / "Info.plist"
    if not plist_path.exists():
        print(f"Warning: Info.plist not found at {plist_path}")
        return False

    try:
        # Dedicated document icon (the macOS counterpart of Windows'
        # DefaultIcon registry value). Falls back to the app icon if the
        # file icon cannot be extracted.
        doc_icon_name = "applet.icns"
        file_icon_path = _extract_data_file("file_icon.icns")
        if file_icon_path:
            resources_dir = app_path / "Contents" / "Resources"
            resources_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_icon_path, resources_dir / "file_icon.icns")
            doc_icon_name = "file_icon.icns"

        with open(plist_path, "rb") as fp:
            pl = plistlib.load(fp)

        doc_types = pl.get("CFBundleDocumentTypes", [])

        # Check if already present
        already_present = False
        for doc in doc_types:
            exts = doc.get("CFBundleTypeExtensions", [])
            if "pmeprj" in exts:
                already_present = True
                break

        if not already_present:
            new_doc_type = {
                "CFBundleTypeExtensions": ["pmeprj"],
                "CFBundleTypeName": "MoleditPy Project File",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
                "LSItemContentTypes": ["com.moleditpy.pmeprj"],
                "CFBundleTypeIconFile": doc_icon_name,
            }
            # Replace, don't append: osacompile applets ship a default
            # document type, and the launcher must claim ONLY .pmeprj.
            pl["CFBundleDocumentTypes"] = [new_doc_type]

            # Export a UTI for .pmeprj: modern macOS binds document types
            # through UTIs, and an unknown extension without one only gets
            # a fragile dynamic UTI.
            exported = pl.get("UTExportedTypeDeclarations", [])
            if not any(
                d.get("UTTypeIdentifier") == "com.moleditpy.pmeprj" for d in exported
            ):
                exported.append(
                    {
                        "UTTypeIdentifier": "com.moleditpy.pmeprj",
                        "UTTypeDescription": "MoleditPy Project File",
                        "UTTypeConformsTo": ["public.data"],
                        "UTTypeIconFile": doc_icon_name,
                        "UTTypeTagSpecification": {
                            "public.filename-extension": ["pmeprj"],
                        },
                    }
                )
                pl["UTExportedTypeDeclarations"] = exported

            with open(plist_path, "wb") as fp:
                plistlib.dump(pl, fp)

            # Touch the app bundle to notify Launch Services of changes
            try:
                os.utime(str(app_path), None)
            except OSError:
                pass

            print("Successfully registered file associations in Info.plist.")
            return True

        return True

    except (OSError, ValueError) as e:
        # plistlib.InvalidFileException is a ValueError subclass
        print(f"Warning: Failed to update Info.plist: {e}")
        return False


def _run_quiet(cmd: list) -> bool:
    """Run a helper command best-effort: missing tools are not an error."""
    try:
        # Generous timeout: rebuilding the system MIME database
        # (update-mime-database /usr/share/mime) processes every installed
        # type and can exceed a minute on slow machines.
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _patch_linux_desktop_entry(desktop_path: Path) -> bool:
    """
    Post-edit a pyshortcuts-generated .desktop file: bind the .pmeprj MIME
    type and run in a terminal (matching the macOS launcher behavior, so
    Python output and errors stay visible).
    """
    if not desktop_path.is_file():
        return False

    try:
        lines = desktop_path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines:
            if line.startswith("Terminal="):
                line = "Terminal=true"
            elif line.startswith("MimeType="):
                continue  # rewritten below
            elif line.startswith("Exec=") and "%f" not in line and "%F" not in line:
                # accept a file argument from the file manager
                line = line.rstrip() + " %f"
            out.append(line)
        if not any(ln == "Terminal=true" for ln in out):
            out.append("Terminal=true")
        out.append(f"MimeType={LINUX_MIME_TYPE};")
        desktop_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        return True
    except OSError as e:
        print(f"Warning: could not update {desktop_path}: {e}")
        return False


def register_file_associations_linux(system: bool = False) -> bool:
    """
    Register the .pmeprj MIME type, its file icon, and the default handler
    on Linux (freedesktop shared-mime-info). Per-user by default; with
    ``system=True`` writes under /usr/share (requires root).
    """
    if platform.system() != "Linux":
        return False

    try:
        print("Registering file associations...")
        data_home = linux_data_home(system)

        # 1. MIME type definition
        mime_dir = data_home / "mime"
        packages_dir = mime_dir / "packages"
        packages_dir.mkdir(parents=True, exist_ok=True)
        mime_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="{LINUX_MIME_TYPE}">
    <comment>MoleditPy Project File</comment>
    <icon name="{_LINUX_MIME_ICON_NAME}"/>
    <glob pattern="*.pmeprj"/>
  </mime-type>
</mime-info>
"""
        (packages_dir / "moleditpy.xml").write_text(mime_xml, encoding="utf-8")
        _run_quiet(["update-mime-database", str(mime_dir)])

        # 2. Document icon for the MIME type (counterpart of the Windows
        # DefaultIcon registry value / macOS file_icon.icns). Every standard
        # hicolor size: file managers request small sizes (16-64) and a
        # 256px-only icon loses the lookup, leaving the generic blank page.
        for size in _LINUX_MIME_ICON_SIZES:
            data_name = "file_icon.png" if size == 256 else f"file_icon_{size}.png"
            icon_png = _extract_data_file(data_name)
            if not icon_png:
                continue
            mimetypes_icon_dir = (
                data_home / "icons" / "hicolor" / f"{size}x{size}" / "mimetypes"
            )
            mimetypes_icon_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(icon_png, mimetypes_icon_dir / f"{_LINUX_MIME_ICON_NAME}.png")
        # -f -t: the per-user hicolor dir has no index.theme, so the plain
        # call fails and any stale icon-theme.cache keeps hiding the icon.
        _run_quiet(
            [
                "gtk-update-icon-cache",
                "-f",
                "-t",
                str(data_home / "icons" / "hicolor"),
            ]
        )

        # 3. Bind the MIME type to the .desktop entry and set it as default
        apps_dir = data_home / "applications"
        _patch_linux_desktop_entry(apps_dir / "MoleditPy.desktop")
        _patch_linux_desktop_entry(Path.home() / "Desktop" / "MoleditPy.desktop")
        _run_quiet(["update-desktop-database", str(apps_dir)])
        if not system:
            # per-user default handler; system scope has no mimeapps default
            _run_quiet(["xdg-mime", "default", "MoleditPy.desktop", LINUX_MIME_TYPE])

        print(f"  Associated .pmeprj with MoleditPy ({LINUX_MIME_TYPE})")
        print("File associations registered successfully.")
        return True

    except OSError as e:
        print(f"Failed to register file associations: {e}")
        return False


def _clean_linux_mimeapps() -> None:
    """Drop MoleditPy's MIME entries from the per-user mimeapps.list files
    (xdg-mime has no 'unset'; a dangling default otherwise remains)."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    candidates = [
        config_home / "mimeapps.list",
        linux_data_home() / "applications" / "mimeapps.list",  # legacy location
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            kept = [line for line in lines if LINUX_MIME_TYPE not in line]
            if len(kept) != len(lines):
                path.write_text("\n".join(kept) + "\n", encoding="utf-8")
                print(f"  Cleaned {path}")
        except OSError as e:
            print(f"  Failed to clean {path}: {e}")


def unregister_file_associations_linux(system: bool = False) -> None:
    """Remove the .pmeprj MIME type, its icon, and refresh the databases."""
    if platform.system() != "Linux":
        return

    print("Unregistering file associations...")
    data_home = linux_data_home(system)
    mime_dir = data_home / "mime"
    for path in (
        mime_dir / "packages" / "moleditpy.xml",
        *(
            data_home
            / "icons"
            / "hicolor"
            / f"{size}x{size}"
            / "mimetypes"
            / f"{_LINUX_MIME_ICON_NAME}.png"
            for size in _LINUX_MIME_ICON_SIZES
        ),
    ):
        try:
            if path.exists():
                path.unlink()
                print(f"  Removed: {path}")
        except OSError as e:
            print(f"  Failed to remove {path}: {e}")

    if not system:
        _clean_linux_mimeapps()

    _run_quiet(["update-mime-database", str(mime_dir)])
    _run_quiet(["update-desktop-database", str(data_home / "applications")])
    _run_quiet(
        ["gtk-update-icon-cache", "-f", "-t", str(data_home / "icons" / "hicolor")]
    )
    print("File associations unregistered.")


def write_linux_system_desktop_entry(
    exe_command: str, icon_path: Optional[str]
) -> bool:
    """
    Write /usr/share/applications/MoleditPy.desktop for a system-wide
    install (pyshortcuts only supports per-user locations).
    """
    apps_dir = linux_data_home(system=True) / "applications"
    try:
        apps_dir.mkdir(parents=True, exist_ok=True)
        icon_line = f"Icon={icon_path}\n" if icon_path else ""
        # Quote a bare executable path containing spaces, or the Exec line
        # is split at the space by the desktop-entry spec.
        if " " in exe_command and not exe_command.startswith('"'):
            exe_command = f'"{exe_command}"'
        (apps_dir / "MoleditPy.desktop").write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=MoleditPy\n"
            "Comment=Molecular editor for DFT preparation\n"
            f"Exec={exe_command} %f\n"
            f"{icon_line}"
            "Terminal=true\n"
            "Categories=Science;Chemistry;\n"
            f"MimeType={LINUX_MIME_TYPE};\n",
            encoding="utf-8",
        )
        _run_quiet(["update-desktop-database", str(apps_dir)])
        print(
            f"Created system application-menu entry: {apps_dir / 'MoleditPy.desktop'}"
        )
        return True
    except OSError as e:
        print(f"Failed to write system desktop entry: {e}")
        return False


def delete_registry_tree(key, sub_key):
    """
    Deletes a registry key and all its subkeys.
    """
    try:
        current_key = winreg.OpenKey(key, sub_key, 0, winreg.KEY_ALL_ACCESS)
        num_subkeys = winreg.QueryInfoKey(current_key)[0]
        for _ in range(num_subkeys):
            # Always delete index 0 — keys shift down as each is removed
            subkey_name = winreg.EnumKey(current_key, 0)
            delete_registry_tree(current_key, subkey_name)

        winreg.CloseKey(current_key)
        winreg.DeleteKey(key, sub_key)
        return True
    except OSError:
        # Key doesn't exist or access denied — treat as already gone
        return False


def unregister_file_associations_windows(system: bool = False) -> None:
    """
    Unregister file associations for .pmeprj and .pmeraw files on Windows.
    With ``system=True`` removes the machine-wide (HKLM) registration.
    """
    if platform.system() != "Windows":
        return

    root = winreg.HKEY_LOCAL_MACHINE if system else winreg.HKEY_CURRENT_USER

    print("Unregistering file associations...")
    keys_to_remove = [
        (root, "Software\\Classes\\.pmeprj"),
        (root, "Software\\Classes\\.pmeraw"),
    ]

    # ProgID might have subkeys (shell, DefaultIcon), so we need recursive delete
    prog_id_key = "Software\\Classes\\MoleditPy.File"

    try:
        # Remove extension associations
        for root, key_path in keys_to_remove:
            try:
                winreg.DeleteKey(root, key_path)
                print(f"  Removed registry key: {key_path}")
            except FileNotFoundError:
                pass  # Already gone
            except OSError as e:
                print(f"  Failed to remove {key_path}: {e}")

        # Remove ProgID recursively
        if delete_registry_tree(root, prog_id_key):
            print(f"  Removed registry tree: {prog_id_key}")

        # Explorer pins its own per-user choice under FileExts; without
        # removing it (and notifying), the association looks still present.
        for ext in (".pmeprj",):
            file_exts_key = (
                "Software\\Microsoft\\Windows\\CurrentVersion\\"
                f"Explorer\\FileExts\\{ext}"
            )
            if delete_registry_tree(winreg.HKEY_CURRENT_USER, file_exts_key):
                print(f"  Removed Explorer cache: {file_exts_key}")

        _notify_windows_assoc_changed()
        print("File associations unregistered.")
    except OSError as e:
        print(f"Error during file association removal: {e}")


def remove_shortcut(system_scope: bool = False) -> None:
    """
    Removes the created shortcuts and file associations.

    With ``system_scope=True`` also removes system-wide artifacts
    (/usr/share on Linux, /Applications on macOS; requires root).
    """
    system = platform.system()
    shortcut_paths = []
    shortcut_name = "MoleditPy"

    if system_scope and not is_root():
        if system == "Windows":
            print(
                "Warning: removing a system-wide install requires an "
                "administrator terminal; system entries will likely remain."
            )
        else:
            print(
                "Warning: removing a system-wide install requires root; "
                "system files will likely remain. Re-run with sudo."
            )

    if system == "Windows":
        # Usually in APPDATA/Microsoft/Windows/Start Menu/Programs
        appdata = os.environ.get("APPDATA")
        if appdata:
            shortcut_paths.append(
                Path(appdata)
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
                / f"{shortcut_name}.lnk"
            )
        # pyshortcuts also creates a Desktop shortcut
        shortcut_paths.append(Path.home() / "Desktop" / f"{shortcut_name}.lnk")

        unregister_file_associations_windows()

        if system_scope:
            program_data = os.environ.get("PROGRAMDATA") or "C:/ProgramData"
            public = os.environ.get("PUBLIC") or "C:/Users/Public"
            shortcut_paths.append(
                Path(program_data)
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
                / f"{shortcut_name}.lnk"
            )
            shortcut_paths.append(Path(public) / "Desktop" / f"{shortcut_name}.lnk")
            unregister_file_associations_windows(system=True)

    elif system == "Linux":
        # Usually in ~/.local/share/applications/ plus a Desktop copy
        home = Path.home()
        shortcut_paths.append(
            linux_data_home() / "applications" / f"{shortcut_name}.desktop"
        )
        shortcut_paths.append(home / "Desktop" / f"{shortcut_name}.desktop")

        unregister_file_associations_linux()

        if system_scope:
            shortcut_paths.append(
                linux_data_home(system=True)
                / "applications"
                / f"{shortcut_name}.desktop"
            )
            unregister_file_associations_linux(system=True)

    elif system == "Darwin":
        home = Path.home()
        shortcut_paths.append(home / "Applications" / f"{shortcut_name}.app")
        shortcut_paths.append(home / "Desktop" / f"{shortcut_name}.app")
        if system_scope:
            shortcut_paths.append(Path("/Applications") / f"{shortcut_name}.app")

    else:
        print(f"Removal not fully supported/automated for OS: {system}")
        return

    removed_any = False
    for shortcut_path in shortcut_paths:
        if shortcut_path.exists():
            try:
                # Drop the bundle from the Launch Services database first,
                # or the deleted app keeps claiming .pmeprj files.
                if system == "Darwin":
                    refresh_launch_services(shortcut_path, unregister=True)
                if shortcut_path.is_dir():
                    shutil.rmtree(shortcut_path)
                else:
                    os.remove(shortcut_path)
                print(f"Removed shortcut: {shortcut_path}")
                removed_any = True
            except OSError as e:
                print(f"Failed to remove shortcut {shortcut_path}: {e}")

    if not removed_any:
        print("Shortcut not found at expected locations.")

    # Clean up the icons extracted at install time
    try:
        shutil.rmtree(get_persistent_data_dir(), ignore_errors=True)
        if system_scope:
            shutil.rmtree(get_persistent_data_dir(system=True), ignore_errors=True)
    except OSError:
        pass


def get_file_icon_path(system: bool = False) -> Optional[str]:
    """
    Gets the absolute path to the file icon (file_icon.ico) for Windows associations.
    """
    if platform.system() != "Windows":
        return None

    # Extract to a persistent location: as_file() paths may be temporary
    # (zip installs) and would be dead by the time the registry reads them.
    return _extract_data_file("file_icon.ico", system=system)


def python_for_executable(exe_path: str) -> str:
    """
    Return the Python interpreter that owns *exe_path*'s environment.

    A console script found on PATH may belong to a different environment
    than the one running this installer (e.g. base conda vs an activated
    env). Pairing such a script with sys.executable produces a launcher
    that dies with "ModuleNotFoundError: No module named 'moleditpy'".
    Prefer the interpreter sitting next to the script, then the script's
    shebang, and only then fall back to sys.executable.
    """
    exe_dir = Path(exe_path).resolve().parent
    for name in ("python3", "python"):
        candidate = exe_dir / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    try:
        with open(exe_path, "rb") as fp:
            first_line = fp.readline(512).decode("utf-8", "replace").strip()
        if first_line.startswith("#!"):
            shebang = first_line[2:].strip()
            # Try the full remainder first (handles spaces in the path),
            # then the first token (handles trailing flags like -sE).
            for cand_str in (shebang, shebang.split()[0] if shebang else ""):
                if not cand_str:
                    continue
                candidate = Path(cand_str)
                if (
                    candidate.name.startswith("python")
                    and candidate.name != "env"
                    and candidate.is_file()
                    and os.access(candidate, os.X_OK)
                ):
                    return str(candidate)
    except OSError:
        pass

    return sys.executable


def verify_launch_command(python_path: str, exe_path: str) -> bool:
    """
    Best-effort check that ``python exe --version`` actually runs.

    Catches environment mismatches at install time instead of leaving the
    user with a shortcut that fails silently on double-click.
    """
    try:
        result = subprocess.run(
            [python_path, exe_path, "--version"],
            capture_output=True,
            timeout=60,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def codesign_app(app_path: Path) -> None:
    """
    Ad-hoc re-sign a modified app bundle.

    osacompile produces a signed applet; editing its Info.plist or swapping
    applet.icns invalidates that signature. Apple Silicon Macs then refuse
    to launch the app — silently, when double-clicked in Finder — and
    Launch Services ignores its icon and document types.
    """
    try:
        result = subprocess.run(
            ["codesign", "--force", "--deep", "--sign", "-", str(app_path)],
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            print(f"Warning: codesign failed: {stderr}")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"Warning: could not re-sign app bundle: {e}")


def refresh_launch_services(app_path: Path, unregister: bool = False) -> None:
    """
    Tell macOS Launch Services about a new/updated (or removed) app bundle.

    Without this, Finder keeps showing the stale default applet icon and
    double-clicking .pmeprj files does not offer/launch the new app until
    the user logs out or the LS database is rebuilt. With ``unregister=True``
    the bundle is dropped from the LS database instead (used before removal,
    so a deleted app does not keep claiming .pmeprj).
    """
    if not unregister:
        try:
            os.utime(str(app_path), None)
        except OSError:
            pass

    lsregister_candidates = [
        Path(
            "/System/Library/Frameworks/CoreServices.framework/Frameworks/"
            "LaunchServices.framework/Support/lsregister"
        ),
        Path(
            "/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/"
            "LaunchServices.framework/Versions/A/Support/lsregister"
        ),
    ]
    for lsregister in lsregister_candidates:
        if lsregister.exists():
            try:
                subprocess.run(
                    [str(lsregister), "-u" if unregister else "-f", str(app_path)],
                    check=False,
                    capture_output=True,
                    timeout=60,
                )
            except (OSError, subprocess.SubprocessError) as e:
                print(f"Warning: Launch Services refresh failed: {e}")
            return


def _move_windows_shortcuts_to_all_users(desktop: bool, app_menu: bool) -> None:
    """
    Relocate freshly created per-user shortcuts to the all-users locations
    (ProgramData Start Menu / Public Desktop). pyshortcuts only writes
    per-user paths, so a system-wide install moves them afterwards.
    """
    name = "MoleditPy"
    moves = []
    appdata = os.environ.get("APPDATA")
    program_data = os.environ.get("PROGRAMDATA") or "C:/ProgramData"
    public = os.environ.get("PUBLIC") or "C:/Users/Public"

    if app_menu and appdata:
        moves.append(
            (
                Path(appdata)
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
                / f"{name}.lnk",
                Path(program_data)
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
                / f"{name}.lnk",
            )
        )
    if desktop:
        moves.append(
            (
                Path.home() / "Desktop" / f"{name}.lnk",
                Path(public) / "Desktop" / f"{name}.lnk",
            )
        )

    for src, dest in moves:
        if not src.is_file():
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest.unlink()
            shutil.move(str(src), str(dest))
            print(f"Moved shortcut to all-users location: {dest}")
        except OSError as e:
            print(f"Warning: could not move {src} to {dest}: {e}")


def install(options: Optional[InstallOptions] = None) -> int:
    """
    Creates shortcuts and file associations for the installed moleditpy
    executable according to *options* (see InstallOptions for defaults).
    Handles Conda environments by using 'conda run'.

    On macOS the launcher always opens MoleditPy inside a Terminal window,
    so Python output and errors stay visible.

    Returns:
        int: 0 on success, 1 on failure.
    """
    if options is None:
        options = InstallOptions()

    system = platform.system()

    if not (options.desktop or options.app_menu or options.file_assoc):
        print("Nothing to install: all components are disabled.")
        return 1

    if options.system and not is_root():
        if system == "Windows":
            print("Error: system-wide installation requires an elevated terminal.")
            print("Re-run from an administrator terminal, or drop --system.")
        else:
            print("Error: system-wide installation requires root privileges.")
            print("Re-run with sudo, or drop --system for a per-user install.")
        return 1

    command_name = "moleditpy"

    # 1. Get Icon
    icon_path = get_icon_path()

    if not icon_path:
        print(
            "Warning: Could not find a suitable icon file. A default icon will be used."
        )

    # 2. Check for Conda Environment
    # CONDA_DEFAULT_ENV: Current environment name (e.g., myenv)
    # CONDA_EXE: Path to conda command
    conda_env = os.environ.get("CONDA_DEFAULT_ENV")
    conda_exe = os.environ.get("CONDA_EXE")

    print(f"Searching for the executable '{command_name}'...")
    original_exe_path = find_executable(command_name)

    # On Linux the package may install as 'moleditpy-linux' instead of 'moleditpy'
    if not original_exe_path and platform.system() == "Linux":
        alt_name = "moleditpy-linux"
        print(f"Not found. Trying alternate name '{alt_name}'...")
        original_exe_path = find_executable(alt_name)
        if original_exe_path:
            command_name = alt_name

    if not original_exe_path:
        print(f"Error: Command '{command_name}' (or 'moleditpy-linux') not found.")
        print("Please ensure the package is installed correctly and that")
        print("its Scripts/bin directory is accessible.")
        return 1

    # If Conda environment
    if conda_env and conda_exe:
        print(f"Conda environment detected: {conda_env}")

        # Target conda.exe instead of app
        target_script = conda_exe

        # Command assembly: conda run -p "C:\envs\myenv" "C:\Path\To\moleditpy.exe"
        # Prefer the env prefix (-p): CONDA_DEFAULT_ENV may be a path for
        # envs activated by path, in which case -n would not resolve.
        # --no-capture-output keeps conda from buffering the GUI app's stdio.
        conda_prefix = os.environ.get("CONDA_PREFIX")
        if conda_prefix:
            env_selector = f'-p "{conda_prefix}"'
        else:
            env_selector = f'-n "{conda_env}"'
        target_args = f'run {env_selector} --no-capture-output "{original_exe_path}"'

    else:
        # Normal environment (pip install, etc.)
        target_script = original_exe_path
        target_args = ""  # No arguments

    try:
        shortcut_name = "MoleditPy"

        print(f"Creating '{shortcut_name}' shortcut...")
        print(f"Targeting: {target_script} {target_args}")

        # Prepare script with arguments
        if target_args:
            # Quote target_script to handle spaces if we have arguments
            full_command = f'"{target_script}" {target_args}'
        else:
            # Pass raw path if no arguments, so pyshortcuts can verify file existence
            full_command = target_script

        if system in ("Windows", "Linux"):
            if options.desktop or options.app_menu:
                if system == "Linux" and options.system:
                    # pyshortcuts only writes per-user locations
                    write_linux_system_desktop_entry(full_command, icon_path)
                    if options.desktop:
                        print(
                            "Note: Desktop shortcuts are per-user; "
                            "skipped for a system-wide install."
                        )
                else:
                    with _com_initialized():
                        make_shortcut(
                            script=full_command,
                            name=shortcut_name,
                            icon=icon_path,
                            desktop=options.desktop,
                            startmenu=options.app_menu,
                            noexe=True,
                        )
                    if system == "Windows" and options.system:
                        _move_windows_shortcuts_to_all_users(
                            options.desktop, options.app_menu
                        )
                    created_in = [
                        loc
                        for enabled, loc in (
                            (options.app_menu, "the application menu"),
                            (options.desktop, "the Desktop"),
                        )
                        if enabled
                    ]
                    print(
                        f"Successfully created '{shortcut_name}' in "
                        f"{' and '.join(created_in)}."
                    )

            if system == "Linux" and options.file_assoc:
                register_file_associations_linux(system=options.system)

        elif system == "Darwin":
            if not (options.desktop or options.app_menu):
                print(
                    "Error: on macOS the file association lives inside the app "
                    "bundle — enable the application menu or the Desktop shortcut."
                )
                return 1

            print("macOS detected. Creating application shortcut natively...")
            target_app_name = f"{shortcut_name}.app"

            # Pair the found console script with the interpreter of its OWN
            # environment. sys.executable (the installer's Python) may belong
            # to a different env — that mismatch is what causes
            # "ModuleNotFoundError: No module named 'moleditpy'" at launch.
            mac_target_script = python_for_executable(original_exe_path)

            if not verify_launch_command(mac_target_script, original_exe_path):
                if mac_target_script != sys.executable and verify_launch_command(
                    sys.executable, original_exe_path
                ):
                    mac_target_script = sys.executable
                else:
                    print(
                        f'Warning: could not verify that "{mac_target_script}" '
                        f'can launch "{original_exe_path}".'
                    )
                    print(
                        "The shortcut may fail to open. If it does, re-run "
                        "'moleditpy-installer' from the Python environment where "
                        "moleditpy is installed (e.g. after 'conda activate <env>')."
                    )

            mac_escaped_script = mac_target_script.replace('"', '\\"')
            applescript_escaped_args = f'"{original_exe_path}"'.replace('"', '\\"')

            # Run MoleditPy inside a Terminal window so Python output and
            # errors are always visible to the user (a silent GUI launch
            # hides failures like a broken environment completely).
            # "do script" returns immediately, so the applet quits right
            # away instead of staying "running" in the Dock.
            applescript_code = f"""
on launch_moleditpy(extra_args)
    set base_cmd to quoted form of "{mac_escaped_script}" & " {applescript_escaped_args}"
    tell application "Terminal"
        activate
        do script base_cmd & extra_args
    end tell
end launch_moleditpy

on run
    my launch_moleditpy("")
end run

on open dropped_items
    set arg_string to ""
    repeat with dropped_item in dropped_items
        set arg_string to arg_string & " " & quoted form of POSIX path of dropped_item
    end repeat
    my launch_moleditpy(arg_string)
end open
"""
            # Build the bundle in a scratch dir (never into an existing .app:
            # osacompile -o keeps leftover files), then copy to the selected
            # destinations.
            build_root = Path(tempfile.mkdtemp(prefix="moleditpy-installer-"))
            target_app_path = build_root / target_app_name

            try:
                # capture_output: osacompile chatter must not scribble over
                # the TUI, and its stderr belongs in the error message.
                compile_result = subprocess.run(
                    ["osacompile", "-o", str(target_app_path), "-e", applescript_code],
                    capture_output=True,
                    timeout=300,
                )
                if compile_result.returncode != 0:
                    stderr = compile_result.stderr.decode(errors="replace").strip()
                    raise RuntimeError(f"osacompile failed: {stderr}")

                # Modern osacompile applets ship a compiled asset catalog
                # (Assets.car) + CFBundleIconName; macOS prefers that over
                # CFBundleIconFile, so a replaced applet.icns is IGNORED
                # unless both are removed.
                assets_car = target_app_path / "Contents" / "Resources" / "Assets.car"
                if assets_car.exists():
                    assets_car.unlink()

                # Give the bundle a stable identity: Launch Services needs a
                # bundle identifier to bind document types (and the icon)
                # reliably; osacompile applets ship without one.
                plist_path = target_app_path / "Contents" / "Info.plist"
                if plist_path.exists():
                    with open(plist_path, "rb") as fp:
                        pl = plistlib.load(fp)
                    pl.pop("CFBundleIconName", None)  # would win over IconFile
                    pl["CFBundleIdentifier"] = "com.moleditpy.launcher"
                    pl["CFBundleName"] = shortcut_name
                    pl["CFBundleDisplayName"] = shortcut_name
                    # Bump per install so Launch Services/Finder drop their
                    # cached (old) icon for the bundle identifier.
                    installer_version = get_installer_version()
                    pl["CFBundleShortVersionString"] = installer_version
                    pl["CFBundleVersion"] = installer_version
                    # Shown in the one-time macOS consent prompt when the
                    # launcher first opens Terminal via Apple events.
                    pl["NSAppleEventsUsageDescription"] = (
                        "MoleditPy launcher opens Terminal to run MoleditPy "
                        "so that output and errors are visible."
                    )
                    if icon_path and os.path.exists(icon_path):
                        pl["CFBundleIconFile"] = "applet.icns"
                    with open(plist_path, "wb") as fp:
                        plistlib.dump(pl, fp)

                if icon_path and os.path.exists(icon_path):
                    app_resources = target_app_path / "Contents" / "Resources"
                    app_resources.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(icon_path, app_resources / "applet.icns")

                if options.file_assoc:
                    register_file_associations_darwin(target_app_path)

                # Re-sign AFTER all bundle modifications, or Apple Silicon
                # refuses to launch the app (silently from Finder).
                codesign_app(target_app_path)

                destinations = []
                if options.app_menu:
                    apps_dir = (
                        Path("/Applications")
                        if options.system
                        else Path.home() / "Applications"
                    )
                    destinations.append(apps_dir / target_app_name)
                if options.desktop:
                    destinations.append(Path.home() / "Desktop" / target_app_name)

                for dest_app in destinations:
                    dest_app.parent.mkdir(parents=True, exist_ok=True)
                    if dest_app.exists():
                        if dest_app.is_dir():
                            shutil.rmtree(dest_app)
                        else:
                            os.remove(dest_app)

                    shutil.copytree(str(target_app_path), str(dest_app), symlinks=True)
                    codesign_app(dest_app)

                    # Refresh Launch Services so the custom icon and the
                    # .pmeprj association take effect immediately.
                    refresh_launch_services(dest_app)
                    print(f"Created shortcut: {dest_app}")

                if options.file_assoc:
                    print("Double-clicking .pmeprj files will now open MoleditPy.")
            except (
                OSError,
                subprocess.SubprocessError,
                RuntimeError,
                ValueError,
            ) as e:
                print(f"Failed to create macOS app bundle natively: {e}")
                return 1
            finally:
                shutil.rmtree(build_root, ignore_errors=True)
        else:
            print(f"Shortcut creation is not supported on this OS: {system}")
            return 1

    except OSError as e:
        print(f"Failed to create shortcut: {e}")
        return 1

    # Register file associations on Windows (.pmeprj only — .pmeraw is a
    # pickle-based format and is intentionally NOT associated with
    # double-click for safety).
    if system == "Windows" and original_exe_path and options.file_assoc:
        file_icon_path = get_file_icon_path(system=options.system)
        if not file_icon_path:
            file_icon_path = icon_path

        register_file_associations_windows(
            str(original_exe_path), file_icon_path, system=options.system
        )

    print("\nYou can remove the shortcut and file associations by running:")
    print("  moleditpy-installer --remove")
    return 0


def get_installer_version() -> str:
    """Gets the version of the installer package."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("moleditpy-installer")
    except (ImportError, PackageNotFoundError):
        pass

    try:
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("version"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            return parts[1].strip().strip('"').strip("'")
    except OSError:
        pass

    return "unknown"


def _tui_available() -> bool:
    """True when an interactive Textual UI can run in this session."""
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
    except (AttributeError, ValueError):
        return False
    try:
        import textual  # noqa: F401
    except ImportError:
        return False
    return True


def main() -> int:
    """Parse CLI arguments and run the TUI, install, or remove."""
    parser = argparse.ArgumentParser(
        prog="moleditpy-installer",
        description=(
            "Installer for MoleditPy shortcuts and file associations "
            f"(v{get_installer_version()}). Run without arguments in a "
            "terminal for the interactive TUI."
        ),
    )
    parser.add_argument(
        "--uninstall",
        "--remove",
        dest="uninstall",
        action="store_true",
        help=(
            "Uninstall: remove the shortcuts and unregister file "
            "associations (--remove is a deprecated alias)."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Search for the moleditpy executable in search paths, print the result, and exit.",
    )
    parser.add_argument(
        "--desktop",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Create a Desktop shortcut (default: no).",
    )
    parser.add_argument(
        "--app-menu",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Create an application-menu entry (default: yes).",
    )
    parser.add_argument(
        "--file-assoc",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Associate .pmeprj files with MoleditPy (default: yes).",
    )
    parser.add_argument(
        "--system",
        action="store_true",
        help="Install system-wide instead of per-user (requires sudo/admin).",
    )
    parser.add_argument(
        "--no-tui",
        action="store_true",
        help="Skip the interactive TUI and install directly with the given options.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {get_installer_version()}",
        help="Show the version of the installer and exit.",
    )

    args = parser.parse_args()

    if args.uninstall:
        remove_shortcut(system_scope=args.system)
        return 0

    if args.check:
        command_name = "moleditpy"
        path = find_executable(command_name)
        if not path and platform.system() == "Linux":
            command_name = "moleditpy-linux"
            path = find_executable(command_name)
        if path:
            print(f"Success: Found executable '{command_name}' at: {path}")

            # On macOS the shortcut pairs the script with its environment's
            # interpreter — verify that pairing actually launches.
            if platform.system() == "Darwin":
                interpreter = python_for_executable(path)
                print(f"Launcher interpreter: {interpreter}")
                if verify_launch_command(interpreter, path):
                    print("Launch check: OK")
                else:
                    print(
                        "Launch check: FAILED — this pairing cannot start "
                        "MoleditPy. Re-run from the Python environment where "
                        "moleditpy is installed."
                    )
                    return 1
            return 0

        print(
            f"Error: Executable '{command_name}' (or 'moleditpy-linux') "
            "was not found in any search paths."
        )
        return 1

    explicit_flags = (
        args.desktop is not None
        or args.app_menu is not None
        or args.file_assoc is not None
        or args.system
    )

    options = InstallOptions(
        desktop=bool(args.desktop) if args.desktop is not None else False,
        app_menu=bool(args.app_menu) if args.app_menu is not None else True,
        file_assoc=bool(args.file_assoc) if args.file_assoc is not None else True,
        system=args.system,
    )

    # Interactive TUI when in a real terminal and nothing was decided on
    # the command line; otherwise install directly with the options.
    if not args.no_tui and not explicit_flags and _tui_available():
        from .tui import run_tui

        return run_tui()

    return install(options)


if __name__ == "__main__":
    sys.exit(main())
