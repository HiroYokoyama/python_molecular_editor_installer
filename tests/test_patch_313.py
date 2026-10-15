"""Regression coverage for installer failures found in the 3.1.3 audit."""

import asyncio
import os
import stat
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "moleditpy-installer"))
from moleditpy_installer import main as installer


def test_tui_discovery_does_not_redirect_other_threads_stdout():
    from moleditpy_installer.tui import InstallerApp

    original_stdout = sys.stdout

    def discover(name, *, quiet=False):
        assert quiet is True
        assert sys.stdout is original_stdout
        return "/env/bin/moleditpy"

    app = InstallerApp()
    with (
        mock.patch.object(installer, "find_executable", side_effect=discover),
        mock.patch.object(app, "call_from_thread") as callback,
    ):
        app._detect_executable()
    callback.assert_called_once()


def test_quiet_discovery_has_no_console_output(tmp_path, capsys):
    app = tmp_path / ("moleditpy.exe" if sys.platform == "win32" else "moleditpy")
    app.write_bytes(b"app")
    app.chmod(app.stat().st_mode | stat.S_IEXEC)
    with mock.patch.object(sys, "executable", str(tmp_path / "python")):
        assert installer.find_executable("moleditpy", quiet=True) == str(app)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("system", ["Windows", "Linux"])
def test_association_failure_returns_failure(system, tmp_path):
    """An unsuccessful requested component must reach the CLI/TUI exit code."""
    with (
        mock.patch("platform.system", return_value=system),
        mock.patch.dict(os.environ, {}, clear=True),
        mock.patch.object(
            installer, "find_executable", return_value=str(tmp_path / "moleditpy")
        ),
        mock.patch.object(installer, "get_icon_path", return_value=None),
        mock.patch.object(installer, "get_file_icon_path", return_value=None),
        mock.patch.object(installer, "make_shortcut"),
        mock.patch.object(installer, "_com_initialized", mock.MagicMock()),
        mock.patch.object(
            installer, "register_file_associations_windows", return_value=False
        ),
        mock.patch.object(
            installer, "register_file_associations_linux", return_value=False
        ),
    ):
        assert installer.install() == 1


def test_system_desktop_failure_stops_install(tmp_path):
    with (
        mock.patch("platform.system", return_value="Linux"),
        mock.patch.dict(os.environ, {}, clear=True),
        mock.patch.object(installer, "is_root", return_value=True),
        mock.patch.object(
            installer, "find_executable", return_value=str(tmp_path / "moleditpy")
        ),
        mock.patch.object(installer, "get_icon_path", return_value=None),
        mock.patch.object(
            installer, "write_linux_system_desktop_entry", return_value=False
        ),
        mock.patch.object(installer, "register_file_associations_linux") as association,
    ):
        assert installer.install(installer.InstallOptions(system=True)) == 1
    association.assert_not_called()


def test_macos_association_failure_keeps_existing_bundle(tmp_path):
    existing = tmp_path / "Applications" / "MoleditPy.app"
    existing.mkdir(parents=True)
    marker = existing / "existing.txt"
    marker.write_text("keep", encoding="utf-8")

    def compile_bundle(command, **kwargs):
        Path(command[2]).mkdir(parents=True)
        return mock.Mock(returncode=0, stderr=b"")

    with (
        mock.patch("platform.system", return_value="Darwin"),
        mock.patch.dict(os.environ, {}, clear=True),
        mock.patch("pathlib.Path.home", return_value=tmp_path),
        mock.patch.object(
            installer, "find_executable", return_value=str(tmp_path / "moleditpy")
        ),
        mock.patch.object(installer, "get_icon_path", return_value=None),
        mock.patch.object(
            installer, "python_for_executable", return_value=sys.executable
        ),
        mock.patch.object(installer, "verify_launch_command", return_value=True),
        mock.patch.object(
            installer.tempfile, "mkdtemp", return_value=str(tmp_path / "build")
        ),
        mock.patch.object(installer.subprocess, "run", side_effect=compile_bundle),
        mock.patch.object(
            installer, "register_file_associations_darwin", return_value=False
        ),
        mock.patch.object(installer, "codesign_app") as sign,
    ):
        assert installer.install() == 1
    sign.assert_not_called()
    assert marker.read_text(encoding="utf-8") == "keep"


