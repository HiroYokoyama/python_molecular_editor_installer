"""
MoleditPy Installer Script
==========================

This script creates a shortcut for the moleditpy application and registers file 
associations on Windows. It is designed to be run after installing the 
'moleditpy-installer' package.
"""

import shutil
import platform
import importlib.resources
import os
import sys
try:
    import winreg
except ImportError:
    winreg = None
from pathlib import Path
from typing import Optional
from pyshortcuts import make_shortcut
import argparse

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
    elif system == "Darwin": # macOS
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
            else:
                 print(f"Error: Icon file not found in package resources: {path}")
                 return None

    except Exception as e:
        print(f"Error finding icon file {icon_name}: {e}")
        return None

def find_executable(name: str) -> Optional[str]:
    """
    Finds the path to the specified executable.
    
    Prioritizes looking in the same directory as the currently running script/executable,
    then falls back to the system PATH.

    Args:
        name (str): The name of the executable (e.g., 'moleditpy').

    Returns:
        Optional[str]: The absolute path to the executable, or None if not found.
    """
    # 1. Check in the same directory as the current script/interpreter
    # sys.argv[0] is usually the script path. sys.executable is the python interpreter.
    # When installed via pip, the wrapper script (moleditpy-installer) is usually in the same
    # bin/Scripts folder as moleditpy.
    
    current_script_dir = Path(sys.argv[0]).resolve().parent
    candidate_path = current_script_dir / name
    
    # Handle Windows .exe extension if not present
    if platform.system() == "Windows":
        if not candidate_path.suffix:
            candidate_path = candidate_path.with_suffix(".exe")
            
    if candidate_path.is_file() and os.access(candidate_path, os.X_OK):
        # Normalize to lowercase .exe for consistency/aesthetics
        if platform.system() == "Windows" and candidate_path.suffix == ".EXE":
             candidate_path = candidate_path.with_suffix(".exe")
             
        print(f"Found executable in local directory: {candidate_path}")
        return str(candidate_path)

    # 2. Fallback to system PATH
    path_from_shutil = shutil.which(name)
    if path_from_shutil:
        # Normalize to lowercase .exe if needed
        if platform.system() == "Windows" and path_from_shutil.endswith(".EXE"):
             path_from_shutil = path_from_shutil[:-4] + ".exe"
             
        print(f"Found executable in system PATH: {path_from_shutil}")
        return path_from_shutil

    return None

def register_file_associations_windows(exe_path: str, icon_path: Optional[str]) -> bool:
    """
    Register file associations for .pmeprj and .pmeraw files on Windows.

    Args:
        exe_path (str): Path to the executable to associate.
        icon_path (Optional[str]): Path to the icon file for the association.

    Returns:
        bool: True if successful, False otherwise.
    """
    if platform.system() != "Windows":
        return False

    try:
        extensions = [".pmeprj", ".pmeraw"]
        prog_id = "MoleditPy.File"
        app_name = "MoleditPy"
        
        print("Registering file associations...")
        
        # Create ProgID
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, f"{app_name} File")
            
        # Set default icon
        if icon_path and os.path.exists(icon_path):
             with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\DefaultIcon") as key:
                winreg.SetValue(key, "", winreg.REG_SZ, icon_path)
        
        # Set open command
        # Quote paths to handle spaces
        command = f'"{exe_path}" "%1"'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\shell\\open\\command") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, command)
        
        # Associate extensions
        for ext in extensions:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{ext}") as key:
                winreg.SetValue(key, "", winreg.REG_SZ, prog_id)
            print(f"  Associated {ext} with {app_name}")
        
        print("File associations registered successfully.")
        return True
        
    except Exception as e:
        print(f"Failed to register file associations: {e}")
        return False



