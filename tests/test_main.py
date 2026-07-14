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
    m.HKEY_LOCAL_MACHINE = 0x80000002
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
            mock.patch("sysconfig.get_path", side_effect=KeyError("mocked error")),
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
            mock.patch("sysconfig.get_path", side_effect=KeyError("mocked error")),
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
            mock.patch("sysconfig.get_path", side_effect=KeyError("mocked error")),
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
            mock.patch("sysconfig.get_path", side_effect=KeyError("mocked error")),
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
            mock.patch("sysconfig.get_path", side_effect=KeyError("mocked error")),
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

    def test_returns_none_when_file_missing_in_package(self):
        """A data file missing from the package must return None."""
        fake_ref = mock.MagicMock()
        fake_ref.__truediv__ = mock.Mock(return_value=fake_ref)
        fake_ref.read_bytes = mock.Mock(side_effect=FileNotFoundError("icon.ico"))

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("importlib.resources.files", return_value=fake_ref),
        ):
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
        deleted = [c.args[1] for c in mock_del.call_args_list]
        assert "Software\Classes\MoleditPy.File" in deleted
        # Explorer's per-user FileExts cache must be cleared too, or the
        # association looks still present after uninstall
        assert (
            "Software\Microsoft\Windows\CurrentVersion\\Explorer\FileExts\.pmeprj"
        ) in deleted

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
            installer_main.install(installer_main.InstallOptions(desktop=True))

        mock_shortcut.assert_called_once()
        _, kwargs = mock_shortcut.call_args
        assert kwargs.get("startmenu") is True
        assert kwargs.get("desktop") is True

    def test_install_defaults_skip_desktop(self, tmp_path):
        """v3 defaults: app menu on, Desktop shortcut off."""
        fake_exe = str(tmp_path / "moleditpy.exe")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(installer_main, "get_file_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "register_file_associations_windows", return_value=True
            ) as mock_assoc,
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("moleditpy_installer.main.make_shortcut") as mock_shortcut,
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            assert installer_main.install() == 0

        _, kwargs = mock_shortcut.call_args
        assert kwargs.get("startmenu") is True
        assert kwargs.get("desktop") is False
        mock_assoc.assert_called_once()

    def test_install_calls_make_shortcut_on_linux(self, tmp_path):
        fake_exe = str(tmp_path / "moleditpy")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(installer_main, "register_file_associations_linux"),
            mock.patch("platform.system", return_value="Linux"),
            mock.patch("moleditpy_installer.main.make_shortcut") as mock_shortcut,
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            installer_main.install(installer_main.InstallOptions(desktop=True))

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
            mock.patch(
                "subprocess.run", return_value=mock.Mock(returncode=0, stderr=b"")
            ) as mock_run,
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
            mock.patch(
                "subprocess.run", return_value=mock.Mock(returncode=0, stderr=b"")
            ) as mock_run,
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
            mock.patch(
                "subprocess.run", return_value=mock.Mock(returncode=0, stderr=b"")
            ) as mock_run,
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
            return mock.Mock(returncode=0, stderr=b"")

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
            mock.patch.object(installer_main, "register_file_associations_linux"),
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
        from importlib.metadata import PackageNotFoundError

        with (
            mock.patch("importlib.metadata.version", side_effect=PackageNotFoundError),
            mock.patch("pathlib.Path.exists", return_value=False),
        ):
            assert installer_main.get_installer_version() == "unknown"

    def test_get_installer_version_from_pyproject(self):
        # Test reading from pyproject.toml when metadata fails
        from importlib.metadata import PackageNotFoundError

        with (
            mock.patch("importlib.metadata.version", side_effect=PackageNotFoundError),
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
            return mock.Mock(returncode=0, stderr=b"")

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
            installer_main.install(installer_main.InstallOptions(desktop=True))

        signed = [str(c.args[0]) for c in mock_sign.call_args_list]
        # build bundle + each destination copy
        assert len(signed) == 3
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
            # exist_ok=False: the scratch build dir must always be fresh
            app = Path(cmd[2])
            resources = app / "Contents" / "Resources"
            resources.mkdir(parents=True, exist_ok=False)
            # what modern osacompile actually produces
            (resources / "Assets.car").write_bytes(b"car")
            with open(app / "Contents" / "Info.plist", "wb") as fp:
                plistlib.dump({"CFBundleIconName": "applet"}, fp)
            return mock.Mock(returncode=0, stderr=b"")

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
            assert (
                installer_main.install(installer_main.InstallOptions(desktop=True)) == 0
            )

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
        """An existing destination bundle must be fully replaced, not
        merged into (leftover files would keep stale icons/doc types)."""
        stale = tmp_path / "Desktop" / "MoleditPy.app" / "Contents"
        stale.mkdir(parents=True)
        (stale / "stale-marker").write_bytes(b"old")

        app = self._install_with_fake_osacompile(tmp_path)

        assert app.exists()
        assert not (app / "Contents" / "stale-marker").exists()


# ---------------------------------------------------------------------------
# Linux file associations
# ---------------------------------------------------------------------------


class TestLinuxFileAssociations:
    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path):
        persistent = tmp_path / "persistent"
        persistent.mkdir()
        with (
            mock.patch.object(
                installer_main, "get_persistent_data_dir", return_value=persistent
            ),
            mock.patch.object(installer_main, "_run_quiet", return_value=True),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
        ):
            yield

    def test_returns_false_on_non_linux(self):
        with mock.patch("platform.system", return_value="Windows"):
            assert installer_main.register_file_associations_linux() is False

    def test_registers_mime_type_and_icon(self, tmp_path):
        with mock.patch("platform.system", return_value="Linux"):
            assert installer_main.register_file_associations_linux() is True

        mime_xml = tmp_path / ".local" / "share" / "mime" / "packages" / "moleditpy.xml"
        assert mime_xml.exists()
        content = mime_xml.read_text(encoding="utf-8")
        assert 'type="application/x-moleditpy-project"' in content
        assert 'pattern="*.pmeprj"' in content

        icon = (
            tmp_path
            / ".local"
            / "share"
            / "icons"
            / "hicolor"
            / "256x256"
            / "mimetypes"
            / "application-x-moleditpy-project.png"
        )
        assert icon.exists()
        assert icon.read_bytes()[:4] == b"\x89PNG"

    def test_sets_default_handler(self, tmp_path):
        with mock.patch("platform.system", return_value="Linux"):
            installer_main.register_file_associations_linux()

        run_quiet_calls = [c.args[0] for c in installer_main._run_quiet.call_args_list]
        assert [
            "xdg-mime",
            "default",
            "MoleditPy.desktop",
            "application/x-moleditpy-project",
        ] in run_quiet_calls

    def test_unregister_removes_files(self, tmp_path):
        with mock.patch("platform.system", return_value="Linux"):
            installer_main.register_file_associations_linux()
            installer_main.unregister_file_associations_linux()

        assert not (
            tmp_path / ".local" / "share" / "mime" / "packages" / "moleditpy.xml"
        ).exists()
        assert not (
            tmp_path
            / ".local"
            / "share"
            / "icons"
            / "hicolor"
            / "256x256"
            / "mimetypes"
            / "application-x-moleditpy-project.png"
        ).exists()

    def test_packaged_file_icon_png_is_valid(self):
        import importlib.resources

        ref = (
            importlib.resources.files("moleditpy_installer") / "data" / "file_icon.png"
        )
        assert ref.read_bytes()[:4] == b"\x89PNG"


