"""
Interactive Textual TUI for the MoleditPy installer (nmtui-style).

Launched by ``moleditpy-installer`` when running in a real terminal with no
component flags; ``--no-tui`` or any explicit option skips it.
"""

import contextlib
import io
import platform

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Label,
    RadioButton,
    RadioSet,
    RichLog,
    Static,
)

from . import main as installer


class _LogWriter(io.TextIOBase):
    """File-like object forwarding installer prints into the RichLog."""

    def __init__(self, app: "InstallerApp") -> None:
        self._app = app
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._app.call_from_thread(self._app.log_line, line)
        return len(text)

    def flush(self) -> None:  # pragma: no cover - io protocol
        if self._buffer:
            self._app.call_from_thread(self._app.log_line, self._buffer)
            self._buffer = ""


class InstallerApp(App):
    """Choose components and scope, then install or remove MoleditPy."""

    TITLE = "MoleditPy Installer"
    SUB_TITLE = f"v{installer.get_installer_version()}"

    CSS = """
    Screen {
        layout: vertical;
    }
    #options {
        height: auto;
        border: round $primary;
        padding: 0 2;
        margin: 1 2 0 2;
    }
    #options Label {
        margin-top: 1;
        text-style: bold;
        color: $text;
    }
    #scope {
        height: auto;
        margin-top: 1;
    }
    #buttons {
        height: auto;
        align-horizontal: center;
        margin: 1 0;
    }
    #buttons Button {
        margin: 0 2;
        min-width: 16;
    }
    #log {
        border: round $secondary;
        margin: 0 2 1 2;
        height: 1fr;
    }
    #status {
        margin: 0 3;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("i", "install", "Install"),
        ("r", "remove", "Remove"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="options"):
            yield Label("Components")
            yield Checkbox("Desktop shortcut", value=False, id="desktop")
            yield Checkbox("Application menu entry", value=True, id="app_menu")
            yield Checkbox(".pmeprj file association", value=True, id="file_assoc")
            yield Label("Scope")
            with RadioSet(id="scope"):
                yield RadioButton("User (recommended)", value=True, id="scope_user")
                yield RadioButton(
                    "System-wide (requires sudo/root)",
                    id="scope_system",
                    disabled=platform.system() == "Windows",
                )
        with Horizontal(id="buttons"):
            yield Button("Install", variant="success", id="install")
            yield Button("Remove", variant="error", id="remove")
            yield Button("Quit", variant="default", id="quit")
        yield Static("", id="status")
        yield RichLog(id="log", wrap=True, markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.exit_code = 0
        self.log_line("Welcome! Pick components, then press Install.")
        if platform.system() == "Windows":
            self.log_line("Note: system-wide scope is not available on Windows.")
        self.run_worker(self._detect_executable, thread=True)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def log_line(self, line: str) -> None:
        self.query_one("#log", RichLog).write(line)

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def _selected_options(self) -> installer.InstallOptions:
        return installer.InstallOptions(
            desktop=self.query_one("#desktop", Checkbox).value,
            app_menu=self.query_one("#app_menu", Checkbox).value,
            file_assoc=self.query_one("#file_assoc", Checkbox).value,
            system=self.query_one("#scope_system", RadioButton).value,
        )

    def _set_busy(self, busy: bool) -> None:
        for button_id in ("install", "remove"):
            self.query_one(f"#{button_id}", Button).disabled = busy

    def _detect_executable(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            path = installer.find_executable("moleditpy")
            if not path and platform.system() == "Linux":
                path = installer.find_executable("moleditpy-linux")
        if path:
            self.call_from_thread(self._set_status, f"Found moleditpy: {path}")
        else:
            self.call_from_thread(
                self._set_status,
                "moleditpy executable not found — install it first (pip install moleditpy)",
            )

    def _run_installer_action(self, action, description: str) -> None:
        writer = _LogWriter(self)
        try:
            with contextlib.redirect_stdout(writer):
                result = action()
        except Exception as e:  # surface, never crash the UI
            self.call_from_thread(self.log_line, f"Unexpected error: {e}")
            result = 1
        writer.flush()
        ok = not result  # None (remove) or 0 (install) mean success
        self.call_from_thread(
            self.log_line,
            f"--- {description} {'finished' if ok else 'FAILED'} ---",
        )
        # Quit propagates the last action's outcome as the exit code
        self.call_from_thread(setattr, self, "exit_code", 0 if ok else 1)
        self.call_from_thread(self._set_busy, False)

    # ------------------------------------------------------------------ #
    # actions
    # ------------------------------------------------------------------ #

    def action_install(self) -> None:
        options = self._selected_options()
        self._set_busy(True)
        self.log_line("")
        self.log_line(
            "Installing: "
            f"desktop={'yes' if options.desktop else 'no'}, "
            f"app menu={'yes' if options.app_menu else 'no'}, "
            f"file association={'yes' if options.file_assoc else 'no'}, "
            f"scope={'system' if options.system else 'user'}"
        )
        self.run_worker(
            lambda: self._run_installer_action(
                lambda: installer.install(options), "Install"
            ),
            thread=True,
        )

    def action_remove(self) -> None:
        system_scope = self.query_one("#scope_system", RadioButton).value
        self._set_busy(True)
        self.log_line("")
        self.log_line(
            f"Removing shortcuts and file associations "
            f"(scope={'system' if system_scope else 'user'})..."
        )
        self.run_worker(
            lambda: self._run_installer_action(
                lambda: installer.remove_shortcut(system_scope=system_scope), "Remove"
            ),
            thread=True,
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "install":
            self.action_install()
        elif event.button.id == "remove":
            self.action_remove()
        elif event.button.id == "quit":
            self.exit(self.exit_code)


def run_tui() -> int:
    """Run the installer TUI; returns a process exit code."""
    app = InstallerApp()
    result = app.run()
    return result if isinstance(result, int) else 0
