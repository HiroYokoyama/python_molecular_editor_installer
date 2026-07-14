"""
Tests for moleditpy_installer.main

Run with:
    python -m pytest tests/ -v
    python -m pytest tests/ -v --cov=moleditpy_installer --cov-report=term-missing
"""

import os
import platform
import stat
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "moleditpy-installer"))

from moleditpy_installer import main as installer_main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_exe(directory: Path, name: str) -> Path:
    """Create a zero-byte executable file for test purposes."""
    if platform.system() == "Windows":
        path = directory / f"{name}.exe"
    else:
        path = directory / name
    path.write_bytes(b"")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _make_winreg_mock():
    """Return a mock winreg module with the constants and functions needed."""
    m = types.ModuleType("winreg")
    m.HKEY_CURRENT_USER = 0x80000001
    m.KEY_ALL_ACCESS = 0xF003F
    m.REG_SZ = 1

    fake_key = mock.MagicMock()
    fake_key.__enter__ = mock.Mock(return_value=fake_key)
    fake_key.__exit__ = mock.Mock(return_value=False)

    m.CreateKey = mock.Mock(return_value=fake_key)
    m.OpenKey = mock.Mock(return_value=fake_key)
    m.SetValue = mock.Mock()
    m.DeleteKey = mock.Mock()
    m.QueryInfoKey = mock.Mock(return_value=(0, 0, 0))  # 0 subkeys by default
    m.EnumKey = mock.Mock(return_value="subkey")
    m.CloseKey = mock.Mock()
    return m


# ---------------------------------------------------------------------------
# find_executable
# ---------------------------------------------------------------------------