class TestPatchLinuxDesktopEntry:
    def test_patches_terminal_mimetype_and_exec(self, tmp_path):
        desktop = tmp_path / "MoleditPy.desktop"
        desktop.write_text(
            "[Desktop Entry]\n"
            "Name=MoleditPy\n"
            "Exec=/usr/bin/moleditpy\n"
            "Terminal=false\n",
            encoding="utf-8",
        )

        assert installer_main._patch_linux_desktop_entry(desktop) is True
        lines = desktop.read_text(encoding="utf-8").splitlines()
        assert "Terminal=true" in lines
        assert "Terminal=false" not in lines
        assert "MimeType=application/x-moleditpy-project;" in lines
        assert "Exec=/usr/bin/moleditpy %f" in lines

    def test_idempotent(self, tmp_path):
        desktop = tmp_path / "MoleditPy.desktop"
        desktop.write_text(
            "[Desktop Entry]\nExec=/usr/bin/moleditpy %f\nTerminal=true\n",
            encoding="utf-8",
        )

        installer_main._patch_linux_desktop_entry(desktop)
        installer_main._patch_linux_desktop_entry(desktop)
        lines = desktop.read_text(encoding="utf-8").splitlines()
        assert lines.count("MimeType=application/x-moleditpy-project;") == 1
        assert lines.count("Terminal=true") == 1
        assert lines.count("Exec=/usr/bin/moleditpy %f") == 1

    def test_returns_false_when_missing(self, tmp_path):
        assert (
            installer_main._patch_linux_desktop_entry(tmp_path / "nope.desktop")
            is False
        )

    def test_install_linux_registers_associations(self, tmp_path):
        fake_exe = str(tmp_path / "moleditpy")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "register_file_associations_linux"
            ) as mock_reg,
            mock.patch("platform.system", return_value="Linux"),
            mock.patch("moleditpy_installer.main.make_shortcut"),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            assert installer_main.install() == 0

        mock_reg.assert_called_once()


