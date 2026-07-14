"""
MoleditPy Installer Script
==========================

This script creates a shortcut for the moleditpy application and registers file
associations on Windows. It is designed to be run after installing the
'moleditpy-installer' package.
"""

import argparse
import importlib.resources
import os
import platform
import shutil
import sys
import sysconfig
from pathlib import Path
from typing import Optional

try:
    import winreg
except ImportError:
    winreg = None

from pyshortcuts import make_shortcut


def get_icon_path() -> Optional[str]:
    """
    Gets the absolute path to the correct icon file based on the OS.

    Returns:
        Optional[str]: The path to the icon file, or None if not found or OS unsupported.
    """
    system = platform.system()
    icon_name = ""

    if system == "Windows":
        icon_name = "icon.ico"
    elif system == "Darwin":  # macOS
        icon_name = "icon.icns"
    elif system == "Linux":
        icon_name = "icon.png"
    else:
        print(f"Warning: Unsupported operating system for icon selection: {system}")
        return None

    try:
        # Check resources
        # Use files() for Python 3.9+ compatibility (and modern standard)
        ref = importlib.resources.files("moleditpy_installer") / "data" / icon_name
        with importlib.resources.as_file(ref) as path:
            # Ensure the file actually exists
            if path.exists():
                return str(path)
            print(f"Error: Icon file not found in package resources: {path}")
            return None

    except OSError as e:
        print(f"Error finding icon file {icon_name}: {e}")
        return None


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
        except Exception:
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
                except Exception:
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


def register_file_associations_windows(exe_path: str, icon_path: Optional[str]) -> bool:
    """
    Register file associations for .pmeprj files on Windows.

    Args:
        exe_path (str): Path to the executable to associate.
        icon_path (Optional[str]): Path to the icon file for the association.

    Returns:
        bool: True if successful, False otherwise.
    """
    if platform.system() != "Windows":
        return False

    try:
        extensions = [".pmeprj"]
        prog_id = "MoleditPy.File"
        app_name = "MoleditPy"

        print("Registering file associations...")

        # Create ProgID
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}"
        ) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, f"{app_name} File")

        # Set default icon
        if icon_path and os.path.exists(icon_path):
            with winreg.CreateKey(
                winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\DefaultIcon"
            ) as key:
                winreg.SetValue(key, "", winreg.REG_SZ, icon_path)

        # Set open command
        # Quote paths to handle spaces
        command = f'"{exe_path}" "%1"'
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            f"Software\\Classes\\{prog_id}\\shell\\open\\command",
        ) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, command)

        # Associate extensions
        for ext in extensions:
            with winreg.CreateKey(
                winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{ext}"
            ) as key:
                winreg.SetValue(key, "", winreg.REG_SZ, prog_id)
            print(f"  Associated {ext} with {app_name}")

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

    import plistlib

    try:
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
            }
            doc_types.append(new_doc_type)
            pl["CFBundleDocumentTypes"] = doc_types

            with open(plist_path, "wb") as fp:
                plistlib.dump(pl, fp)

            # Touch the app bundle to notify Launch Services of changes
            try:
                os.utime(str(app_path), None)
            except Exception:
                pass

            print("Successfully registered file associations in Info.plist.")
            return True

        return True

    except Exception as e:
        print(f"Warning: Failed to update Info.plist: {e}")
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