class TestFindExecutable:
    """Tests for find_executable path detection logic."""

    def test_finds_exe_next_to_python_interpreter(self, tmp_path):
        """Executable in Scripts/ sibling of sys.executable should be found first."""
        scripts = tmp_path / "Scripts"
        scripts.mkdir()
        _make_fake_exe(scripts, "moleditpy")

        with mock.patch.object(
            installer_main.sys, "executable", str(tmp_path / "python.exe")
        ):
            with mock.patch.object(
                installer_main.sys, "argv", [str(tmp_path / "some_script.py")]
            ):
                with mock.patch("shutil.which", return_value=None):
                    result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result.lower()

    def test_finds_exe_in_same_dir_as_python_unix(self, tmp_path):
        """Executable in the same dir as sys.executable (Linux/macOS layout)."""
        with mock.patch("platform.system", return_value="Linux"):
            _make_fake_exe(tmp_path, "moleditpy")

            with (
                mock.patch.object(
                    installer_main.sys, "executable", str(tmp_path / "python")
                ),
                mock.patch.object(
                    installer_main.sys, "argv", [str(tmp_path / "some_script.py")]
                ),
                mock.patch("shutil.which", return_value=None),
            ):
                result = installer_main.find_executable("moleditpy")

        assert result is not None

    def test_finds_exe_in_python_dir(self, tmp_path):
        """Executable found in the directory containing sys.executable (any OS)."""
        exe = _make_fake_exe(tmp_path, "moleditpy")

        with (
            mock.patch.object(
                installer_main.sys, "executable", str(tmp_path / "python.exe")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(tmp_path / "some_script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
        ):
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert Path(result).name == exe.name

    def test_finds_exe_via_argv0_dir(self, tmp_path):
        """Executable next to sys.argv[0] (direct script invocation fallback)."""
        scripts = tmp_path / "scripts_dir"
        scripts.mkdir()
        _make_fake_exe(scripts, "moleditpy")

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with mock.patch.object(
            installer_main.sys, "executable", str(fake_python_dir / "python.exe")
        ):
            with mock.patch.object(
                installer_main.sys, "argv", [str(scripts / "moleditpy-installer")]
            ):
                with mock.patch("shutil.which", return_value=None):
                    result = installer_main.find_executable("moleditpy")

        assert result is not None

    def test_falls_back_to_shutil_which(self, tmp_path):
        """If not found locally, shutil.which result is returned."""
        fake_path = str(tmp_path / "moleditpy")

        with mock.patch.object(
            installer_main.sys, "executable", str(tmp_path / "python.exe")
        ):
            with mock.patch.object(
                installer_main.sys, "argv", [str(tmp_path / "script.py")]
            ):
                with mock.patch("shutil.which", return_value=fake_path):
                    result = installer_main.find_executable("moleditpy")

        assert result == fake_path

    def test_returns_none_when_not_found(self, tmp_path):
        """Returns None when the executable cannot be located anywhere."""
        with mock.patch.object(
            installer_main.sys, "executable", str(tmp_path / "python.exe")
        ):
            with mock.patch.object(
                installer_main.sys, "argv", [str(tmp_path / "script.py")]
            ):
                with mock.patch("shutil.which", return_value=None):
                    result = installer_main.find_executable("nonexistent_app")

        assert result is None

    def test_finds_exe_in_user_local_bin(self, tmp_path):
        """~/.local/bin is searched for pip --user installs on Linux/macOS."""
        user_local_bin = tmp_path / ".local" / "bin"
        user_local_bin.mkdir(parents=True)

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Linux"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
        ):
            _make_fake_exe(user_local_bin, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result

    def test_finds_exe_in_macos_user_python_bin(self, tmp_path):
        """~/Library/Python/3.9/bin is searched on macOS/Darwin."""
        mac_user_bin = tmp_path / "Library" / "Python" / "3.9" / "bin"
        mac_user_bin.mkdir(parents=True)

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch("sysconfig.get_scheme_names", return_value=[]),
        ):
            _make_fake_exe(mac_user_bin, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result

    def test_finds_exe_via_sysconfig_user_scheme_windows(self, tmp_path):
        """User scheme from sysconfig (nt_user) is searched on Windows."""
        sysconfig_bin = tmp_path / "sysconfig_bin"
        sysconfig_bin.mkdir()

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python.exe")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch("sysconfig.get_path", return_value=str(sysconfig_bin)),
        ):
            _make_fake_exe(sysconfig_bin, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result.lower()

    def test_finds_exe_via_sysconfig_user_scheme_posix(self, tmp_path):
        """User scheme from sysconfig (posix_user) is searched on Unix/Linux/macOS."""
        sysconfig_bin = tmp_path / "sysconfig_bin"
        sysconfig_bin.mkdir()

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Linux"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch("sysconfig.get_scheme_names", return_value=["posix_user"]),
            mock.patch("sysconfig.get_path", return_value=str(sysconfig_bin)),
        ):
            _make_fake_exe(sysconfig_bin, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert Path(result).name == "moleditpy"

    def test_finds_exe_in_localappdata_scripts(self, tmp_path):
        """User-level Python Scripts dir under %LOCALAPPDATA% is searched on Windows."""
        scripts_dir = tmp_path / "Programs" / "Python312" / "Scripts"
        scripts_dir.mkdir(parents=True)

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python.exe")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch.dict(os.environ, {"LOCALAPPDATA": str(tmp_path)}, clear=False),
        ):
            _make_fake_exe(scripts_dir, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result.lower()

    def test_finds_exe_in_ms_store_python_scripts(self, tmp_path):
        """Microsoft Store Python user-level scripts are searched on Windows."""
        scripts_dir = (
            tmp_path
            / "Packages"
            / "PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0"
            / "LocalCache"
            / "local-packages"
            / "Python312"
            / "Scripts"
        )
        scripts_dir.mkdir(parents=True)

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python.exe")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch.dict(os.environ, {"LOCALAPPDATA": str(tmp_path)}, clear=False),
            mock.patch("sysconfig.get_path", side_effect=Exception("mocked error")),
        ):
            _make_fake_exe(scripts_dir, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result.lower()

    def test_finds_exe_in_roaming_appdata_scripts(self, tmp_path):
        """User-level Python Scripts dir under %APPDATA% is searched on Windows."""
        scripts_dir = tmp_path / "Python" / "Python312" / "Scripts"
        scripts_dir.mkdir(parents=True)

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python.exe")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch.dict(os.environ, {"APPDATA": str(tmp_path)}, clear=False),
            mock.patch("sysconfig.get_path", side_effect=Exception("mocked error")),
        ):
            _make_fake_exe(scripts_dir, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result.lower()

    def test_finds_exe_in_user_conda_scripts(self, tmp_path):
        """Common user Conda directory is searched on Windows."""
        scripts_dir = tmp_path / "miniconda3" / "Scripts"
        scripts_dir.mkdir(parents=True)

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python.exe")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch("sysconfig.get_path", side_effect=Exception("mocked error")),
        ):
            _make_fake_exe(scripts_dir, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result.lower()

    def test_finds_exe_in_pyenv_versions(self, tmp_path):
        """pyenv version binaries are searched on macOS/Linux."""
        scripts_dir = tmp_path / ".pyenv" / "versions" / "3.12.0" / "bin"
        scripts_dir.mkdir(parents=True)

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch("sysconfig.get_scheme_names", return_value=[]),
        ):
            _make_fake_exe(scripts_dir, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result

    def test_finds_exe_in_custom_user_bin_directories(self, tmp_path):
        """~/bin or ~/.bin is searched on macOS/Linux."""
        scripts_dir = tmp_path / "bin"
        scripts_dir.mkdir(parents=True)

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch("sysconfig.get_scheme_names", return_value=[]),
        ):
            _make_fake_exe(scripts_dir, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result

    def test_finds_exe_in_unix_conda_envs(self, tmp_path):
        """miniconda3/envs/*/bin is searched on Linux/macOS."""
        scripts_dir = tmp_path / "miniconda3" / "envs" / "test_env" / "bin"
        scripts_dir.mkdir(parents=True)

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Linux"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch("sysconfig.get_scheme_names", return_value=[]),
        ):
            _make_fake_exe(scripts_dir, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result

    def test_finds_exe_in_pyenv_win(self, tmp_path):
        """pyenv-win version binaries are searched on Windows."""
        scripts_dir = (
            tmp_path / ".pyenv" / "pyenv-win" / "versions" / "3.12.0" / "Scripts"
        )
        scripts_dir.mkdir(parents=True)

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python.exe")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch("sysconfig.get_path", side_effect=Exception("mocked error")),
        ):
            _make_fake_exe(scripts_dir, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result.lower()

    def test_finds_exe_in_poetry_windows(self, tmp_path):
        """Poetry global scripts are searched on Windows."""
        scripts_dir = tmp_path / "pypoetry" / "venv" / "Scripts"
        scripts_dir.mkdir(parents=True)

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python.exe")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch.dict(os.environ, {"LOCALAPPDATA": str(tmp_path)}, clear=False),
            mock.patch.dict(os.environ, {"APPDATA": str(tmp_path)}, clear=False),
            mock.patch("sysconfig.get_path", side_effect=Exception("mocked error")),
        ):
            _make_fake_exe(scripts_dir, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result.lower()

    def test_finds_exe_in_asdf(self, tmp_path):
        """ASDF python installations are searched on macOS/Linux."""
        scripts_dir = tmp_path / ".asdf" / "installs" / "python" / "3.12.0" / "bin"
        scripts_dir.mkdir(parents=True)

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Linux"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch("sysconfig.get_scheme_names", return_value=[]),
        ):
            _make_fake_exe(scripts_dir, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert Path(result).name == "moleditpy"

    def test_finds_exe_in_mise(self, tmp_path):
        """Mise python installations are searched on macOS/Linux."""
        scripts_dir = (
            tmp_path
            / ".local"
            / "share"
            / "mise"
            / "installs"
            / "python"
            / "3.12.0"
            / "bin"
        )
        scripts_dir.mkdir(parents=True)

        fake_python_dir = tmp_path / "python_dir"
        fake_python_dir.mkdir()

        with (
            mock.patch("platform.system", return_value="Linux"),
            mock.patch.object(
                installer_main.sys, "executable", str(fake_python_dir / "python")
            ),
            mock.patch.object(
                installer_main.sys, "argv", [str(fake_python_dir / "script.py")]
            ),
            mock.patch("shutil.which", return_value=None),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch("sysconfig.get_scheme_names", return_value=[]),
        ):
            _make_fake_exe(scripts_dir, "moleditpy")
            result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert Path(result).name == "moleditpy"


# ---------------------------------------------------------------------------
# get_icon_path
# ---------------------------------------------------------------------------


class TestGetIconPath:
    def test_returns_path_on_windows(self, tmp_path):
        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(
                installer_main, "get_persistent_data_dir", return_value=tmp_path
            ),
        ):
            path = installer_main.get_icon_path()
        assert path is None or path.endswith(".ico")

    def test_returns_path_on_linux(self, tmp_path):
        with (
            mock.patch("platform.system", return_value="Linux"),
            mock.patch.object(
                installer_main, "get_persistent_data_dir", return_value=tmp_path
            ),
        ):
            path = installer_main.get_icon_path()
        assert path is None or path.endswith(".png")

    def test_returns_path_on_darwin(self, tmp_path):
        with (
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch.object(
                installer_main, "get_persistent_data_dir", return_value=tmp_path
            ),
        ):
            path = installer_main.get_icon_path()
        assert path is None or path.endswith(".icns")

    def test_returns_none_on_unknown_os(self):
        with mock.patch("platform.system", return_value="FreeBSD"):
            path = installer_main.get_icon_path()
        assert path is None

    def test_returns_none_when_resource_raises(self):
        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("importlib.resources.files", side_effect=OSError("not found")),
        ):
            path = installer_main.get_icon_path()
        assert path is None

    def test_returns_none_when_file_missing_in_package(self, tmp_path):
        """as_file context resolves to a path that doesn't exist."""
        missing = tmp_path / "icon.ico"

        fake_ref = mock.MagicMock()
        fake_ref.__truediv__ = mock.Mock(return_value=fake_ref)

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("importlib.resources.files", return_value=fake_ref),
            mock.patch("importlib.resources.as_file") as mock_as_file,
        ):
            mock_as_file.return_value.__enter__ = mock.Mock(return_value=missing)
            mock_as_file.return_value.__exit__ = mock.Mock(return_value=False)
            path = installer_main.get_icon_path()

        assert path is None