# ---------------------------------------------------------------------------
# System-wide conda search paths
# ---------------------------------------------------------------------------


class TestSystemCondaSearch:
    def test_finds_exe_in_system_conda_root(self, tmp_path):
        """/opt/miniconda3-style installs must be searched explicitly."""
        conda_root = tmp_path / "opt_conda"
        (conda_root / "bin").mkdir(parents=True)
        with mock.patch("platform.system", return_value="Linux"):
            _make_fake_exe(conda_root / "bin", "moleditpy")

            with (
                mock.patch.object(installer_main, "_SYSTEM_CONDA_ROOTS", [conda_root]),
                mock.patch.object(
                    installer_main.sys, "executable", str(tmp_path / "py" / "python")
                ),
                mock.patch.object(
                    installer_main.sys, "argv", [str(tmp_path / "py" / "x.py")]
                ),
                mock.patch("shutil.which", return_value=None),
                mock.patch("pathlib.Path.home", return_value=tmp_path / "home"),
            ):
                result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "opt_conda" in result

    def test_finds_exe_in_system_conda_env(self, tmp_path):
        conda_root = tmp_path / "opt_conda"
        env_bin = conda_root / "envs" / "chem" / "bin"
        env_bin.mkdir(parents=True)
        with mock.patch("platform.system", return_value="Linux"):
            _make_fake_exe(env_bin, "moleditpy")

            with (
                mock.patch.object(installer_main, "_SYSTEM_CONDA_ROOTS", [conda_root]),
                mock.patch.object(
                    installer_main.sys, "executable", str(tmp_path / "py" / "python")
                ),
                mock.patch.object(
                    installer_main.sys, "argv", [str(tmp_path / "py" / "x.py")]
                ),
                mock.patch("shutil.which", return_value=None),
                mock.patch("pathlib.Path.home", return_value=tmp_path / "home"),
            ):
                result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "chem" in result


class TestDarwinDocTypeReplacement:
    def test_replaces_applet_default_doc_types(self, tmp_path):
        """osacompile applets ship a default document type; the launcher
        must claim ONLY .pmeprj, so registration replaces the list."""
        import plistlib

        app_path = tmp_path / "MoleditPy.app"
        contents_path = app_path / "Contents"
        contents_path.mkdir(parents=True)
        plist_path = contents_path / "Info.plist"
        with open(plist_path, "wb") as fp:
            plistlib.dump(
                {
                    "CFBundleDocumentTypes": [
                        {
                            "CFBundleTypeExtensions": ["*"],
                            "CFBundleTypeName": "Applet Default",
                        }
                    ]
                },
                fp,
            )

        with (
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch.object(installer_main, "_extract_data_file", return_value=None),
        ):
            assert installer_main.register_file_associations_darwin(app_path) is True

        with open(plist_path, "rb") as fp:
            pl = plistlib.load(fp)
        doc_types = pl["CFBundleDocumentTypes"]
        assert len(doc_types) == 1
        assert doc_types[0]["CFBundleTypeExtensions"] == ["pmeprj"]


# ---------------------------------------------------------------------------
# InstallOptions / scope handling (v3)
# ---------------------------------------------------------------------------


