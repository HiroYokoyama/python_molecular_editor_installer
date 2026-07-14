# Executable Search Paths

This document details the search order and directories scanned by `moleditpy-installer` to locate the `moleditpy` (or `moleditpy-linux`) executable.

The installer scans these paths sequentially and returns the first valid, executable file it finds.

---

## 1. Interpreter-Relative Directories (All OS)
The installer first checks directories relative to the running Python interpreter (`sys.executable`). This is highly reliable for virtual environments and conda environments.
* Sibling `Scripts` or `bin` directory (e.g. `path/to/python/parent/Scripts` or `path/to/python/parent/bin`)
* Interpreter folder itself (e.g. `path/to/python/parent/`)

## 2. Script Entry-Point Sibling (All OS)
The installer checks the directory next to the wrapper script that started the installer (`sys.argv[0]`). Because pip installs related packages into the same folder, this finds sibling executables:
* `path/to/moleditpy-installer/parent/`

## 3. User-Local Directories

### Windows
If running on Windows, the installer searches these user-local directories:
1. **User scheme via `sysconfig`:**
   * Dynamic lookup using `sysconfig.get_path("scripts", "nt_user")`
2. **Microsoft Store Python Packages:**
   * `%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.*\LocalCache\local-packages\Python*\Scripts`
3. **Standard Python Installer (User-Level):**
   * `%LOCALAPPDATA%\Programs\Python\Python*\Scripts` (Sorted to prefer the newest Python version)
4. **Alternative Python Installer (User-Level):**
   * `%APPDATA%\Python\Python*\Scripts` (Sorted to prefer the newest Python version)
5. **Conda Windows User Installations:**
   * `~/miniconda3/Scripts`
   * `~/anaconda3/Scripts`
   * `~/AppData/Local/miniconda3/Scripts`
   * `~/AppData/Local/anaconda3/Scripts`
6. **pyenv-win Versions:**
   * `~/.pyenv/pyenv-win/versions/*/Scripts` (Sorted to prefer the newest Python version)
7. **Poetry (Windows):**
   * `%APPDATA%\pypoetry\venv\Scripts`
   * `~/.poetry/bin`

### macOS & Linux
If running on a Unix-like OS, the installer searches these directories:
1. **User schemes via `sysconfig`:**
   * `sysconfig.get_path("scripts", "posix_user")`
   * `sysconfig.get_path("scripts", "osx_framework_user")`
2. **Standard User Bin:**
   * `~/.local/bin`
3. **macOS Python Library Bin (macOS only):**
   * `~/Library/Python/*/bin` (Sorted to prefer the newest Python version)
4. **pyenv Versions:**
   * `~/.pyenv/versions/*/bin` (Sorted to prefer the newest Python version)
5. **ASDF Python Installs:**
   * `~/.asdf/installs/python/*/bin` (Sorted to prefer the newest Python version)
6. **Mise (formerly RTX) Python Installs:**
   * `~/.local/share/mise/installs/python/*/bin` (Sorted to prefer the newest Python version)
7. **Conda Environment Directories:**
   * `~/miniconda3/envs/*/bin`
   * `~/anaconda3/envs/*/bin`
   * `~/.conda/envs/*/bin`
8. **Common Unix Package Manager & Shell Paths:**
   * `~/miniconda3/bin`
   * `~/anaconda3/bin`
   * `~/.linuxbrew/bin` (Homebrew Linux)
   * `~/.nix-profile/bin` (Nix Package Manager)
   * `~/.guix-profile/bin` (Guix)
   * `~/.asdf/shims` (ASDF shims)
   * `~/.poetry/bin`
   * `~/bin`
   * `~/.bin`
9. **System-wide Conda Installations** (their `bin` plus `envs/*/bin`):
   * `/opt/miniconda3` (macOS pkg-installer default)
   * `/opt/anaconda3`
   * `/opt/conda` (docker/miniforge convention)
   * `/opt/homebrew/Caskroom/miniconda/base`
   * `/usr/local/miniconda3`
   * `/usr/local/anaconda3`

## 4. System PATH (All OS)
As a final fallback, the installer checks the standard system `PATH` environment variable using `shutil.which`.