# ---------------------------------------------------------------------------
# get_file_icon_path
# ---------------------------------------------------------------------------


class TestGetFileIconPath:
    def test_returns_none_on_non_windows(self):
        with mock.patch("platform.system", return_value="Linux"):
            assert installer_main.get_file_icon_path() is None

    def test_returns_persistent_path_on_windows(self, tmp_path):
        """The icon must be extracted to a persistent dir (not %TEMP%),
        because the registry references it long after install."""
        fake_ref = mock.MagicMock()
        fake_ref.__truediv__ = mock.Mock(return_value=fake_ref)
        fake_ref.read_bytes = mock.Mock(return_value=b"icon-bytes")

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("importlib.resources.files", return_value=fake_ref),
            mock.patch.object(
                installer_main, "get_persistent_data_dir", return_value=tmp_path
            ),
        ):
            path = installer_main.get_file_icon_path()

        assert path == str(tmp_path / "file_icon.ico")
        assert (tmp_path / "file_icon.ico").read_bytes() == b"icon-bytes"

    def test_returns_none_when_resource_raises(self):
        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("importlib.resources.files", side_effect=OSError("boom")),
        ):
            assert installer_main.get_file_icon_path() is None


# ---------------------------------------------------------------------------
# register_file_associations_windows
# ---------------------------------------------------------------------------


class TestRegisterFileAssociationsWindows:
    def test_returns_false_on_non_windows(self):
        with mock.patch("platform.system", return_value="Linux"):
            assert (
                installer_main.register_file_associations_windows("/bin/app", None)
                is False
            )

    def test_registers_extensions_on_windows(self, tmp_path):
        fake_icon = str(tmp_path / "icon.ico")
        Path(fake_icon).write_bytes(b"")
        winreg_mock = _make_winreg_mock()

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(installer_main, "winreg", winreg_mock),
        ):
            result = installer_main.register_file_associations_windows(
                r"C:\app\moleditpy.exe", fake_icon
            )

        assert result is True
        assert (
            winreg_mock.CreateKey.call_count >= 4
        )  # ProgID + DefaultIcon + command + 2 exts

    def test_returns_false_on_oserror(self):
        winreg_mock = _make_winreg_mock()
        winreg_mock.CreateKey.side_effect = OSError("access denied")

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(installer_main, "winreg", winreg_mock),
        ):
            result = installer_main.register_file_associations_windows(
                r"C:\app\moleditpy.exe", None
            )

        assert result is False

    def test_skips_icon_when_path_missing(self):
        winreg_mock = _make_winreg_mock()

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(installer_main, "winreg", winreg_mock),
        ):
            result = installer_main.register_file_associations_windows(
                r"C:\app\moleditpy.exe", None
            )

        assert result is True


# ---------------------------------------------------------------------------
# register_file_associations_darwin
# ---------------------------------------------------------------------------


class TestRegisterFileAssociationsDarwin:
    @pytest.fixture(autouse=True)
    def _isolate_persistent_dir(self, tmp_path):
        """The function extracts file_icon.icns — keep the tests away
        from the real per-user persistent dir."""
        with mock.patch.object(
            installer_main,
            "get_persistent_data_dir",
            return_value=tmp_path / "persistent",
        ):
            (tmp_path / "persistent").mkdir(exist_ok=True)
            yield

    def test_returns_false_on_non_darwin(self, tmp_path):
        with mock.patch("platform.system", return_value="Linux"):
            assert installer_main.register_file_associations_darwin(tmp_path) is False

    def test_returns_false_when_plist_missing(self, tmp_path):
        with mock.patch("platform.system", return_value="Darwin"):
            assert installer_main.register_file_associations_darwin(tmp_path) is False

    def test_adds_file_association_to_plist(self, tmp_path):
        app_path = tmp_path / "MoleditPy.app"
        contents_path = app_path / "Contents"
        contents_path.mkdir(parents=True)
        plist_path = contents_path / "Info.plist"

        import plistlib

        initial_plist = {"CFBundleIdentifier": "com.moleditpy"}
        with open(plist_path, "wb") as fp:
            plistlib.dump(initial_plist, fp)

        with mock.patch("platform.system", return_value="Darwin"):
            result = installer_main.register_file_associations_darwin(app_path)

        assert result is True
        with open(plist_path, "rb") as fp:
            pl = plistlib.load(fp)

        assert "CFBundleDocumentTypes" in pl
        doc_types = pl["CFBundleDocumentTypes"]
        assert len(doc_types) == 1
        assert "pmeprj" in doc_types[0]["CFBundleTypeExtensions"]

    def test_does_not_duplicate_existing_association(self, tmp_path):
        app_path = tmp_path / "MoleditPy.app"
        contents_path = app_path / "Contents"
        contents_path.mkdir(parents=True)
        plist_path = contents_path / "Info.plist"

        import plistlib

        initial_plist = {
            "CFBundleIdentifier": "com.moleditpy",
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeExtensions": ["pmeprj"],
                    "CFBundleTypeName": "MoleditPy Project File",
                    "CFBundleTypeRole": "Editor",
                    "LSHandlerRank": "Owner",
                }
            ],
        }
        with open(plist_path, "wb") as fp:
            plistlib.dump(initial_plist, fp)

        with mock.patch("platform.system", return_value="Darwin"):
            result = installer_main.register_file_associations_darwin(app_path)

        assert result is True
        with open(plist_path, "rb") as fp:
            pl = plistlib.load(fp)

        assert len(pl["CFBundleDocumentTypes"]) == 1

    def test_returns_false_on_load_error(self, tmp_path):
        app_path = tmp_path / "MoleditPy.app"
        contents_path = app_path / "Contents"
        contents_path.mkdir(parents=True)
        plist_path = contents_path / "Info.plist"
        # Write invalid plist data
        plist_path.write_bytes(b"invalid data")

        with mock.patch("platform.system", return_value="Darwin"):
            result = installer_main.register_file_associations_darwin(app_path)

        assert result is False


# ---------------------------------------------------------------------------
# delete_registry_tree
# ---------------------------------------------------------------------------


