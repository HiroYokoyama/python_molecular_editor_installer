import shutil
import platform
import importlib.resources # Python 3.9+
import os
from pyshortcuts import make_shortcut

if platform.system() == "Windows":
    import winreg

def get_icon_path():
    """Gets the path to the correct icon file based on the OS."""
    system = platform.system()
    icon_name = ""
    
    if system == "Windows":
        icon_name = "icon.ico"
    elif system == "Darwin": # macOS
        icon_name = "icon.icns"
    elif system == "Linux":
        icon_name = "icon.png"
    else:
        return None # Unsupported OS

    try:
        # --- START OF FIX ---
        # In Python 3.12+, .files() returns a Path object directly.
        # The 'with' statement is not needed and causes an error.
        path = importlib.resources.files("moleditpy_installer").joinpath("data", icon_name)
        
        if not path.exists():
            print(f"Error: Icon file not found at expected location: {path}")
            return None
            
        return str(path)
        # --- END OF FIX ---
        
    except Exception as e:
        print(f"Error finding icon file {icon_name}: {e}")
        return None

def register_file_associations_windows(exe_path, icon_path):
    """Register file associations for .pmeprj and .pmeraw files on Windows."""
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
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\shell\\open\\command") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, f'"{exe_path}" "%1"')
        
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

def create_shortcut():
    """
    Creates a shortcut for the installed moleditpy executable.
    """
    command_name = "moleditpy" 
    
    print(f"Searching for the executable '{command_name}'...")
    exe_path = shutil.which(command_name)
    
    if not exe_path:
        print(f"Error: Command '{command_name}' not found.")
        print("Please ensure 'moleditpy' or 'moleditpy-linux' is installed correctly")
        print("and that its location is included in your system's PATH.")
        return

    print(f"Executable found: {exe_path}")
    
    icon_path = get_icon_path()
    
    if not icon_path:
        print("Warning: Could not find a suitable icon file. A default icon will be used.")

    try:
        shortcut_name = "MoleditPy"
        system = platform.system()

        print(f"Creating '{shortcut_name}' in the application menu...")

        if system == "Windows" or system == "Linux":
            make_shortcut(
                script=exe_path,
                name=shortcut_name,
                icon=icon_path,      
                desktop=False,
                startmenu=True
            )
            print(f"Successfully created '{shortcut_name}' in the application menu.")
        
        elif system == "Darwin":
            print("macOS detected. Creating link in /Applications folder...")
            make_shortcut(
                script=exe_path,
                name=shortcut_name,
                icon=icon_path
            )
            print(f"Successfully created '{shortcut_name}' in /Applications.")
        else:
             print(f"Shortcut creation is not supported on this OS: {system}")
             return
            
    except Exception as e:
        print(f"Failed to create shortcut: {e}")
    
    # Register file associations on Windows
    if system == "Windows" and exe_path:
        register_file_associations_windows(exe_path, icon_path)

if __name__ == "__main__":
    create_shortcut()
    