def unregister_file_associations_windows() -> None:
    """
    Unregister file associations for .pmeprj and .pmeraw files on Windows.
    """
    if platform.system() != "Windows":
        return

    print("Unregistering file associations...")
    keys_to_remove = [
        (winreg.HKEY_CURRENT_USER, "Software\\Classes\\.pmeprj"),
        (winreg.HKEY_CURRENT_USER, "Software\\Classes\\.pmeraw"),
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
        if delete_registry_tree(winreg.HKEY_CURRENT_USER, prog_id_key):
            print(f"  Removed registry tree: {prog_id_key}")

        print("File associations unregistered.")
    except OSError as e:
        print(f"Error during file association removal: {e}")


def remove_shortcut() -> None:
    """
    Removes the created shortcut and file associations (on Windows).
    """
    system = platform.system()
    shortcut_path = None
    shortcut_name = "MoleditPy"

    if system == "Windows":
        # Usually in APPDATA/Microsoft/Windows/Start Menu/Programs
        appdata = os.environ.get("APPDATA")
        if appdata:
            shortcut_path = (
                Path(appdata)
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
                / f"{shortcut_name}.lnk"
            )

        unregister_file_associations_windows()

    elif system == "Linux":
        # Usually in ~/.local/share/applications/
        home = Path.home()
        shortcut_path = (
            home / ".local" / "share" / "applications" / f"{shortcut_name}.desktop"
        )

    elif system == "Darwin":
        home = Path.home()
        paths_to_remove = [
            home / "Applications" / f"{shortcut_name}.app",
            home / "Desktop" / f"{shortcut_name}.app",
        ]
        removed_any = False
        for path in paths_to_remove:
            if path.exists():
                try:
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    print(f"Removed shortcut: {path}")
                    removed_any = True
                except OSError as e:
                    print(f"Failed to remove shortcut {path}: {e}")

        if not removed_any:
            print("Shortcut not found at expected locations on macOS.")
        return

    else:
        print(f"Removal not fully supported/automated for OS: {system}")
        return

    if shortcut_path and shortcut_path.exists():
        try:
            if shortcut_path.is_dir():
                shutil.rmtree(shortcut_path)
            else:
                os.remove(shortcut_path)
            print(f"Removed shortcut: {shortcut_path}")
        except OSError as e:
            print(f"Failed to remove shortcut {shortcut_path}: {e}")
    else:
        print(f"Shortcut not found at expected location: {shortcut_path}")


def get_file_icon_path() -> Optional[str]:
    """
    Gets the absolute path to the file icon (file_icon.ico) for Windows associations.
    """
    if platform.system() != "Windows":
        return None

    try:
        ref = (
            importlib.resources.files("moleditpy_installer") / "data" / "file_icon.ico"
        )
        with importlib.resources.as_file(ref) as path:
            if path.exists():
                return str(path)
    except OSError as e:
        print(f"Error finding file icon: {e}")

    return None


def install() -> None:
    """
    Creates a shortcut for the installed moleditpy executable.
    Handles Conda environments by using 'conda run'.
    """
    command_name = "moleditpy"

    # 1. アイコンの取得 (Get Icon)
    icon_path = get_icon_path()

    if not icon_path:
        print(
            "Warning: Could not find a suitable icon file. A default icon will be used."
        )

    # 2. Conda環境かどうかの判定 (Check for Conda Environment)
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
        return

    # ショートカット作成用の変数を初期化 (Initialize shortcut variables)
    target_script = ""
    target_args = ""

    # Conda環境、かつ base 環境以外の場合 (If Conda environment and not base)
    if conda_env and conda_exe and conda_env != "base":
        print(f"Conda environment detected: {conda_env}")

        # ターゲットをアプリ本体ではなく 'conda.exe' にする (Target conda.exe instead of app)
        target_script = conda_exe

        # コマンド組立: conda run -n myenv "C:\Path\To\moleditpy.exe"
        target_args = f'run -n {conda_env} "{original_exe_path}"'

    else:
        # 通常の環境 (pip installなど) (Normal environment)
        target_script = original_exe_path
        target_args = ""  # No arguments

    system = platform.system()

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
            make_shortcut(
                script=full_command,
                name=shortcut_name,
                icon=icon_path,
                desktop=True,
                startmenu=True,
                noexe=True,
            )
            print(
                f"Successfully created '{shortcut_name}' in the application menu and on the Desktop."
            )

        elif system == "Darwin":
            print("macOS detected. Creating application shortcut...")
            scut = make_shortcut(
                script=full_command,
                name=shortcut_name,
                icon=icon_path,
                desktop=True,
                terminal=True,  # Keep terminal for stdout/stderr if needed
                noexe=True,
            )

            if scut is not None:
                desktop_dir = getattr(scut, "desktop_dir", None)
                target = getattr(scut, "target", None)
                if isinstance(desktop_dir, (str, Path)) and isinstance(
                    target, (str, Path)
                ):
                    src_app = Path(desktop_dir) / target
                    dest_dir = Path.home() / "Applications"

                    if src_app.exists():
                        register_file_associations_darwin(src_app)
                        try:
                            dest_dir.mkdir(parents=True, exist_ok=True)
                            dest_app = dest_dir / target
                            if dest_app.exists():
                                if dest_app.is_dir():
                                    shutil.rmtree(dest_app)
                                else:
                                    os.remove(dest_app)

                            shutil.copytree(str(src_app), str(dest_app))

                            print("Created shortcut on ~/Applications and Desktop.")
                            print(
                                "If you want to add to /Applications folder, please move the desktop one."
                            )
                        except Exception as e:
                            print(
                                f"Warning: Failed to copy application bundle to {dest_dir}: {e}"
                            )
                            print("Created shortcut on Desktop.")
                            print(
                                "If you want to add to /Applications folder, please move the desktop one."
                            )
                    else:
                        print("Created shortcut on Desktop.")
                        print(
                            "If you want to add to /Applications folder, please move the desktop one."
                        )
                else:
                    print("Created shortcut on Desktop.")
                    print(
                        "If you want to add to /Applications folder, please move the desktop one."
                    )
            else:
                print("Created shortcut on Desktop.")
                print(
                    "If you want to add to /Applications folder, please move the desktop one."
                )
        else:
            print(f"Shortcut creation is not supported on this OS: {system}")
            return

    except OSError as e:
        print(f"Failed to create shortcut: {e}")

    # Register file associations on Windows
    if system == "Windows" and original_exe_path:
        file_icon_path = get_file_icon_path()
        if not file_icon_path:
            file_icon_path = icon_path

        register_file_associations_windows(str(original_exe_path), file_icon_path)

        print("\nYou can remove the shortcut and file associations by running:")
        print("  moleditpy-installer --remove")


def get_installer_version() -> str:
    """Gets the version of the installer package."""
    try:
        from importlib.metadata import version

        return version("moleditpy-installer")
    except Exception:
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
    except Exception:
        pass

    return "1.5.0"  # Fallback


def main() -> int:
    """Parse CLI arguments and run install or remove."""
    parser = argparse.ArgumentParser(
        prog="moleditpy-installer",
        description=(
            "Installer for MoleditPy shortcut and file associations "
            f"(v{get_installer_version()})."
        ),
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove the shortcut and unregister file associations.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Search for the moleditpy executable in search paths, print the result, and exit.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {get_installer_version()}",
        help="Show the version of the installer and exit.",
    )

    args = parser.parse_args()

    if args.remove:
        remove_shortcut()
        return 0

    if args.check:
        command_name = "moleditpy"
        path = find_executable(command_name)
        if not path and platform.system() == "Linux":
            command_name = "moleditpy-linux"
            path = find_executable(command_name)
        if path:
            print(f"Success: Found executable '{command_name}' at: {path}")
            return 0

        print(
            f"Error: Executable '{command_name}' (or 'moleditpy-linux') "
            "was not found in any search paths."
        )
        return 1

    install()
    return 0


if __name__ == "__main__":
    sys.exit(main())