class TestDeleteRegistryTree:
    def test_deletes_key_with_no_subkeys(self):
        winreg_mock = _make_winreg_mock()
        winreg_mock.QueryInfoKey.return_value = (0, 0, 0)

        with mock.patch.object(installer_main, "winreg", winreg_mock):
            result = installer_main.delete_registry_tree(
                winreg_mock.HKEY_CURRENT_USER, "key"
            )

        assert result is True
        winreg_mock.DeleteKey.assert_called_once()

    def test_returns_false_on_oserror(self):
        winreg_mock = _make_winreg_mock()
        winreg_mock.OpenKey.side_effect = OSError("not found")

        with mock.patch.object(installer_main, "winreg", winreg_mock):
            result = installer_main.delete_registry_tree(
                winreg_mock.HKEY_CURRENT_USER, "key"
            )

        assert result is False


# ---------------------------------------------------------------------------
# unregister_file_associations_windows
# ---------------------------------------------------------------------------


class TestUnregisterFileAssociationsWindows:
    def test_no_op_on_non_windows(self):
        with mock.patch("platform.system", return_value="Linux"):
            installer_main.unregister_file_associations_windows()  # should not raise

    def test_removes_keys_on_windows(self):
        winreg_mock = _make_winreg_mock()

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(installer_main, "winreg", winreg_mock),
            mock.patch.object(
                installer_main, "delete_registry_tree", return_value=True
            ) as mock_del,
        ):
            installer_main.unregister_file_associations_windows()

        assert winreg_mock.DeleteKey.call_count == 2  # .pmeprj and .pmeraw
        mock_del.assert_called_once()

    def test_ignores_already_missing_keys(self, capsys):
        winreg_mock = _make_winreg_mock()
        winreg_mock.DeleteKey.side_effect = FileNotFoundError

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(installer_main, "winreg", winreg_mock),
            mock.patch.object(
                installer_main, "delete_registry_tree", return_value=False
            ),
        ):
            installer_main.unregister_file_associations_windows()

        # Should complete without error output about missing keys
        captured = capsys.readouterr()
        assert "failed" not in captured.out.lower()

    def test_prints_error_on_oserror(self, capsys):
        winreg_mock = _make_winreg_mock()
        winreg_mock.DeleteKey.side_effect = OSError("permission denied")

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(installer_main, "winreg", winreg_mock),
            mock.patch.object(
                installer_main, "delete_registry_tree", return_value=False
            ),
        ):
            installer_main.unregister_file_associations_windows()

        captured = capsys.readouterr()
        assert "failed" in captured.out.lower()


# ---------------------------------------------------------------------------
# remove_shortcut
# ---------------------------------------------------------------------------