class TestInstallOptions:
    def test_all_disabled_is_an_error(self, capsys):
        result = installer_main.install(
            installer_main.InstallOptions(
                desktop=False, app_menu=False, file_assoc=False
            )
        )
        assert result == 1
        assert "Nothing to install" in capsys.readouterr().out

    def test_system_scope_needs_admin_on_windows(self, capsys):
        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(installer_main, "is_root", return_value=False),
        ):
            result = installer_main.install(installer_main.InstallOptions(system=True))
        assert result == 1
        assert "elevated" in capsys.readouterr().out

    def test_windows_system_scope_registers_hklm_and_moves_shortcuts(self, tmp_path):
        fake_exe = str(tmp_path / "moleditpy.exe")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(installer_main, "get_file_icon_path", return_value=None),
            mock.patch.object(installer_main, "is_root", return_value=True),
            mock.patch.object(
                installer_main, "register_file_associations_windows", return_value=True
            ) as mock_assoc,
            mock.patch.object(
                installer_main, "_move_windows_shortcuts_to_all_users"
            ) as mock_move,
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("moleditpy_installer.main.make_shortcut"),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            result = installer_main.install(installer_main.InstallOptions(system=True))

        assert result == 0
        mock_move.assert_called_once_with(False, True)
        assert mock_assoc.call_args.kwargs.get("system") is True

    def test_system_scope_requires_root(self, capsys):
        with (
            mock.patch("platform.system", return_value="Linux"),
            mock.patch.object(installer_main, "is_root", return_value=False),
        ):
            result = installer_main.install(installer_main.InstallOptions(system=True))
        assert result == 1
        assert "root" in capsys.readouterr().out

    def test_file_assoc_only_on_windows(self, tmp_path):
        """file association without any shortcut is valid on Windows."""
        fake_exe = str(tmp_path / "moleditpy.exe")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(installer_main, "get_file_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "register_file_associations_windows", return_value=True
            ) as mock_assoc,
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("moleditpy_installer.main.make_shortcut") as mock_shortcut,
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            result = installer_main.install(
                installer_main.InstallOptions(desktop=False, app_menu=False)
            )

        assert result == 0
        mock_shortcut.assert_not_called()
        mock_assoc.assert_called_once()

    def test_no_file_assoc_skips_registration_on_windows(self, tmp_path):
        fake_exe = str(tmp_path / "moleditpy.exe")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "register_file_associations_windows"
            ) as mock_assoc,
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("moleditpy_installer.main.make_shortcut"),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            result = installer_main.install(
                installer_main.InstallOptions(file_assoc=False)
            )

        assert result == 0
        mock_assoc.assert_not_called()

    def test_darwin_requires_a_bundle_destination(self, tmp_path, capsys):
        fake_exe = str(tmp_path / "moleditpy")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            result = installer_main.install(
                installer_main.InstallOptions(desktop=False, app_menu=False)
            )

        assert result == 1
        assert "bundle" in capsys.readouterr().out

    def test_linux_system_scope_writes_system_desktop_entry(self, tmp_path):
        fake_exe = str(tmp_path / "moleditpy")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(installer_main, "is_root", return_value=True),
            mock.patch.object(
                installer_main, "write_linux_system_desktop_entry", return_value=True
            ) as mock_entry,
            mock.patch.object(
                installer_main, "register_file_associations_linux", return_value=True
            ) as mock_assoc,
            mock.patch("platform.system", return_value="Linux"),
            mock.patch("moleditpy_installer.main.make_shortcut") as mock_shortcut,
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            result = installer_main.install(installer_main.InstallOptions(system=True))

        assert result == 0
        mock_entry.assert_called_once()
        mock_shortcut.assert_not_called()
        mock_assoc.assert_called_once_with(system=True)


class TestLinuxSystemDesktopEntry:
    def test_writes_entry(self, tmp_path):
        with (
            mock.patch.object(
                installer_main, "linux_data_home", return_value=tmp_path / "usr_share"
            ),
            mock.patch.object(installer_main, "_run_quiet", return_value=True),
        ):
            exe = "/opt/conda/bin/moleditpy"
            assert (
                installer_main.write_linux_system_desktop_entry(
                    exe, "/usr/share/icons/moleditpy.png"
                )
                is True
            )

        entry = tmp_path / "usr_share" / "applications" / "MoleditPy.desktop"
        content = entry.read_text(encoding="utf-8")
        assert "Exec=/opt/conda/bin/moleditpy %f" in content
        assert "Terminal=true" in content
        assert "MimeType=application/x-moleditpy-project;" in content
        assert "Icon=/usr/share/icons/moleditpy.png" in content


class TestLinuxDataHome:
    def test_honors_xdg_data_home(self, tmp_path):
        with mock.patch.dict(
            os.environ, {"XDG_DATA_HOME": str(tmp_path / "xdg")}, clear=False
        ):
            assert installer_main.linux_data_home() == tmp_path / "xdg"

    def test_system_scope_is_usr_share(self):
        assert installer_main.linux_data_home(system=True) == Path("/usr/share")


class TestRemoveSystemScope:
    def test_darwin_system_scope_targets_applications(self, tmp_path):
        with (
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch.object(installer_main, "refresh_launch_services"),
            mock.patch.object(
                installer_main,
                "get_persistent_data_dir",
                return_value=tmp_path / "persistent",
            ),
            mock.patch("shutil.rmtree") as mock_rmtree,
            mock.patch("pathlib.Path.exists", return_value=True),
            mock.patch("pathlib.Path.is_dir", return_value=True),
        ):
            installer_main.remove_shortcut(system_scope=True)

        removed = {str(c.args[0]) for c in mock_rmtree.call_args_list}
        assert str(Path("/Applications") / "MoleditPy.app") in removed


# ---------------------------------------------------------------------------
# TUI (textual)
# ---------------------------------------------------------------------------

try:
    import textual  # noqa: F401

    HAS_TEXTUAL = True
except ImportError:
    HAS_TEXTUAL = False


