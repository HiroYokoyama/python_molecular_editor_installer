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

        with mock.patch.object(installer_main.sys, "executable", str(tmp_path / "python.exe")):
            with mock.patch.object(
                installer_main.sys, "argv", [str(tmp_path / "some_script.py")]
            ):
                with mock.patch("shutil.which", return_value=None):
                    result = installer_main.find_executable("moleditpy")

        assert result is not None
        assert "moleditpy" in result.lower()

    @pytest.mark.skipif(platform.system() == "Windows", reason="Unix layout only")
    def test_finds_exe_in_same_dir_as_python_unix(self, tmp_path):
        """Executable in the same dir as sys.executable (Linux/macOS layout)."""
        _make_fake_exe(tmp_path, "moleditpy")

        with (
            mock.patch.object(installer_main.sys, "executable", str(tmp_path / "python")),
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
            mock.patch.object(installer_main.sys, "executable", str(tmp_path / "python.exe")),
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

        with mock.patch.object(installer_main.sys, "executable", str(tmp_path / "python.exe")):
            with mock.patch.object(installer_main.sys, "argv", [str(tmp_path / "script.py")]):
                with mock.patch("shutil.which", return_value=fake_path):
                    result = installer_main.find_executable("moleditpy")

        assert result == fake_path

    def test_returns_none_when_not_found(self, tmp_path):
        """Returns None when the executable cannot be located anywhere."""
        with mock.patch.object(installer_main.sys, "executable", str(tmp_path / "python.exe")):
            with mock.patch.object(installer_main.sys, "argv", [str(tmp_path / "script.py")]):
                with mock.patch("shutil.which", return_value=None):
                    result = installer_main.find_executable("nonexistent_app")

        assert result is None


# ---------------------------------------------------------------------------
# get_icon_path
# ---------------------------------------------------------------------------


class TestGetIconPath:
    def test_returns_path_on_windows(self):
        with mock.patch("platform.system", return_value="Windows"):
            path = installer_main.get_icon_path()
        assert path is None or path.endswith(".ico")

    def test_returns_path_on_linux(self):
        with mock.patch("platform.system", return_value="Linux"):
            path = installer_main.get_icon_path()
        assert path is None or path.endswith(".png")

    def test_returns_path_on_darwin(self):
        with mock.patch("platform.system", return_value="Darwin"):
            path = installer_main.get_icon_path()
        assert path is None or path.endswith(".icns")

    def test_returns_none_on_unknown_os(self):
        with mock.patch("platform.system", return_value="FreeBSD"):
            path = installer_main.get_icon_path()
        assert path is None

    def test_returns_none_when_resource_raises(self):
        with mock.patch("platform.system", return_value="Windows"), mock.patch(
            "importlib.resources.files", side_effect=OSError("not found")
        ):
            path = installer_main.get_icon_path()
        assert path is None

    def test_returns_none_when_file_missing_in_package(self, tmp_path):
        """as_file context resolves to a path that doesn't exist."""
        missing = tmp_path / "icon.ico"

        fake_ref = mock.MagicMock()
        fake_ref.__truediv__ = mock.Mock(return_value=fake_ref)

        with mock.patch("platform.system", return_value="Windows"), mock.patch(
            "importlib.resources.files", return_value=fake_ref
        ), mock.patch(
            "importlib.resources.as_file"
        ) as mock_as_file:
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

    def test_returns_path_on_windows_when_file_exists(self, tmp_path):
        fake_icon = tmp_path / "file_icon.ico"
        fake_icon.write_bytes(b"")

        fake_ref = mock.MagicMock()
        fake_ref.__truediv__ = mock.Mock(return_value=fake_ref)

        with mock.patch("platform.system", return_value="Windows"), mock.patch(
            "importlib.resources.files", return_value=fake_ref
        ), mock.patch(
            "importlib.resources.as_file"
        ) as mock_as_file:
            mock_as_file.return_value.__enter__ = mock.Mock(return_value=fake_icon)
            mock_as_file.return_value.__exit__ = mock.Mock(return_value=False)
            path = installer_main.get_file_icon_path()

        assert path == str(fake_icon)

    def test_returns_none_when_resource_raises(self):
        with mock.patch("platform.system", return_value="Windows"), mock.patch(
            "importlib.resources.files", side_effect=OSError("boom")
        ):
            assert installer_main.get_file_icon_path() is None


# ---------------------------------------------------------------------------
# register_file_associations_windows
# ---------------------------------------------------------------------------


class TestRegisterFileAssociationsWindows:
    def test_returns_false_on_non_windows(self):
        with mock.patch("platform.system", return_value="Linux"):
            assert installer_main.register_file_associations_windows("/bin/app", None) is False

    def test_registers_extensions_on_windows(self, tmp_path):
        fake_icon = str(tmp_path / "icon.ico")
        Path(fake_icon).write_bytes(b"")
        winreg_mock = _make_winreg_mock()

        with mock.patch("platform.system", return_value="Windows"), mock.patch.object(
            installer_main, "winreg", winreg_mock
        ):
            result = installer_main.register_file_associations_windows(
                r"C:\app\moleditpy.exe", fake_icon
            )

        assert result is True
        assert winreg_mock.CreateKey.call_count >= 4  # ProgID + DefaultIcon + command + 2 exts

    def test_returns_false_on_oserror(self):
        winreg_mock = _make_winreg_mock()
        winreg_mock.CreateKey.side_effect = OSError("access denied")

        with mock.patch("platform.system", return_value="Windows"), mock.patch.object(
            installer_main, "winreg", winreg_mock
        ):
            result = installer_main.register_file_associations_windows(
                r"C:\app\moleditpy.exe", None
            )

        assert result is False

    def test_skips_icon_when_path_missing(self):
        winreg_mock = _make_winreg_mock()

        with mock.patch("platform.system", return_value="Windows"), mock.patch.object(
            installer_main, "winreg", winreg_mock
        ):
            result = installer_main.register_file_associations_windows(
                r"C:\app\moleditpy.exe", None
            )

        assert result is True


# ---------------------------------------------------------------------------
# delete_registry_tree
# ---------------------------------------------------------------------------


class TestDeleteRegistryTree:
    def test_deletes_key_with_no_subkeys(self):
        winreg_mock = _make_winreg_mock()
        winreg_mock.QueryInfoKey.return_value = (0, 0, 0)

        with mock.patch.object(installer_main, "winreg", winreg_mock):
            result = installer_main.delete_registry_tree(winreg_mock.HKEY_CURRENT_USER, "key")

        assert result is True
        winreg_mock.DeleteKey.assert_called_once()

    def test_returns_false_on_oserror(self):
        winreg_mock = _make_winreg_mock()
        winreg_mock.OpenKey.side_effect = OSError("not found")

        with mock.patch.object(installer_main, "winreg", winreg_mock):
            result = installer_main.delete_registry_tree(winreg_mock.HKEY_CURRENT_USER, "key")

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

        with mock.patch("platform.system", return_value="Windows"), mock.patch.object(
            installer_main, "winreg", winreg_mock
        ), mock.patch.object(
            installer_main, "delete_registry_tree", return_value=True
        ) as mock_del:
            installer_main.unregister_file_associations_windows()

        assert winreg_mock.DeleteKey.call_count == 2  # .pmeprj and .pmeraw
        mock_del.assert_called_once()

    def test_ignores_already_missing_keys(self, capsys):
        winreg_mock = _make_winreg_mock()
        winreg_mock.DeleteKey.side_effect = FileNotFoundError

        with mock.patch("platform.system", return_value="Windows"), mock.patch.object(
            installer_main, "winreg", winreg_mock
        ), mock.patch.object(installer_main, "delete_registry_tree", return_value=False):
            installer_main.unregister_file_associations_windows()

        # Should complete without error output about missing keys
        captured = capsys.readouterr()
        assert "failed" not in captured.out.lower()

    def test_prints_error_on_oserror(self, capsys):
        winreg_mock = _make_winreg_mock()
        winreg_mock.DeleteKey.side_effect = OSError("permission denied")

        with mock.patch("platform.system", return_value="Windows"), mock.patch.object(
            installer_main, "winreg", winreg_mock
        ), mock.patch.object(installer_main, "delete_registry_tree", return_value=False):
            installer_main.unregister_file_associations_windows()

        captured = capsys.readouterr()
        assert "failed" in captured.out.lower()


# ---------------------------------------------------------------------------
# remove_shortcut
# ---------------------------------------------------------------------------


class TestRemoveShortcut:
    def test_removes_lnk_on_windows(self, tmp_path):
        lnk = tmp_path / "MoleditPy.lnk"
        lnk.write_bytes(b"")

        with mock.patch("platform.system", return_value="Windows"), mock.patch.dict(
            os.environ, {"APPDATA": str(tmp_path / "AppData")}
        ), mock.patch.object(
            installer_main, "unregister_file_associations_windows"
        ), mock.patch(
            "pathlib.Path.exists", return_value=True
        ), mock.patch(
            "os.remove"
        ) as mock_rm:
            installer_main.remove_shortcut()

        mock_rm.assert_called_once()

    def test_removes_desktop_file_on_linux(self, tmp_path):
        apps_dir = tmp_path / ".local" / "share" / "applications"
        apps_dir.mkdir(parents=True)
        desktop = apps_dir / "MoleditPy.desktop"
        desktop.write_bytes(b"")

        with mock.patch("platform.system", return_value="Linux"), mock.patch(
            "pathlib.Path.home", return_value=tmp_path
        ):
            installer_main.remove_shortcut()

        assert not desktop.exists()

    def test_removes_app_bundle_on_darwin(self, tmp_path):
        app_bundle = tmp_path / "Desktop" / "MoleditPy.app"
        app_bundle.mkdir(parents=True)

        with mock.patch("platform.system", return_value="Darwin"), mock.patch(
            "pathlib.Path.home", return_value=tmp_path
        ):
            installer_main.remove_shortcut()

        assert not app_bundle.exists()

    def test_prints_message_when_shortcut_missing(self, capsys):
        with mock.patch("platform.system", return_value="Linux"), mock.patch(
            "pathlib.Path.home", return_value=Path("/nonexistent/path")
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
        with mock.patch("platform.system", return_value="Linux"), mock.patch(
            "pathlib.Path.home", return_value=Path("/tmp")
        ), mock.patch("pathlib.Path.exists", return_value=True), mock.patch(
            "pathlib.Path.is_dir", return_value=False
        ), mock.patch(
            "os.remove", side_effect=OSError("permission denied")
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
        assert kwargs.get("desktop") is False

    def test_install_calls_make_shortcut_on_darwin(self, tmp_path):
        fake_exe = str(tmp_path / "moleditpy")

        with (
            mock.patch.object(installer_main, "find_executable", return_value=fake_exe),
            mock.patch.object(installer_main, "get_icon_path", return_value=None),
            mock.patch("platform.system", return_value="Darwin"),
            mock.patch("moleditpy_installer.main.make_shortcut") as mock_shortcut,
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            installer_main.install()

        mock_shortcut.assert_called_once()
        _, kwargs = mock_shortcut.call_args
        assert kwargs.get("desktop") is True

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
        script_arg = mock_shortcut.call_args[1].get("script") or mock_shortcut.call_args[0][0]
        assert "conda" in script_arg.lower()
        assert "myenv" in script_arg

    def test_install_skips_conda_for_base_env(self, tmp_path):
        """CONDA_DEFAULT_ENV=base should be treated like no conda env."""
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

        script_arg = mock_shortcut.call_args[1].get("script") or mock_shortcut.call_args[0][0]
        # base env → target is the app exe directly, not the conda wrapper
        assert script_arg == fake_exe

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
                "moleditpy_installer.main.make_shortcut", side_effect=OSError("disk full")
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
        with mock.patch.object(installer_main, "install") as mock_install, mock.patch(
            "sys.argv", ["moleditpy-installer"]
        ):
            result = installer_main.main()
        mock_install.assert_called_once()
        assert result == 0

    def test_main_calls_remove_shortcut_with_flag(self):
        with mock.patch.object(installer_main, "remove_shortcut") as mock_remove, mock.patch(
            "sys.argv", ["moleditpy-installer", "--remove"]
        ):
            result = installer_main.main()
        mock_remove.assert_called_once()
        assert result == 0


# ---------------------------------------------------------------------------
# __main__ module
# ---------------------------------------------------------------------------


def test_package_runnable_as_module():
    """Verify __main__.py exists and imports cleanly (enables python -m moleditpy_installer)."""
    import importlib

    mod = importlib.import_module("moleditpy_installer.__main__")
    assert mod is not None