class TestRemoveShortcut:
    @pytest.fixture(autouse=True)
    def _isolate_persistent_dir(self, tmp_path):
        """remove_shortcut() deletes the persistent icon dir — keep the
        tests away from the real one."""
        with mock.patch.object(
            installer_main,
            "get_persistent_data_dir",
            return_value=tmp_path / "persistent",
        ):
            (tmp_path / "persistent").mkdir(exist_ok=True)
            yield

    def test_removes_lnk_on_windows(self, tmp_path):
        lnk = tmp_path / "MoleditPy.lnk"
        lnk.write_bytes(b"")

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.dict(os.environ, {"APPDATA": str(tmp_path / "AppData")}),
            mock.patch.object(installer_main, "unregister_file_associations_windows"),
            mock.patch("pathlib.Path.exists", return_value=True),
            mock.patch("os.remove") as mock_rm,
        ):
            installer_main.remove_shortcut()

        # Both the Start Menu and the Desktop shortcuts must be removed
        # (pyshortcuts creates both at install time).
        assert mock_rm.call_count == 2
        removed = {str(c.args[0]) for c in mock_rm.call_args_list}
        assert any("Start Menu" in p for p in removed)
        assert any("Desktop" in p for p in removed)

    def test_removes_desktop_file_on_linux(self, tmp_path):
        apps_dir = tmp_path / ".local" / "share" / "applications"
        apps_dir.mkdir(parents=True)
        desktop = apps_dir / "MoleditPy.desktop"
        desktop.write_bytes(b"")

        with (
            mock.patch("platform.system", return_value="Linux"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
        ):
            installer_main.remove_shortcut()

        assert not desktop.exists()

    def test_removes_app_bundle_on_darwin_applications(self, tmp_path):
        app_bundle = tmp_path / "Applications" / "MoleditPy.app"
        app_bundle.mkdir(parents=True)

        with (
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
        ):
            installer_main.remove_shortcut()

        assert not app_bundle.exists()

    def test_removes_app_bundle_on_darwin_desktop_fallback(self, tmp_path):
        app_bundle = tmp_path / "Desktop" / "MoleditPy.app"
        app_bundle.mkdir(parents=True)

        with (
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
        ):
            installer_main.remove_shortcut()

        assert not app_bundle.exists()

    def test_darwin_remove_unregisters_launch_services(self, tmp_path):
        """A deleted bundle must be dropped from the LS database, or it
        keeps claiming .pmeprj files."""
        app_bundle = tmp_path / "Applications" / "MoleditPy.app"
        app_bundle.mkdir(parents=True)

        with (
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch.object(installer_main, "refresh_launch_services") as mock_ls,
        ):
            installer_main.remove_shortcut()

        mock_ls.assert_called_once_with(app_bundle, unregister=True)

    def test_remove_cleans_persistent_icon_dir(self, tmp_path):
        persistent = tmp_path / "persistent"  # created by the autouse fixture
        (persistent / "icon.ico").write_bytes(b"x")

        with (
            mock.patch("platform.system", return_value="Linux"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
        ):
            installer_main.remove_shortcut()

        assert not persistent.exists()

    def test_prints_message_when_shortcut_missing(self, capsys):
        with (
            mock.patch("platform.system", return_value="Linux"),
            mock.patch("pathlib.Path.home", return_value=Path("/nonexistent/path")),
        ):
            installer_main.remove_shortcut()

        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()

    def test_unsupported_os(self, capsys):
        with mock.patch("platform.system", return_value="FreeBSD"):
            installer_main.remove_shortcut()

        captured = capsys.readouterr()
        assert "not fully supported" in captured.out.lower()

    def test_prints_error_on_remove_failure(self, capsys):
        with (
            mock.patch("platform.system", return_value="Linux"),
            mock.patch("pathlib.Path.home", return_value=Path("/tmp")),
            mock.patch("pathlib.Path.exists", return_value=True),
            mock.patch("pathlib.Path.is_dir", return_value=False),
            mock.patch("os.remove", side_effect=OSError("permission denied")),
        ):
            installer_main.remove_shortcut()

        captured = capsys.readouterr()
        assert "failed" in captured.out.lower()


# ---------------------------------------------------------------------------
# install() — high-level smoke tests
# ---------------------------------------------------------------------------


class TestInstall:
    def test_install_aborts_when_executable_not_found(self, capsys):
        with mock.patch.object(installer_main, "find_executable", return_value=None):
            installer_main.install()

        captured = capsys.readouterr()
        assert "not found" in captured.out.lower() or "error" in captured.out.lower()

    def test_install_calls_make_shortcut_on_windows(self, tmp_path):
        fake_exe = str(tmp_path / "moleditpy.exe")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(installer_main, "get_file_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "register_file_associations_windows", return_value=True
            ),
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("moleditpy_installer.main.make_shortcut") as mock_shortcut,
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            installer_main.install()

        mock_shortcut.assert_called_once()
        _, kwargs = mock_shortcut.call_args
        assert kwargs.get("startmenu") is True
        assert kwargs.get("desktop") is True

    def test_install_calls_make_shortcut_on_linux(self, tmp_path):
        fake_exe = str(tmp_path / "moleditpy")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch("platform.system", return_value="Linux"),
            mock.patch("moleditpy_installer.main.make_shortcut") as mock_shortcut,
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            installer_main.install()

        mock_shortcut.assert_called_once()
        _, kwargs = mock_shortcut.call_args
        assert kwargs.get("startmenu") is True
        assert kwargs.get("desktop") is True

    def test_install_calls_osacompile_on_darwin(self, tmp_path):
        fake_exe = str(tmp_path / "moleditpy")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "python_for_executable", return_value=sys.executable
            ),
            mock.patch.object(
                installer_main, "verify_launch_command", return_value=True
            ),
            mock.patch.object(installer_main, "refresh_launch_services"),
            mock.patch.object(installer_main, "codesign_app"),
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch("subprocess.run") as mock_run,
            mock.patch("shutil.copytree"),
            mock.patch("moleditpy_installer.main.register_file_associations_darwin"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            installer_main.install()

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "osacompile"
        assert "-e" in args
        # The AppleScript must have the "on open" handler for double-clicked
        # files and run MoleditPy inside Terminal so output stays visible.
        applescript_idx = args.index("-e") + 1
        applescript = args[applescript_idx]
        assert "on open dropped_items" in applescript
        assert 'tell application "Terminal"' in applescript
        assert "do script" in applescript

    def test_install_darwin_uses_env_of_found_executable(self, tmp_path):
        """The launcher must use the found script's own interpreter, not
        blindly sys.executable — mismatched envs cause ModuleNotFoundError."""
        fake_exe = str(tmp_path / "moleditpy")
        env_python = str(tmp_path / "envbin" / "python3")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "python_for_executable", return_value=env_python
            ),
            mock.patch.object(
                installer_main, "verify_launch_command", return_value=True
            ) as mock_verify,
            mock.patch.object(installer_main, "refresh_launch_services"),
            mock.patch.object(installer_main, "codesign_app"),
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch("subprocess.run") as mock_run,
            mock.patch("shutil.copytree"),
            mock.patch("moleditpy_installer.main.register_file_associations_darwin"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            installer_main.install()

        mock_verify.assert_called_once_with(env_python, fake_exe)
        args = mock_run.call_args[0][0]
        applescript = args[args.index("-e") + 1]
        assert env_python in applescript

    def test_install_darwin_falls_back_to_sys_executable(self, tmp_path):
        """If the paired interpreter cannot launch moleditpy but
        sys.executable can, the launcher uses sys.executable."""
        fake_exe = str(tmp_path / "moleditpy")
        bad_python = str(tmp_path / "badbin" / "python3")

        def fake_verify(python_path, exe_path):
            return python_path == sys.executable

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "python_for_executable", return_value=bad_python
            ),
            mock.patch.object(
                installer_main, "verify_launch_command", side_effect=fake_verify
            ),
            mock.patch.object(installer_main, "refresh_launch_services"),
            mock.patch.object(installer_main, "codesign_app"),
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch("subprocess.run") as mock_run,
            mock.patch("shutil.copytree"),
            mock.patch("moleditpy_installer.main.register_file_associations_darwin"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            installer_main.install()

        args = mock_run.call_args[0][0]
        applescript = args[args.index("-e") + 1]
        assert sys.executable in applescript
        assert bad_python not in applescript

    def test_install_darwin_copies_app_to_applications(self, tmp_path):
        fake_exe = str(tmp_path / "moleditpy")

        def mock_subprocess_run(*args, **kwargs):
            # Simulate osacompile creating the target app directory
            app_path = args[0][2]
            os.makedirs(app_path, exist_ok=True)

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "python_for_executable", return_value=sys.executable
            ),
            mock.patch.object(
                installer_main, "verify_launch_command", return_value=True
            ),
            mock.patch.object(installer_main, "refresh_launch_services"),
            mock.patch.object(installer_main, "codesign_app"),
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch("subprocess.run", side_effect=mock_subprocess_run),
            mock.patch("moleditpy_installer.main.register_file_associations_darwin"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            installer_main.install()

        # It should have copied to ~/Applications
        assert (tmp_path / "Applications" / "MoleditPy.app").exists()

    def test_install_unsupported_os(self, tmp_path, capsys):
        fake_exe = str(tmp_path / "moleditpy")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch("platform.system", return_value="FreeBSD"),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            installer_main.install()

        captured = capsys.readouterr()
        assert "not supported" in captured.out.lower()

    def test_install_uses_conda_run_when_conda_env_active(self, tmp_path):
        fake_exe = str(tmp_path / "moleditpy.exe")
        fake_conda = str(tmp_path / "conda.exe")

        env = {"CONDA_DEFAULT_ENV": "myenv", "CONDA_EXE": fake_conda}

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(installer_main, "get_file_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "register_file_associations_windows", return_value=True
            ),
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("moleditpy_installer.main.make_shortcut") as mock_shortcut,
            mock.patch.dict(os.environ, env, clear=True),
        ):
            installer_main.install()

        mock_shortcut.assert_called_once()
        script_arg = (
            mock_shortcut.call_args[1].get("script") or mock_shortcut.call_args[0][0]
        )
        assert "conda" in script_arg.lower()
        assert "myenv" in script_arg

    def test_install_uses_conda_for_base_env(self, tmp_path):
        """CONDA_DEFAULT_ENV=base should use conda run to ensure proper PATH."""
        fake_exe = str(tmp_path / "moleditpy.exe")
        fake_conda = str(tmp_path / "conda.exe")

        env = {"CONDA_DEFAULT_ENV": "base", "CONDA_EXE": fake_conda}

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(installer_main, "get_file_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "register_file_associations_windows", return_value=True
            ),
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("moleditpy_installer.main.make_shortcut") as mock_shortcut,
            mock.patch.dict(os.environ, env, clear=True),
        ):
            installer_main.install()

        script_arg = (
            mock_shortcut.call_args[1].get("script") or mock_shortcut.call_args[0][0]
        )
        assert fake_conda in script_arg
        assert 'run -n "base"' in script_arg
        assert "--no-capture-output" in script_arg

    def test_install_prefers_conda_prefix_over_env_name(self, tmp_path):
        """CONDA_PREFIX (-p) is preferred: CONDA_DEFAULT_ENV may be a path
        for envs activated by path, where -n would not resolve."""
        fake_exe = str(tmp_path / "moleditpy.exe")
        fake_conda = str(tmp_path / "conda.exe")
        fake_prefix = str(tmp_path / "envs" / "myenv")

        env = {
            "CONDA_DEFAULT_ENV": "myenv",
            "CONDA_EXE": fake_conda,
            "CONDA_PREFIX": fake_prefix,
        }

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(installer_main, "get_file_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "register_file_associations_windows", return_value=True
            ),
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("moleditpy_installer.main.make_shortcut") as mock_shortcut,
            mock.patch.dict(os.environ, env, clear=True),
        ):
            installer_main.install()

        script_arg = (
            mock_shortcut.call_args[1].get("script") or mock_shortcut.call_args[0][0]
        )
        assert f'run -p "{fake_prefix}"' in script_arg
        assert "--no-capture-output" in script_arg

    def test_install_falls_back_to_moleditpy_linux(self, tmp_path):
        """On Linux, if 'moleditpy' is not found, 'moleditpy-linux' is tried."""
        fake_exe = str(tmp_path / "moleditpy-linux")

        def fake_find(name):
            return fake_exe if name == "moleditpy-linux" else None

        with (
            mock.patch.object(installer_main, "find_executable", side_effect=fake_find),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch("platform.system", return_value="Linux"),
            mock.patch("moleditpy_installer.main.make_shortcut") as mock_shortcut,
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            installer_main.install()

        mock_shortcut.assert_called_once()

    def test_install_handles_make_shortcut_oserror(self, tmp_path, capsys):
        fake_exe = str(tmp_path / "moleditpy.exe")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(installer_main, "get_file_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "register_file_associations_windows", return_value=True
            ),
            mock.patch("platform.system", return_value="Windows"),
            mock.patch(
                "moleditpy_installer.main.make_shortcut",
                side_effect=OSError("disk full"),
            ),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            installer_main.install()

        captured = capsys.readouterr()
        assert "failed" in captured.out.lower()


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------


class TestMainCLI:
    def test_main_calls_install_by_default(self):
        with (
            mock.patch.object(
                installer_main, "install", return_value=0
            ) as mock_install,
            mock.patch("sys.argv", ["moleditpy-installer"]),
        ):
            result = installer_main.main()
        mock_install.assert_called_once()
        assert result == 0

    def test_main_propagates_install_failure(self):
        with (
            mock.patch.object(installer_main, "install", return_value=1),
            mock.patch("sys.argv", ["moleditpy-installer"]),
        ):
            assert installer_main.main() == 1

    def test_main_calls_remove_shortcut_with_flag(self):
        with (
            mock.patch.object(installer_main, "remove_shortcut") as mock_remove,
            mock.patch("sys.argv", ["moleditpy-installer", "--remove"]),
        ):
            result = installer_main.main()
        mock_remove.assert_called_once()
        assert result == 0

    def test_get_installer_version(self):
        # Test returning version from metadata when package is installed
        with mock.patch("importlib.metadata.version", return_value="2.0.0"):
            assert installer_main.get_installer_version() == "2.0.0"

        # Last-resort fallback must not claim a concrete (stale) version
        with (
            mock.patch("importlib.metadata.version", side_effect=Exception),
            mock.patch("pathlib.Path.exists", return_value=False),
        ):
            assert installer_main.get_installer_version() == "unknown"

    def test_get_installer_version_from_pyproject(self):
        # Test reading from pyproject.toml when metadata fails
        with (
            mock.patch("importlib.metadata.version", side_effect=Exception),
            mock.patch("pathlib.Path.exists", return_value=True),
            mock.patch(
                "builtins.open", mock.mock_open(read_data='version = "1.5.0"\n')
            ),
        ):
            assert installer_main.get_installer_version() == "1.5.0"

    def test_main_version_flag(self, capsys):
        with (
            mock.patch("sys.argv", ["moleditpy-installer", "--version"]),
            mock.patch(
                "moleditpy_installer.main.get_installer_version", return_value="1.5.0"
            ),
        ):
            with pytest.raises(SystemExit) as excinfo:
                installer_main.main()
        assert excinfo.value.code == 0
        captured = capsys.readouterr()
        output = captured.out or captured.err
        assert "1.5.0" in output
        assert "moleditpy-installer" in output

    def test_main_help_flag_prints_version(self, capsys):
        with (
            mock.patch("sys.argv", ["moleditpy-installer", "--help"]),
            mock.patch(
                "moleditpy_installer.main.get_installer_version", return_value="1.5.0"
            ),
        ):
            with pytest.raises(SystemExit) as excinfo:
                installer_main.main()
        assert excinfo.value.code == 0
        captured = capsys.readouterr()
        output = captured.out or captured.err
        assert "1.5.0" in output
        assert "moleditpy-installer" in output

    def test_main_check_flag_success(self, capsys):
        with (
            mock.patch("sys.argv", ["moleditpy-installer", "--check"]),
            mock.patch(
                "moleditpy_installer.main.find_executable",
                return_value="/path/to/moleditpy",
            ),
            mock.patch("platform.system", return_value="Windows"),
        ):
            result = installer_main.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "Success: Found executable" in captured.out
        assert "/path/to/moleditpy" in captured.out

    def test_main_check_flag_failure(self, capsys):
        with (
            mock.patch("sys.argv", ["moleditpy-installer", "--check"]),
            mock.patch("moleditpy_installer.main.find_executable", return_value=None),
            mock.patch("platform.system", return_value="Windows"),
        ):
            result = installer_main.main()
        assert result == 1
        captured = capsys.readouterr()
        assert "Error: Executable" in captured.out

    def test_main_check_flag_linux_fallback(self, capsys):
        def fake_find(name):
            return "/path/to/moleditpy-linux" if name == "moleditpy-linux" else None

        with (
            mock.patch("sys.argv", ["moleditpy-installer", "--check"]),
            mock.patch(
                "moleditpy_installer.main.find_executable", side_effect=fake_find
            ),
            mock.patch("platform.system", return_value="Linux"),
        ):
            result = installer_main.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "Success: Found executable 'moleditpy-linux'" in captured.out


# ---------------------------------------------------------------------------
# __main__ module
# ---------------------------------------------------------------------------


def test_package_runnable_as_module():
    """Verify __main__.py exists and imports cleanly (enables python -m moleditpy_installer)."""
    import importlib

    mod = importlib.import_module("moleditpy_installer.__main__")
    assert mod is not None


# ---------------------------------------------------------------------------
# python_for_executable
# ---------------------------------------------------------------------------


class TestPythonForExecutable:
    @staticmethod
    def _make_unix_exe(directory: Path, name: str) -> Path:
        """Create an executable with an exact (extension-less, Unix) name."""
        path = directory / name
        path.write_bytes(b"")
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def test_prefers_python3_next_to_script(self, tmp_path):
        exe = self._make_unix_exe(tmp_path, "moleditpy")
        py3 = self._make_unix_exe(tmp_path, "python3")
        self._make_unix_exe(tmp_path, "python")

        result = installer_main.python_for_executable(str(exe))
        assert result == str(py3)

    def test_uses_python_when_no_python3(self, tmp_path):
        exe = self._make_unix_exe(tmp_path, "moleditpy")
        py = self._make_unix_exe(tmp_path, "python")

        result = installer_main.python_for_executable(str(exe))
        assert result == str(py)

    def test_uses_shebang_when_no_adjacent_python(self, tmp_path):
        env_bin = tmp_path / "env" / "bin"
        env_bin.mkdir(parents=True)
        shebang_py = _make_fake_exe(env_bin, "python3.12")

        exe = tmp_path / "moleditpy"
        exe.write_text(f"#!{shebang_py}\nimport moleditpy\n")

        result = installer_main.python_for_executable(str(exe))
        assert result == str(shebang_py)

    def test_ignores_env_shebang(self, tmp_path):
        exe = tmp_path / "moleditpy"
        exe.write_text("#!/usr/bin/env python3\nimport moleditpy\n")

        result = installer_main.python_for_executable(str(exe))
        assert result == sys.executable

    def test_falls_back_to_sys_executable(self, tmp_path):
        exe = tmp_path / "moleditpy"
        exe.write_bytes(b"MZ binary launcher")

        result = installer_main.python_for_executable(str(exe))
        assert result == sys.executable


# ---------------------------------------------------------------------------
# verify_launch_command
# ---------------------------------------------------------------------------


class TestVerifyLaunchCommand:
    def test_returns_true_on_zero_exit(self):
        fake_result = mock.Mock(returncode=0)
        with mock.patch("subprocess.run", return_value=fake_result) as mock_run:
            assert installer_main.verify_launch_command("/py", "/exe") is True
        assert mock_run.call_args[0][0] == ["/py", "/exe", "--version"]

    def test_returns_false_on_nonzero_exit(self):
        fake_result = mock.Mock(returncode=1)
        with mock.patch("subprocess.run", return_value=fake_result):
            assert installer_main.verify_launch_command("/py", "/exe") is False

    def test_returns_false_on_exception(self):
        with mock.patch("subprocess.run", side_effect=OSError("no such file")):
            assert installer_main.verify_launch_command("/py", "/exe") is False


# ---------------------------------------------------------------------------
# refresh_launch_services
# ---------------------------------------------------------------------------


class TestRefreshLaunchServices:
    def test_calls_lsregister_when_present(self, tmp_path):
        app = tmp_path / "MoleditPy.app"
        app.mkdir()

        with (
            mock.patch("pathlib.Path.exists", return_value=True),
            mock.patch("subprocess.run") as mock_run,
        ):
            installer_main.refresh_launch_services(app)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0].endswith("lsregister")
        assert cmd[1] == "-f"
        assert cmd[2] == str(app)

    def test_silent_when_lsregister_missing(self, tmp_path):
        app = tmp_path / "MoleditPy.app"
        app.mkdir()

        # Force the lsregister candidates to look absent (they really do
        # exist on macOS CI runners, so this must be mocked explicitly).
        with (
            mock.patch("pathlib.Path.exists", return_value=False),
            mock.patch("subprocess.run") as mock_run,
        ):
            installer_main.refresh_launch_services(app)

        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# UTI declaration (macOS document binding)