def test_macos_quotes_executable_path_for_terminal(tmp_path):
    exe = '/opt/chem $HOME/with "quotes"\\folder/moleditpy'
    with (
        mock.patch("platform.system", return_value="Darwin"),
        mock.patch.dict(os.environ, {}, clear=True),
        mock.patch("pathlib.Path.home", return_value=tmp_path),
        mock.patch.object(installer, "find_executable", return_value=exe),
        mock.patch.object(installer, "get_icon_path", return_value=None),
        mock.patch.object(
            installer, "python_for_executable", return_value="/env/bin/python"
        ),
        mock.patch.object(installer, "verify_launch_command", return_value=True),
        mock.patch.object(
            installer, "register_file_associations_darwin", return_value=True
        ),
        mock.patch.object(installer, "codesign_app"),
        mock.patch.object(installer, "refresh_launch_services"),
        mock.patch.object(installer.shutil, "copytree"),
        mock.patch.object(
            installer.subprocess, "run", return_value=mock.Mock(returncode=0)
        ) as compile_app,
    ):
        assert installer.install() == 0
    code = compile_app.call_args.args[0][-1]
    base_cmd = next(line for line in code.splitlines() if "set base_cmd" in line)
    assert base_cmd.count("quoted form of") == 2
    assert '$HOME/with \\"quotes\\"\\\\folder/moleditpy' in base_cmd


def test_mime_cleanup_preserves_other_handlers_and_comments(tmp_path):
    mimeapps = tmp_path / "mimeapps.list"
    mime = installer.LINUX_MIME_TYPE
    mimeapps.write_text(
        f"# {mime} documentation\n"
        "[Default Applications]\n"
        f"{mime}=MoleditPy.desktop;OtherEditor.desktop;\n"
        "[Added Associations]\n"
        f"{mime}=OtherEditor.desktop;MoleditPy.desktop;\n"
        "[Removed Associations]\n"
        f"{mime}=BlockedEditor.desktop;\n"
        "text/plain=TextEditor.desktop;\n",
        encoding="utf-8",
    )
    with (
        mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}),
        mock.patch.object(installer, "linux_data_home", return_value=tmp_path / "data"),
    ):
        installer._clean_linux_mimeapps()
    result = mimeapps.read_text(encoding="utf-8")
    assert "MoleditPy.desktop" not in result
    assert result.count(f"{mime}=OtherEditor.desktop;") == 2
    assert f"{mime}=BlockedEditor.desktop;" in result
    assert f"# {mime} documentation" in result
    assert "text/plain=TextEditor.desktop;" in result


@pytest.mark.parametrize("system", ["Linux", "Darwin"])
def test_search_prefers_venv_next_to_symlinked_python(tmp_path, system):
    base = tmp_path / "base"
    env = tmp_path / "env" / "bin"
    base.mkdir()
    env.mkdir(parents=True)
    base_python = base / "python"
    base_python.write_bytes(b"python")
    env_python = env / "python"
    try:
        env_python.symlink_to(base_python)
    except OSError:
        pytest.skip("Creating symbolic links is not available on this host")
    for directory in (base, env):
        app = directory / "moleditpy"
        app.write_bytes(b"app")
        app.chmod(app.stat().st_mode | stat.S_IEXEC)
    with (
        mock.patch("platform.system", return_value=system),
        mock.patch.object(sys, "executable", str(env_python)),
    ):
        assert installer.find_executable("moleditpy") == str(env / "moleditpy")


@pytest.mark.parametrize("first", ["install", "remove"])
def test_tui_shortcuts_cannot_start_overlapping_actions(first):
    from moleditpy_installer.tui import InstallerApp

    async def check():
        app = InstallerApp()
        with mock.patch.object(app, "_detect_executable"):
            async with app.run_test() as pilot:
                await pilot.pause()
                # Leave the first worker pending, as a slow real operation would be.
                with mock.patch.object(app, "run_worker") as worker:
                    getattr(app, f"action_{first}")()
                    app.action_install()
                    app.action_remove()
                    app.action_quit()
                    assert worker.call_count == 1
                    assert app.return_value is None
                    app._finish_action("Install", False)
                    app.action_install()
                    assert worker.call_count == 2  # a failed action can be retried

    asyncio.run(check())


def test_tui_success_wait_does_not_allow_another_action():
    from moleditpy_installer.tui import InstallerApp

    async def check():
        app = InstallerApp()
        with mock.patch.object(app, "_detect_executable"):
            async with app.run_test() as pilot:
                await pilot.pause()
                with mock.patch.object(app, "run_worker") as worker:
                    app.action_install()
                    app._finish_action("Install", True)
                    app.action_remove()
                    assert worker.call_count == 1

    asyncio.run(check())
