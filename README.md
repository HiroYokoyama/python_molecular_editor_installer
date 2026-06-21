# MoleditPy Installer

This package is a helper utility that automatically installs the correct version of `moleditpy` or `moleditpy-linux` for your OS, creates an application menu shortcut, and registers file associations (Windows only).

## How to Use

1.  **Install**
    ```bash
    pip install moleditpy-installer
    ```
    This will automatically install the correct `moleditpy` package (for Windows/macOS) or `moleditpy-linux` (for Linux) as a dependency.

2.  **Create Shortcut**
    After installation, run the following command in your terminal to create the shortcut in your application menu (e.g., Start Menu on Windows) and register file associations for `.pmeprj` and `.pmeraw` files (Windows only).

    ```bash
    moleditpy-installer
    ```

    You can also invoke it as a Python module (use an **underscore**, not a hyphen):

    ```bash
    python -m moleditpy_installer
    ```

    > **Note:** `python -m moleditpy-installer` (with a hyphen) is invalid Python syntax and will not work. Always use the underscore form (`moleditpy_installer`) with `-m`.

3.  **Remove Shortcut**
    To remove the shortcut and unregister file associations, run:

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
    This command returns exit code `0` if the executable is found, and `1` otherwise.

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