@pytest.mark.skipif(not HAS_TEXTUAL, reason="textual is not installed")
class TestTui:
    def test_defaults_match_spec(self):
        """TUI defaults: desktop off, app menu on, file assoc on, user scope."""
        import asyncio

        from moleditpy_installer.tui import InstallerApp

        async def check():
            app = InstallerApp()
            async with app.run_test() as pilot:
                from textual.widgets import Checkbox, RadioButton

                assert app.query_one("#desktop", Checkbox).value is False
                assert app.query_one("#app_menu", Checkbox).value is True
                assert app.query_one("#file_assoc", Checkbox).value is True
                assert app.query_one("#scope_user", RadioButton).value is True
                assert app.query_one("#scope_system", RadioButton).value is False
                assert app._selected_options() == installer_main.InstallOptions()
                await pilot.pause()

        asyncio.run(check())

    def test_install_button_runs_install(self):
        import asyncio

        from moleditpy_installer.tui import InstallerApp

        async def check():
            app = InstallerApp()
            with mock.patch.object(
                installer_main, "install", return_value=0
            ) as mock_install:
                async with app.run_test() as pilot:
                    await pilot.pause()
                    from textual.widgets import Button

                    app.query_one("#install", Button).press()
                    for _ in range(100):
                        await pilot.pause(0.05)
                        if mock_install.called:
                            break
            assert mock_install.called
            assert mock_install.call_args.args[0] == installer_main.InstallOptions()
            # success auto-exits the TUI
            assert app.return_value == 0

        asyncio.run(check())


# ---------------------------------------------------------------------------
# v3.0.1 bug-fix and coverage tests
# ---------------------------------------------------------------------------


