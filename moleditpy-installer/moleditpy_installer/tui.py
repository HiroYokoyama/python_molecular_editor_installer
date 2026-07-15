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

    # Focus Install on start so a bare Enter runs the default install.
    # (A plain .focus() in on_mount is overridden by the screen's
    # auto-focus once it becomes active.)
    AUTO_FOCUS = "#install"

    # Pause before auto-exit on success so the final log lines stay
    # readable in the TUI (tests shrink this to keep the suite fast).
    EXIT_DELAY_SECONDS = 2.0

    # Compact layout: everything (including the buttons) must fit in a
    # standard 80x24 terminal — on smaller screens the buttons were pushed
    # below the fold and mouse clicks could not reach them. overflow-y
    # keeps the screen scrollable as a safety net on tiny terminals.
    CSS = """
    Screen {
        layout: vertical;
        overflow-y: auto;
    }
    #options {
        height: auto;
        border: round $primary;
        padding: 0 1;
        margin: 0 2;
    }
    #options Label {
        text-style: bold;
        color: $text;
    }
    #scope {
        height: auto;
        border: none;
        padding: 0;
    }
    #buttons {
        height: auto;
        align-horizontal: center;
    }
    #buttons Button {
        margin: 0 2;
        min-width: 16;
    }
    #log {
        border: round $secondary;
        margin: 0 2;
        height: 1fr;
        min-height: 3;
    }
    #status {
        height: 1;
        margin: 0 2;
        padding: 0 1;
        background: $boost;
        color: $text;
    }
    """

    BINDINGS = [
        ("i", "install", "Install"),
        ("u", "remove", "Uninstall"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.exit_code = 0
        self._history = []
        self._show_uninstall_note = False
        self._action_started = False

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
                    "System-wide (requires sudo / admin terminal)",
                    id="scope_system",
                )
        with Horizontal(id="buttons"):
            yield Button("Install", variant="success", id="install")
            yield Button("Uninstall", variant="error", id="remove")
            yield Button("Quit", variant="default", id="quit")
        yield Static("Status: detecting moleditpy executable…", id="status")
        yield RichLog(id="log", wrap=True, markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.log_line("Welcome! Pick components, then press Install.")
        if platform.system() == "Windows":
            self.log_line("Note: system-wide scope needs an administrator terminal.")
        self.run_worker(self._detect_executable, thread=True)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def log_line(self, line: str) -> None:
        self._history.append(line)
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
            self.call_from_thread(self._set_detect_status, f"Found moleditpy: {path}")
        else:
            self.call_from_thread(
                self._set_detect_status,
                "moleditpy executable not found — install it first (pip install moleditpy)",
            )

    def _set_detect_status(self, text: str) -> None:
        # A slow detection must not overwrite the status of an install or
        # uninstall the user has already started.
        if not self._action_started:
            self._set_status(text)

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
        self.call_from_thread(self._finish_action, description, ok)

    def _finish_action(self, description: str, ok: bool) -> None:
        self.log_line(f"--- {description} {'finished' if ok else 'FAILED'} ---")
        self.exit_code = 0 if ok else 1
        if ok:
            if description == "Uninstall":
                self._show_uninstall_note = True
            # Linger briefly so the result is readable, then exit;
            # run_tui() replays the log in the terminal afterwards.
            self._set_status(f"{description} finished — exiting…")
            self.set_timer(self.EXIT_DELAY_SECONDS, lambda: self.exit(self.exit_code))
        else:
            # Stay open so the options can be adjusted and retried.
            self._set_status(f"{description} FAILED — see the log, adjust and retry.")
            self._set_busy(False)

    # ------------------------------------------------------------------ #
    # actions
    # ------------------------------------------------------------------ #

    def action_install(self) -> None:
        options = self._selected_options()
        self._action_started = True
        self._set_busy(True)
        self.log_line("")
        self.log_line(
            "Installing: "
            f"desktop={'yes' if options.desktop else 'no'}, "
            f"app menu={'yes' if options.app_menu else 'no'}, "
            f"file association={'yes' if options.file_assoc else 'no'}, "
            f"scope={'system' if options.system else 'user'}"
        )
        self._set_status("Installing…")
        self.run_worker(
            lambda: self._run_installer_action(
                lambda: installer.install(options), "Install"
            ),
            thread=True,
        )

    def action_remove(self) -> None:
        system_scope = self.query_one("#scope_system", RadioButton).value
        self._action_started = True
        self._set_busy(True)
        self.log_line("")
        self.log_line(
            f"Removing shortcuts and file associations "
            f"(scope={'system' if system_scope else 'user'})..."
        )
        self._set_status("Removing…")
        self.run_worker(
            lambda: self._run_installer_action(
                lambda: installer.remove_shortcut(system_scope=system_scope),
                "Uninstall",
            ),
            thread=True,
        )

    def on_key(self, event) -> None:
        """Move between the action buttons with the left/right arrow keys
        (tab / shift+tab always work as well)."""
        focused = self.focused
        button_ids = ("install", "remove", "quit")
        if (
            event.key in ("left", "right")
            and focused is not None
            and focused.id in button_ids
        ):
            index = button_ids.index(focused.id)
            step = 1 if event.key == "right" else -1
            target = button_ids[(index + step) % len(button_ids)]
            self.query_one(f"#{target}", Button).focus()
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "install":
            self.action_install()
        elif event.button.id == "remove":
            self.action_remove()
        elif event.button.id == "quit":
            self.exit(self.exit_code)


def run_tui() -> int:
    """Run the installer TUI; returns a process exit code.

    After the TUI closes (auto-exit on success or manual quit), the full
    session log is replayed to the terminal so the results stay visible.
    """
    app = InstallerApp()
    result = app.run()
    code = result if isinstance(result, int) else 0

    history = getattr(app, "_history", [])
    if history:
        print("MoleditPy installer log:")
        for line in history:
            print(f"  {line}")
    print(f"Result: {'success' if code == 0 else f'FAILED (exit code {code})'}")
    if getattr(app, "_show_uninstall_note", False):
        print(
            "Note: shortcuts and file associations were removed. "
            "To fully remove MoleditPy itself, run: pip uninstall moleditpy"
        )
    return code
