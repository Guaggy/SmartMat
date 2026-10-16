"""Engineering > Connection > "SmartMat server": test the server, send or fetch this mat's calibration, read its log.

Plain ttk widgets only (no colours or fonts; the theme styles them). Every network call runs in a thread, so the
window never freezes; Tk is only touched from the main thread. The PIN lives in the dialog's entry and in the one
call that sends it: it is never shown, saved or logged.
"""

import json
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import app_settings
from processing import calibration
from server_client import ServerClient, compare_profiles

MARKERS = {"matches": "Calibration matches server", "differs": "Calibration differs from server",
           "not_on_server": "Calibration not on server"}
NO_MAT_HINT = "Connect a real mat (Serial or MQTT) to send or fetch its calibration."


def ask_pin(parent, what):
    """Small modal dialog with a masked entry; the PIN text, or None when cancelled"""
    dialog = tk.Toplevel(parent)
    dialog.title("PIN")
    dialog.transient(parent.winfo_toplevel())
    dialog.resizable(False, False)
    ttk.Label(dialog, text=f"Enter your PIN to {what}.", padding=(12, 12, 12, 4)).pack()
    pin = tk.StringVar()
    entry = ttk.Entry(dialog, textvariable=pin, show="*", width=20)
    entry.pack(padx=12, pady=4)
    result = []
    done = lambda *_: (result.append(pin.get()), dialog.destroy())
    buttons = ttk.Frame(dialog, padding=12)
    buttons.pack()
    ttk.Button(buttons, text="OK", command=done).pack(side=tk.LEFT, padx=4)
    ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=4)
    dialog.bind("<Return>", done)
    dialog.bind("<Escape>", lambda _: dialog.destroy())
    entry.focus_set()
    dialog.grab_set()
    parent.wait_window(dialog)
    pin.set("")
    return result[0] if result and result[0] else None