class TestV301Fixes:
    def test_system_desktop_entry_quotes_spaces(self, tmp_path):
        """An Exec path with spaces must be quoted or the desktop-entry
        spec splits the command at the space."""
        with (
            mock.patch.object(installer_main, "linux_data_home", return_value=tmp_path),
            mock.patch.object(installer_main, "_run_quiet", return_value=True),
        ):
            assert (
                installer_main.write_linux_system_desktop_entry(
                    "/opt/my conda/bin/moleditpy", None
                )
                is True
            )

        content = (tmp_path / "applications" / "MoleditPy.desktop").read_text(
            encoding="utf-8"
        )
        assert 'Exec="/opt/my conda/bin/moleditpy" %f' in content

    def test_system_desktop_entry_write_failure(self, tmp_path, capsys):
        with (
            mock.patch.object(installer_main, "linux_data_home", return_value=tmp_path),
            mock.patch.object(Path, "write_text", side_effect=OSError("denied")),
        ):
            assert (
                installer_main.write_linux_system_desktop_entry("/bin/m", None) is False
            )
        assert "Failed to write system desktop entry" in capsys.readouterr().out

    def test_remove_system_scope_warns_without_root(self, tmp_path, capsys):
        with (
            mock.patch("platform.system", return_value="Linux"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch.object(installer_main, "is_root", return_value=False),
            mock.patch.object(installer_main, "unregister_file_associations_linux"),
            mock.patch.object(
                installer_main,
                "get_persistent_data_dir",
                return_value=tmp_path / "persistent",
            ),
        ):
            installer_main.remove_shortcut(system_scope=True)

        out = capsys.readouterr().out
        assert "requires root" in out

    def test_run_quiet_missing_tool_returns_false(self):
        assert installer_main._run_quiet(["definitely-not-a-real-tool-xyz"]) is False

    def test_patch_desktop_entry_write_failure(self, tmp_path, capsys):
        desktop = tmp_path / "MoleditPy.desktop"
        desktop.write_text("[Desktop Entry]\nExec=/bin/m\n", encoding="utf-8")

        with mock.patch.object(Path, "write_text", side_effect=OSError("denied")):
            assert installer_main._patch_linux_desktop_entry(desktop) is False
        assert "could not update" in capsys.readouterr().out

    def test_refresh_launch_services_warns_on_subprocess_error(self, tmp_path, capsys):
        app = tmp_path / "MoleditPy.app"
        app.mkdir()

        with (
            mock.patch("pathlib.Path.exists", return_value=True),
            mock.patch("subprocess.run", side_effect=OSError("boom")),
        ):
            installer_main.refresh_launch_services(app)

        assert "Launch Services refresh failed" in capsys.readouterr().out

    def test_darwin_osacompile_failure_returns_1(self, tmp_path, capsys):
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
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch(
                "subprocess.run",
                return_value=mock.Mock(returncode=1, stderr=b"syntax error"),
            ),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            result = installer_main.install()

        assert result == 1
        out = capsys.readouterr().out
        assert "osacompile failed" in out
        assert "syntax error" in out

    def test_darwin_unverifiable_pairing_warns_but_proceeds(self, tmp_path, capsys):
        fake_exe = str(tmp_path / "moleditpy")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(
                installer_main, "python_for_executable", return_value=sys.executable
            ),
            mock.patch.object(
                installer_main, "verify_launch_command", return_value=False
            ),
            mock.patch.object(installer_main, "refresh_launch_services"),
            mock.patch.object(installer_main, "codesign_app"),
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch(
                "subprocess.run", return_value=mock.Mock(returncode=0, stderr=b"")
            ),
            mock.patch("shutil.copytree"),
            mock.patch("moleditpy_installer.main.register_file_associations_darwin"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            installer_main.install()

        assert "could not verify" in capsys.readouterr().out

    def test_linux_system_note_when_desktop_requested(self, tmp_path, capsys):
        fake_exe = str(tmp_path / "moleditpy")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch.object(installer_main, "is_root", return_value=True),
            mock.patch.object(
                installer_main, "write_linux_system_desktop_entry", return_value=True
            ),
            mock.patch.object(
                installer_main, "register_file_associations_linux", return_value=True
            ),
            mock.patch("platform.system", return_value="Linux"),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            result = installer_main.install(
                installer_main.InstallOptions(system=True, desktop=True)
            )

        assert result == 0
        assert "per-user" in capsys.readouterr().out


class TestMainDispatch:
    def test_main_dispatches_to_tui(self):
        with (
            mock.patch("sys.argv", ["moleditpy-installer"]),
            mock.patch.object(installer_main, "_tui_available", return_value=True),
            mock.patch("moleditpy_installer.tui.run_tui", return_value=0) as mock_tui,
        ):
            assert installer_main.main() == 0
        mock_tui.assert_called_once()

    def test_main_no_tui_flag_installs_directly(self):
        with (
            mock.patch("sys.argv", ["moleditpy-installer", "--no-tui"]),
            mock.patch.object(installer_main, "_tui_available", return_value=True),
            mock.patch.object(installer_main, "install", return_value=0) as mock_i,
        ):
            assert installer_main.main() == 0
        mock_i.assert_called_once_with(installer_main.InstallOptions())

    def test_main_explicit_flags_skip_tui_and_build_options(self):
        with (
            mock.patch(
                "sys.argv",
                ["moleditpy-installer", "--desktop", "--no-file-assoc"],
            ),
            mock.patch.object(installer_main, "_tui_available", return_value=True),
            mock.patch.object(installer_main, "install", return_value=0) as mock_i,
        ):
            assert installer_main.main() == 0
        mock_i.assert_called_once_with(
            installer_main.InstallOptions(
                desktop=True, app_menu=True, file_assoc=False, system=False
            )
        )

    def test_main_uninstall_passes_system_scope(self):
        with (
            mock.patch("sys.argv", ["moleditpy-installer", "--uninstall", "--system"]),
            mock.patch.object(installer_main, "remove_shortcut") as mock_remove,
        ):
            assert installer_main.main() == 0
        mock_remove.assert_called_once_with(system_scope=True)

    def test_main_remove_is_a_compatible_alias(self):
        with (
            mock.patch("sys.argv", ["moleditpy-installer", "--remove"]),
            mock.patch.object(installer_main, "remove_shortcut") as mock_remove,
        ):
            assert installer_main.main() == 0
        mock_remove.assert_called_once_with(system_scope=False)

    def test_tui_available_false_without_tty(self):
        with mock.patch.object(sys.stdin, "isatty", return_value=False):
            assert installer_main._tui_available() is False


@pytest.mark.skipif(not HAS_TEXTUAL, reason="textual is not installed")
class TestTuiActions:
    def _run(self, coro):
        import asyncio

        asyncio.run(coro)

    def test_remove_button_runs_remove(self):
        from moleditpy_installer.tui import InstallerApp

        async def check():
            app = InstallerApp()
            with mock.patch.object(
                installer_main, "remove_shortcut", return_value=None
            ) as mock_remove:
                async with app.run_test() as pilot:
                    await pilot.pause()
                    from textual.widgets import Button

                    app.query_one("#remove", Button).press()
                    for _ in range(100):
                        await pilot.pause(0.05)
                        if mock_remove.called:
                            break
            assert mock_remove.called
            assert mock_remove.call_args.kwargs == {"system_scope": False}
            assert app.exit_code == 0

        self._run(check())

    def test_failed_install_sets_exit_code(self):
        from moleditpy_installer.tui import InstallerApp

        async def check():
            app = InstallerApp()
            with mock.patch.object(installer_main, "install", return_value=1):
                async with app.run_test() as pilot:
                    await pilot.pause()
                    from textual.widgets import Button

                    app.query_one("#install", Button).press()
                    for _ in range(100):
                        await pilot.pause(0.05)
                        if app.exit_code == 1:
                            break
            assert app.exit_code == 1

        self._run(check())

    def test_exception_in_action_is_logged_not_raised(self):
        from moleditpy_installer.tui import InstallerApp

        async def check():
            app = InstallerApp()
            with mock.patch.object(
                installer_main, "install", side_effect=RuntimeError("kaboom")
            ):
                async with app.run_test() as pilot:
                    await pilot.pause()
                    from textual.widgets import Button

                    app.query_one("#install", Button).press()
                    for _ in range(100):
                        await pilot.pause(0.05)
                        if app.exit_code == 1:
                            break
            assert app.exit_code == 1

        self._run(check())

    def test_quit_button_exits_with_code(self):
        from moleditpy_installer.tui import InstallerApp

        async def check():
            app = InstallerApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                from textual.widgets import Button

                app.query_one("#quit", Button).press()
                await pilot.pause()
            assert app.return_value == 0

        self._run(check())

    def test_log_writer_forwards_lines(self):
        from moleditpy_installer.tui import _LogWriter

        class FakeApp:
            def __init__(self):
                self.lines = []

            def call_from_thread(self, fn, *args):
                fn(*args)

            def log_line(self, line):
                self.lines.append(line)

        app = FakeApp()
        writer = _LogWriter(app)
        writer.write("hello\nwor")
        writer.write("ld\n")
        writer.write("tail")
        writer.flush()
        assert app.lines == ["hello", "world", "tail"]

    def test_mouse_click_reaches_buttons_at_80x24(self):
        """Regression: on a standard 80x24 terminal the buttons were pushed
        below the fold by the tall layout, so mouse clicks never reached
        them (only the key bindings worked)."""
        import asyncio

        from moleditpy_installer.tui import InstallerApp

        async def check():
            app = InstallerApp()
            with mock.patch.object(
                installer_main, "install", return_value=0
            ) as mock_install:
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause()
                    button = app.query_one("#install")
                    # the whole button must be inside the visible screen
                    assert button.region.y + button.region.height <= 24, (
                        f"Install button out of view: {button.region}"
                    )
                    clicked = await pilot.click("#install")
                    assert clicked
                    for _ in range(100):
                        await pilot.pause(0.05)
                        if mock_install.called:
                            break
            assert mock_install.called

        asyncio.run(check())

    def test_run_tui_returns_int(self):
        from moleditpy_installer import tui

        with mock.patch.object(tui.InstallerApp, "run", return_value=None):
            assert tui.run_tui() == 0
        with mock.patch.object(tui.InstallerApp, "run", return_value=3):
            assert tui.run_tui() == 3

    def test_run_tui_replays_log_to_terminal(self, capsys):
        from moleditpy_installer import tui

        def fake_run(self):
            self._history.extend(["line one", "line two"])
            return 0

        with mock.patch.object(tui.InstallerApp, "run", fake_run):
            assert tui.run_tui() == 0

        out = capsys.readouterr().out
        assert "MoleditPy installer log:" in out
        assert "line one" in out
        assert "line two" in out
        assert "Result: success" in out

    def test_run_tui_prints_failure_result(self, capsys):
        from moleditpy_installer import tui

        with mock.patch.object(tui.InstallerApp, "run", return_value=1):
            assert tui.run_tui() == 1
        assert "FAILED (exit code 1)" in capsys.readouterr().out

    def test_status_bar_visible_and_updated(self):
        import asyncio

        from moleditpy_installer.tui import InstallerApp

        async def check():
            app = InstallerApp()
            async with app.run_test() as pilot:
                from textual.widgets import Static

                status = app.query_one("#status", Static)
                assert status.display  # the bar is shown
                # detection worker fills it in
                for _ in range(100):
                    await pilot.pause(0.05)
                    if "moleditpy" in str(status.render()):
                        break
                assert "moleditpy" in str(status.render())

        asyncio.run(check())

    def test_failure_keeps_tui_open_for_retry(self):
        import asyncio

        from moleditpy_installer.tui import InstallerApp

        async def check():
            app = InstallerApp()
            with mock.patch.object(installer_main, "install", return_value=1):
                async with app.run_test() as pilot:
                    await pilot.pause()
                    from textual.widgets import Button

                    app.query_one("#install", Button).press()
                    for _ in range(100):
                        await pilot.pause(0.05)
                        if app.exit_code == 1:
                            break
                    await pilot.pause()
                    # app did NOT exit; buttons re-enabled for a retry
                    assert app.return_value is None
                    assert app.query_one("#install", Button).disabled is False

        asyncio.run(check())


# ---------------------------------------------------------------------------
# v3.0.3: COM guard, Explorer refresh, mimeapps cleanup, Windows system scope
# ---------------------------------------------------------------------------


class TestComInitialized:
    def test_noop_off_windows(self):
        with mock.patch("platform.system", return_value="Linux"):
            with installer_main._com_initialized():
                pass  # must not raise nor import pythoncom

    @pytest.mark.skipif(
        platform.system() != "Windows", reason="COM only exists on Windows"
    )
    def test_com_usable_in_worker_thread(self):
        """Regression: TUI installs run in a worker thread where COM is not
        initialized — pyshortcuts then fails with CO_E_NOTINITIALIZED."""
        import threading

        errors = []

        def worker():
            try:
                from win32com.client import Dispatch

                with installer_main._com_initialized():
                    Dispatch("WScript.Shell")
            except Exception as e:  # pragma: no cover - failure detail
                errors.append(e)

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert not errors


class TestWindowsAssocRefresh:
    def test_register_notifies_explorer(self, tmp_path):
        fake_winreg = _make_winreg_mock()
        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(installer_main, "winreg", fake_winreg),
            mock.patch.object(
                installer_main, "_notify_windows_assoc_changed"
            ) as mock_notify,
        ):
            assert (
                installer_main.register_file_associations_windows(
                    str(tmp_path / "moleditpy.exe"), None
                )
                is True
            )
        mock_notify.assert_called_once()

    def test_unregister_notifies_explorer(self):
        fake_winreg = _make_winreg_mock()
        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(installer_main, "winreg", fake_winreg),
            mock.patch.object(installer_main, "delete_registry_tree"),
            mock.patch.object(
                installer_main, "_notify_windows_assoc_changed"
            ) as mock_notify,
        ):
            installer_main.unregister_file_associations_windows()
        mock_notify.assert_called_once()

    def test_system_scope_uses_hklm(self, tmp_path):
        fake_winreg = _make_winreg_mock()
        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch.object(installer_main, "winreg", fake_winreg),
            mock.patch.object(installer_main, "_notify_windows_assoc_changed"),
        ):
            installer_main.register_file_associations_windows(
                str(tmp_path / "moleditpy.exe"), None, system=True
            )
        roots = {c.args[0] for c in fake_winreg.CreateKey.call_args_list}
        assert roots == {fake_winreg.HKEY_LOCAL_MACHINE}

    def test_notify_helper_never_raises(self):
        # cross-platform: on Windows fires SHChangeNotify, elsewhere no-op
        installer_main._notify_windows_assoc_changed()


