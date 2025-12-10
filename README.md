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

3.  **Remove Shortcut**
    To remove the shortcut and unregister file associations, run:

    ```bash
    moleditpy-installer --remove
    ```

4.  **Help**
    To see all available options, run:

    ```bash
    moleditpy-installer --help

    ```