# ---------------------------------------------------------------------------


class TestDarwinUTIDeclaration:
    @pytest.fixture(autouse=True)
    def _isolate_persistent_dir(self, tmp_path):
        with mock.patch.object(
            installer_main,
            "get_persistent_data_dir",
            return_value=tmp_path / "persistent",
        ):
            (tmp_path / "persistent").mkdir(exist_ok=True)
            yield

    def test_exports_pmeprj_uti(self, tmp_path):
        import plistlib

        app_path = tmp_path / "MoleditPy.app"
        contents_path = app_path / "Contents"
        contents_path.mkdir(parents=True)
        plist_path = contents_path / "Info.plist"
        with open(plist_path, "wb") as fp:
            plistlib.dump({"CFBundleIdentifier": "com.moleditpy.launcher"}, fp)

        with mock.patch("platform.system", return_value="Darwin"):
            result = installer_main.register_file_associations_darwin(app_path)

        assert result is True
        with open(plist_path, "rb") as fp:
            pl = plistlib.load(fp)

        doc_types = pl["CFBundleDocumentTypes"]
        assert doc_types[0]["CFBundleTypeExtensions"] == ["pmeprj"]
        assert doc_types[0]["LSItemContentTypes"] == ["com.moleditpy.pmeprj"]

        exported = pl["UTExportedTypeDeclarations"]
        assert exported[0]["UTTypeIdentifier"] == "com.moleditpy.pmeprj"
        assert exported[0]["UTTypeTagSpecification"]["public.filename-extension"] == [
            "pmeprj"
        ]