class TestCleanLinuxMimeapps:
    def test_removes_only_our_entries(self, tmp_path):
        config = tmp_path / ".config"
        config.mkdir()
        mimeapps = config / "mimeapps.list"
        mimeapps.write_text(
            "[Default Applications]\n"
            "application/x-moleditpy-project=MoleditPy.desktop;\n"
            "text/plain=gedit.desktop;\n",
            encoding="utf-8",
        )

        with (
            mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(config)}, clear=False),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
        ):
            installer_main._clean_linux_mimeapps()

        content = mimeapps.read_text(encoding="utf-8")
        assert "moleditpy" not in content
        assert "text/plain=gedit.desktop;" in content

    def test_silent_when_files_missing(self, tmp_path):
        with (
            mock.patch.dict(
                os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}, clear=False
            ),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
        ):
            installer_main._clean_linux_mimeapps()  # must not raise


class TestWindowsSystemRemove:
    def test_windows_system_scope_warns_without_admin(self, tmp_path, capsys):
        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(installer_main, "is_root", return_value=False),
            mock.patch.object(installer_main, "unregister_file_associations_windows"),
            mock.patch.object(
                installer_main,
                "get_persistent_data_dir",
                return_value=tmp_path / "persistent",
            ),
        ):
            installer_main.remove_shortcut(system_scope=True)

        assert "administrator" in capsys.readouterr().out

    def test_windows_system_scope_targets_all_users_paths(self, tmp_path):
        env = {
            "PROGRAMDATA": str(tmp_path / "ProgramData"),
            "PUBLIC": str(tmp_path / "Public"),
        }
        pd_lnk = tmp_path / "ProgramData/Microsoft/Windows/Start Menu/Programs"
        pd_lnk.mkdir(parents=True)
        (pd_lnk / "MoleditPy.lnk").write_bytes(b"x")
        (tmp_path / "Public/Desktop").mkdir(parents=True)
        (tmp_path / "Public/Desktop/MoleditPy.lnk").write_bytes(b"x")

        with (
            mock.patch("platform.system", return_value="Windows"),
            mock.patch("pathlib.Path.home", return_value=tmp_path),
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(installer_main, "is_root", return_value=True),
            mock.patch.object(
                installer_main, "unregister_file_associations_windows"
            ) as mock_unreg,
            mock.patch.object(
                installer_main,
                "get_persistent_data_dir",
                return_value=tmp_path / "persistent",
            ),
        ):
            installer_main.remove_shortcut(system_scope=True)

        assert not (pd_lnk / "MoleditPy.lnk").exists()
        assert not (tmp_path / "Public/Desktop/MoleditPy.lnk").exists()
        # user-level AND system-level (HKLM) registrations removed
        assert mock.call(system=True) in mock_unreg.call_args_list