def delete_registry_tree(key, sub_key):
    """
    Deletes a registry key and all its subkeys.
    """
    try:
        current_key = winreg.OpenKey(key, sub_key, 0, winreg.KEY_ALL_ACCESS)
        info = winreg.QueryInfoKey(current_key)
        for i in range(0, info[0]):
            # Delete all subkeys first
            # Since we are deleting, the index 0 will always point to 'next' remaining key
            # But keys are re-indexed, so we might need to query again or delete recursively
            # A simpler approach for recursion:
            subkey_name = winreg.EnumKey(current_key, 0)
            delete_registry_tree(current_key, subkey_name)
            
        winreg.CloseKey(current_key)
        winreg.DeleteKey(key, sub_key)
        return True
    except Exception:
        # If key doesn't exist or error, return False (or ignore if it's just missing)
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
                pass # Already gone
            except Exception as e:
                print(f"  Failed to remove {key_path}: {e}")

        # Remove ProgID recursively
        if delete_registry_tree(winreg.HKEY_CURRENT_USER, prog_id_key):
             print(f"  Removed registry tree: {prog_id_key}")
        else:
             # It might not exist, check if it was just a simple delete failure or missing
             pass

        print("File associations unregistered.")
    except Exception as e:
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
            shortcut_path = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{shortcut_name}.lnk"
        
        unregister_file_associations_windows()

    elif system == "Linux":
        # Usually in ~/.local/share/applications/
        home = Path.home()
        shortcut_path = home / ".local" / "share" / "applications" / f"{shortcut_name}.desktop"

    elif system == "Darwin":
        # In /Applications or ~/Desktop depending on how it was created.
        # The installer used desktop=True which usually puts it on Desktop
        # But log said /Applications. Let's check Desktop first as per user plan assumption.
        home = Path.home()
        shortcut_path = home / "Desktop" / f"{shortcut_name}.app"
        
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
        except Exception as e:
            print(f"Failed to remove shortcut {shortcut_path}: {e}")
    else:
        print(f"Shortcut not found at expected location: {shortcut_path}")


def install() -> None:
    """
    Creates a shortcut for the installed moleditpy executable.
    Handles Conda environments by using 'conda run'.
    """
    command_name = "moleditpy" 
    
    # 1. アイコンの取得 (Get Icon)
    icon_path = get_icon_path()
    
    if not icon_path:
        print("Warning: Could not find a suitable icon file. A default icon will be used.")

    # 2. Conda環境かどうかの判定 (Check for Conda Environment)
    # CONDA_DEFAULT_ENV: Current environment name (e.g., myenv)
    # CONDA_EXE: Path to conda command
    conda_env = os.environ.get('CONDA_DEFAULT_ENV')
    conda_exe = os.environ.get('CONDA_EXE')

    print(f"Searching for the executable '{command_name}'...")
    original_exe_path = find_executable(command_name)
    
    if not original_exe_path:
        print(f"Error: Command '{command_name}' not found.")
        print("Please ensure 'moleditpy' (or 'moleditpy-linux') is installed correctly")
        print("and that its location is available.")
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
        target_args = "" # No arguments

    try:
        shortcut_name = "MoleditPy"
        system = platform.system()

        print(f"Creating '{shortcut_name}' shortcut...")
        print(f"Targeting: {target_script} {target_args}")

        # Prepare script with arguments
        if target_args:
             # Quote target_script to handle spaces if we have arguments
            full_command = f'"{target_script}" {target_args}'
        else:
             # Pass raw path if no arguments, so pyshortcuts can verify file existence
            full_command = target_script

        if system == "Windows" or system == "Linux":
            make_shortcut(
                script=full_command,
                name=shortcut_name,
                icon=icon_path,      
                desktop=False,
                startmenu=True,
                noexe=True
            )
            print(f"Successfully created '{shortcut_name}' in the application menu.")
        
        elif system == "Darwin":
            print("macOS detected. Creating application in /Applications folder...")
            make_shortcut(
                script=full_command,
                name=shortcut_name,
                icon=icon_path,
                desktop=True,
                terminal=True, # Keep terminal for stdout/stderr if needed
                noexe=True
            )
            print(f"Successfully created '{shortcut_name}' in /Applications.")
        else:
             print(f"Shortcut creation is not supported on this OS: {system}")
             return

    except Exception as e:
        print(f"Failed to create shortcut: {e}")
    
    # Register file associations on Windows
    if system == "Windows" and original_exe_path:
        register_file_associations_windows(str(original_exe_path), icon_path)

        print("\nYou can remove the shortcut and file associations by running:")
        print("  moleditpy-installer --remove")

def main():
    parser = argparse.ArgumentParser(description="Installer for MoleditPy shortcut and file associations.")
    parser.add_argument("--remove", action="store_true", help="Remove the shortcut and unregister file associations.")
    
    args = parser.parse_args()
    
    if args.remove:
        remove_shortcut()
    else:
        install()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())