# ---------------------------------------------------------------------------
# codesign_app
# ---------------------------------------------------------------------------


class TestCodesignApp:
    def test_ad_hoc_signs_bundle(self, tmp_path):
        app = tmp_path / "MoleditPy.app"
        app.mkdir()

        fake_result = mock.Mock(returncode=0, stderr=b"")
        with mock.patch("subprocess.run", return_value=fake_result) as mock_run:
            installer_main.codesign_app(app)

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "codesign"
        assert "--force" in cmd
        assert "-" in cmd  # ad-hoc identity
        assert cmd[-1] == str(app)

    def test_warns_on_failure(self, tmp_path, capsys):
        app = tmp_path / "MoleditPy.app"
        app.mkdir()

        fake_result = mock.Mock(returncode=1, stderr=b"sign error")
        with mock.patch("subprocess.run", return_value=fake_result):
            installer_main.codesign_app(app)

        assert "codesign failed" in capsys.readouterr().out

    def test_survives_missing_codesign(self, tmp_path, capsys):
        app = tmp_path / "MoleditPy.app"
        app.mkdir()

        with mock.patch("subprocess.run", side_effect=FileNotFoundError("codesign")):
            installer_main.codesign_app(app)

        assert "could not re-sign" in capsys.readouterr().out

    def test_install_darwin_signs_both_copies(self, tmp_path):
        """The bundle is modified after osacompile, so BOTH the Desktop and
        ~/Applications copies must be re-signed or Apple Silicon refuses to
        launch them (silently) and ignores their icon."""
        fake_exe = str(tmp_path / "moleditpy")

        def mock_subprocess_run(*args, **kwargs):
            os.makedirs(args[0][2], exist_ok=True)

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "python_for_executable", return_value=sys.executable
            ),
            mock.patch.object(
                installer_main, "verify_launch_command", return_value=True
            ),
            mock.patch.object(installer_main, "refresh_launch_services"),
            mock.patch.object(installer_main, "codesign_app") as mock_sign,
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch("subprocess.run", side_effect=mock_subprocess_run),
            mock.patch("moleditpy_installer.main.register_file_associations_darwin"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            installer_main.install()

        signed = [str(c.args[0]) for c in mock_sign.call_args_list]
        assert len(signed) == 2
        assert str(tmp_path / "Desktop" / "MoleditPy.app") in signed
        assert str(tmp_path / "Applications" / "MoleditPy.app") in signed


# ---------------------------------------------------------------------------
# --check launch verification (macOS)
# ---------------------------------------------------------------------------


class TestCheckLaunchVerification:
    def _run_check(self, verify_ok):
        with (
            mock.patch("sys.argv", ["moleditpy-installer", "--check"]),
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch.object(
                installer_main, "find_executable", return_value="/env/bin/moleditpy"
            ),
            mock.patch.object(
                installer_main,
                "python_for_executable",
                return_value="/env/bin/python3",
            ),
            mock.patch.object(
                installer_main, "verify_launch_command", return_value=verify_ok
            ),
        ):
            return installer_main.main()

    def test_check_passes_when_launchable(self, capsys):
        assert self._run_check(True) == 0
        assert "Launch check: OK" in capsys.readouterr().out

    def test_check_fails_when_not_launchable(self, capsys):
        assert self._run_check(False) == 1
        assert "Launch check: FAILED" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# macOS document icon + app icon override fixes
# ---------------------------------------------------------------------------


class TestDarwinDocumentIcon:
    @pytest.fixture(autouse=True)
    def _isolate_persistent_dir(self, tmp_path):
        with mock.patch.object(
            installer_main,
            "get_persistent_data_dir",
            return_value=tmp_path / "persistent",
        ):
            (tmp_path / "persistent").mkdir(exist_ok=True)
            yield

    def test_file_icon_copied_and_referenced(self, tmp_path):
        """.pmeprj documents get their own icon (macOS counterpart of the
        Windows DefaultIcon registry value)."""
        import plistlib

        app_path = tmp_path / "MoleditPy.app"
        contents_path = app_path / "Contents"
        contents_path.mkdir(parents=True)
        with open(contents_path / "Info.plist", "wb") as fp:
            plistlib.dump({"CFBundleIdentifier": "com.moleditpy.launcher"}, fp)

        with mock.patch("platform.system", return_value="Darwin"):
            assert installer_main.register_file_associations_darwin(app_path) is True

        assert (contents_path / "Resources" / "file_icon.icns").exists()
        with open(contents_path / "Info.plist", "rb") as fp:
            pl = plistlib.load(fp)
        assert pl["CFBundleDocumentTypes"][0]["CFBundleTypeIconFile"] == (
            "file_icon.icns"
        )
        assert pl["UTExportedTypeDeclarations"][0]["UTTypeIconFile"] == (
            "file_icon.icns"
        )

    def test_falls_back_to_app_icon_when_extraction_fails(self, tmp_path):
        import plistlib

        app_path = tmp_path / "MoleditPy.app"
        contents_path = app_path / "Contents"
        contents_path.mkdir(parents=True)
        with open(contents_path / "Info.plist", "wb") as fp:
            plistlib.dump({}, fp)

        with (
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch.object(installer_main, "_extract_data_file", return_value=None),
        ):
            assert installer_main.register_file_associations_darwin(app_path) is True

        with open(contents_path / "Info.plist", "rb") as fp:
            pl = plistlib.load(fp)
        assert pl["CFBundleDocumentTypes"][0]["CFBundleTypeIconFile"] == "applet.icns"

    def test_packaged_file_icon_icns_is_valid(self):
        """The shipped file_icon.icns must be a real ICNS file."""
        import importlib.resources

        ref = (
            importlib.resources.files("moleditpy_installer") / "data" / "file_icon.icns"
        )
        header = ref.read_bytes()[:4]
        assert header == b"icns"


class TestDarwinAppIconOverride:
    def _install_with_fake_osacompile(self, tmp_path):
        import plistlib

        def fake_osacompile(cmd, **kwargs):
            app = Path(cmd[2])
            resources = app / "Contents" / "Resources"
            resources.mkdir(parents=True, exist_ok=False)
            # what modern osacompile actually produces
            (resources / "Assets.car").write_bytes(b"car")
            with open(app / "Contents" / "Info.plist", "wb") as fp:
                plistlib.dump({"CFBundleIconName": "applet"}, fp)

        with (
            mock.patch.object(
                installer_main, "find_executable", return_value=str(tmp_path / "m")
            ),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "python_for_executable", return_value=sys.executable
            ),
            mock.patch.object(
                installer_main, "verify_launch_command", return_value=True
            ),
            mock.patch.object(installer_main, "refresh_launch_services"),
            mock.patch.object(installer_main, "codesign_app"),
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch("subprocess.run", side_effect=fake_osacompile),
            mock.patch("moleditpy_installer.main.register_file_associations_darwin"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            assert installer_main.install() == 0

        return tmp_path / "Desktop" / "MoleditPy.app"

    def test_assets_car_and_iconname_removed(self, tmp_path):
        """Assets.car / CFBundleIconName would override applet.icns, so the
        custom icon was silently ignored — both must be stripped."""
        import plistlib

        app = self._install_with_fake_osacompile(tmp_path)

        assert not (app / "Contents" / "Resources" / "Assets.car").exists()
        with open(app / "Contents" / "Info.plist", "rb") as fp:
            pl = plistlib.load(fp)
        assert "CFBundleIconName" not in pl
        assert pl["CFBundleIdentifier"] == "com.moleditpy.launcher"
        # Version stamped so Launch Services drops its cached icon
        assert pl["CFBundleVersion"] == installer_main.get_installer_version()

    def test_stale_desktop_bundle_replaced(self, tmp_path):
        """osacompile -o into an existing .app keeps leftovers — the old
        bundle must be removed first (fake osacompile uses exist_ok=False,
        so this would raise if it were not)."""
        stale = tmp_path / "Desktop" / "MoleditPy.app" / "Contents"
        stale.mkdir(parents=True)
        (stale / "stale-marker").write_bytes(b"old")

        app = self._install_with_fake_osacompile(tmp_path)

        assert not (app / "Contents" / "stale-marker").exists()