class ServerPanel:
    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.LabelFrame(parent, text="SmartMat server", padding=8)
        self.url_var = tk.StringVar(value=app_settings.effective_server_url())
        self.status_var = tk.StringVar(value="")
        self.marker_var = tk.StringVar(value="")
        self.hint_var = tk.StringVar(value="")
        self.busy = False
        self.shown_mat = False  # which mat the marker is for (False = none yet)
        ttk.Label(self.frame, wraplength=760, justify=tk.LEFT, text=(
            "The SmartMat server (on the Pi or a PC) keeps each mat's calibration for everyone. "
            "Sending asks for your PIN. Example: http://10.0.0.15:8000")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        ttk.Label(self.frame, text="Server URL").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(self.frame, textvariable=self.url_var, width=35).grid(row=1, column=1, sticky="w", padx=8)
        self.test_button = ttk.Button(self.frame, text="Test", command=self._test)
        self.test_button.grid(row=1, column=2, sticky="w")
        bar = ttk.Frame(self.frame)
        bar.grid(row=2, column=0, columnspan=4, sticky="w", pady=6)
        self.mat_buttons = [ttk.Button(bar, text=text, command=command) for text, command in (
            ("Send calibration to server", self._send), ("Get from server", self._get),
            ("Server log", self._show_log))]
        for button in self.mat_buttons:
            button.pack(side=tk.LEFT, padx=(0, 8))
        for row, variable in enumerate((self.marker_var, self.hint_var, self.status_var), start=3):
            ttk.Label(self.frame, textvariable=variable, wraplength=760, justify=tk.LEFT).grid(
                row=row, column=0, columnspan=4, sticky="w")
        self._tick()

    # ---- state

    def _mat(self):
        return self.app._profile_mat_id()

    def _tick(self):
        """Once a second: keep the buttons right for the connected mat and re-check the marker when it changes"""
        if not self.frame.winfo_exists():
            return
        mat = self._mat()
        if mat != self.shown_mat and not self.busy:
            self.shown_mat = mat
            self._refresh_marker()
        self._set_states()
        self.frame.after(1000, self._tick)

    def _set_states(self):
        mat = self._mat()
        state = ["disabled"] if self.busy else ["!disabled"]
        self.test_button.state(state)
        for button in self.mat_buttons:
            button.state(["disabled"] if self.busy or not mat else ["!disabled"])
        self.hint_var.set("" if mat else NO_MAT_HINT)

    def _url(self):
        """The URL from the field (saved to settings.json), or None with the reason in the status line"""
        text = self.url_var.get().strip()
        try:
            app_settings.save_server_url(text)
        except ValueError as error:
            self.status_var.set(str(error))
            return None
        except OSError as error:
            self.status_var.set(f"Could not save the server address: {error}")
        if not text:
            self.status_var.set("Enter the server address first.")
            return None
        self.url_var.set(app_settings.effective_server_url())
        return self.url_var.get()

    def _run(self, work, done):
        """work() in a thread; done(result) back on the main thread unless the window is gone"""
        self.busy = True
        self._set_states()

        def thread():
            result = work()
            try:
                self.frame.after(0, lambda: finish(result))
            except (tk.TclError, RuntimeError):
                pass

        def finish(result):
            if not self.frame.winfo_exists():
                return
            self.busy = False
            self._set_states()
            done(result)

        threading.Thread(target=thread, daemon=True).start()

    def _local_profile(self, mat):
        self.app._save_profile()  # writes the live state to the mat's profile file
        return calibration.load_profile(mat)

    # ---- marker

    def _refresh_marker(self):
        mat, url = self._mat(), app_settings.effective_server_url()
        if not url:
            self.marker_var.set("Calibration: server not set")
            return
        if not mat:
            self.marker_var.set("Calibration: no mat connected")
            return
        self.marker_var.set("Calibration: checking the server ...")
        local = self._local_profile(mat)

        def done(result):
            if self._mat() != mat:  # the mat changed while asking
                return
            ok, data = result
            if not ok:
                self.marker_var.set(f"Calibration: server not reachable ({data})")
            else:
                remote = data.get("profile") if isinstance(data, dict) else None
                self.marker_var.set(MARKERS[compare_profiles(local, remote)])

        self._run(lambda: ServerClient(url).get_profile(mat), done)

    # ---- buttons

    def _test(self):
        url = self._url()
        if url is None:
            return
        self.status_var.set(f"Testing {url} ...")

        def done(result):
            ok, data = result
            if ok and isinstance(data, dict):
                self.status_var.set(f"OK: SmartMat server version {data.get('version', '?')}, "
                                    f"{data.get('mats', '?')} mat(s) connected")
            else:
                self.status_var.set(f"Test failed: {data}")
            self._refresh_marker()

        self._run(lambda: ServerClient(url).health(), done)

    def _send(self):
        url, mat = self._url(), self._mat()
        if url is None or not mat:
            return
        profile = self._local_profile(mat)
        if profile is None:
            self.status_var.set("This mat has no calibration profile to send yet.")
            return
        pin = ask_pin(self.frame, "send this calibration")
        if pin is None:
            return
        self.status_var.set("Sending ...")

        def done(result):
            ok, data = result
            if ok:
                user = data.get("user") if isinstance(data, dict) else None
                version = data.get("version") if isinstance(data, dict) else None
                self.status_var.set(f"Saved by {user}" if user else f"Saved on the server (version {version})")
                self._refresh_marker()
            else:
                self.status_var.set(f"Not saved: {data}")

        self._run(lambda: ServerClient(url).put_profile(mat, profile, pin), done)

    def _get(self):
        url, mat = self._url(), self._mat()
        if url is None or not mat:
            return
        self.status_var.set("Fetching ...")

        def done(result):
            ok, data = result
            if not ok:
                self.status_var.set(f"Could not get it: {data}")
                return
            profile = data.get("profile") if isinstance(data, dict) else None
            if not profile:
                self.status_var.set("The server has no calibration for this mat.")
                return
            if self._mat() == mat and messagebox.askyesno(
                    "Get from server", f"Replace this mat's tare and calibration here with the server's "
                                       f"(version {data.get('version')})?", parent=self.frame):
                self.status_var.set(self._apply(mat, profile))
                self._refresh_marker()
            else:
                self.status_var.set("Nothing changed.")

        self._run(lambda: ServerClient(url).get_profile(mat), done)

    def _apply(self, mat, profile):
        """Put the server's profile through the app's normal profile load (it is read from the mat's profile file).
        The current state is saved first and put back if the server's profile does not fit this mat."""
        path = calibration.profile_path(mat)
        try:
            self.app._save_profile()
            backup = path.read_text(encoding="utf-8") if path.exists() else None
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        except OSError as error:
            return f"Could not write the profile: {error}"
        label = self.app._load_profile()
        if "restored" in label:
            return "Calibration replaced with the server's."
        if backup is not None:
            path.write_text(backup, encoding="utf-8")
            self.app._load_profile()
        return f"The server's profile does not fit this mat, kept the current one{label}"

    def _show_log(self):
        url, mat = self._url(), self._mat()
        if url is None or not mat:
            return
        window = tk.Toplevel(self.frame)
        window.title(f"Server log: {mat}")
        window.geometry("760x360")
        note = tk.StringVar(value="Loading ...")
        ttk.Label(window, textvariable=note, padding=6).pack(side=tk.TOP, fill=tk.X)
        table = ttk.Treeview(window, columns=("time", "event", "user", "detail"), show="headings")
        for key, title, width in (("time", "Time", 140), ("event", "Event", 150), ("user", "By", 100),
                                  ("detail", "Detail", 340)):
            table.heading(key, text=title)
            table.column(key, width=width, anchor="w")
        table.pack(fill=tk.BOTH, expand=True)

        def thread():
            result = ServerClient(url).get_log(mat)
            try:
                window.after(0, lambda: fill(result))
            except (tk.TclError, RuntimeError):
                pass

        def fill(result):
            if not window.winfo_exists():
                return
            ok, data = result
            if not ok:
                note.set(f"Could not read the log: {data}")
                return
            note.set(f"{len(data)} recent event(s), newest first" if data else "No events for this mat yet.")
            for event in data:
                detail = event.get("detail")
                table.insert("", tk.END, values=(
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event.get("t", 0))),
                    event.get("kind", ""), event.get("user") or "",
                    "" if detail is None else json.dumps(detail, separators=(",", ":"))))

        threading.Thread(target=thread, daemon=True).start()
