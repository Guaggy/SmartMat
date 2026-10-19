"""Engineering > Connection > "SmartMat server": test the server, send or fetch this mat's calibration, read its log.

Plain ttk widgets only (no colours or fonts; the theme styles them). Every network call runs in a thread, so the
window never freezes; Tk is only touched from the main thread. The PIN lives in the dialog's entry and in the one
call that sends it: it is never shown, saved or logged.
"""

import json
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from client import analysis_sync
import app_settings
from processing import calibration
from processing.recording import RECORDINGS_DIR, load_session
from client.server_client import ServerClient, compare_profiles

MARKERS = {"matches": "Calibration matches server", "differs": "Calibration differs from server",
           "not_on_server": "Calibration not on server"}
NO_MAT_HINT = "Connect a real mat (Serial or MQTT) to send or fetch its calibration."
PREVIEW_MAX_S = 600   # a preview replays at most the first ten minutes of a recording


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


def apply_profile_to_app(app, mat, profile, source):
    """Put a profile from elsewhere (the server, a mat's passport) through the app's normal profile load (it is read from
    the mat's profile file). The current state is saved first and put back if the profile does not fit this mat.
    Returns the sentence for the status line."""
    path = calibration.profile_path(mat)
    try:
        app._save_profile()
        backup = path.read_text(encoding="utf-8") if path.exists() else None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    except OSError as error:
        return f"Could not write the profile: {error}"
    label = app._load_profile()
    if "restored" in label:
        return f"Calibration replaced with {source}."
    if backup is not None:
        path.write_text(backup, encoding="utf-8")
        app._load_profile()
    return f"{source.capitalize()} profile does not fit this mat, kept the current one{label}"


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
        ttk.Label(self.frame, wraplength=760, justify=tk.LEFT, text=(
            "Analysis settings of this mat (contact threshold, hotspots, movement, time analysis, risk indices): "
            "compare them with the server's, preview what the server would do with yours on a recording, send them "
            "or get the server's. Files: Save / Load preset above.")).grid(
            row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))
        analysis_bar = ttk.Frame(self.frame)
        analysis_bar.grid(row=4, column=0, columnspan=4, sticky="w", pady=6)
        self.analysis_buttons = [ttk.Button(analysis_bar, text=text, command=command) for text, command in (
            ("Compare", self._compare), ("Preview on a recording...", self._preview),
            ("Send analysis settings...", self._push), ("Get analysis settings", self._pull))]
        for button in self.analysis_buttons:
            button.pack(side=tk.LEFT, padx=(0, 8))
        for row, variable in enumerate((self.marker_var, self.hint_var, self.status_var), start=5):
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
        for button in (*self.mat_buttons, *self.analysis_buttons):
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
        return apply_profile_to_app(self.app, mat, profile, "the server's")

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

    # ---- analysis settings: compare, push, pull, preview (the logic is in analysis_sync.py)

    def _analysis_page(self, then):
        """Read this mat's settings from the server, then then(mat, url, page) on the main thread"""
        url, mat = self._url(), self._mat()
        if url is None or not mat:
            return
        self.status_var.set("Asking the server ...")

        def done(result):
            ok, page = result
            if not ok:
                self.status_var.set(f"Could not read the mat's settings from the server: {page}")
            elif self._mat() == mat:  # the mat changed while asking: drop the answer
                then(mat, url, page)

        self._run(lambda: ServerClient(url).get_config(mat), done)

    def _compare(self):
        def then(mat, url, page):
            rows = analysis_sync.compare(self.app.current_settings(), page)
            differing = sum(row["differs"] for row in rows)
            self.status_var.set(f"{differing} analysis setting(s) differ from the server's." if differing
                                else "Analysis settings match the server's.")
            self._show_rows(mat, page, rows)

        self._analysis_page(then)

    def _show_rows(self, mat, page, rows):
        window = tk.Toplevel(self.frame)
        window.title(f"Analysis settings: {mat}")
        window.geometry("720x420")
        ttk.Label(window, padding=6, wraplength=700, justify=tk.LEFT, text=(
            f"Server settings version {page.get('stamp', '?')}. \"From\" says where the server's value comes from: "
            "factory, site (every mat) or this mat.")).pack(side=tk.TOP, fill=tk.X)
        show_all = tk.BooleanVar(value=False)
        table = ttk.Treeview(window, columns=("setting", "desktop", "server", "from"), show="headings")
        for key, title, width in (("setting", "Setting", 260), ("desktop", "This desktop", 130),
                                  ("server", "Server", 130), ("from", "From", 90)):
            table.heading(key, text=title)
            table.column(key, width=width, anchor="w")

        def fill():
            table.delete(*table.get_children())
            for row in rows:
                if row["differs"] or show_all.get():
                    table.insert("", tk.END, values=(
                        row["label"], analysis_sync.describe(row["key"], row["local"]),
                        analysis_sync.describe(row["key"], row["server"]), row["source"]))

        ttk.Checkbutton(window, text="Show the settings that match too", variable=show_all, command=fill).pack(
            side=tk.TOP, anchor="w", padx=6)
        table.pack(fill=tk.BOTH, expand=True)
        fill()

    def _push(self):
        def then(mat, url, page):
            rows = analysis_sync.compare(self.app.current_settings(), page)
            changes = analysis_sync.changes_to_push(rows)
            if not changes:
                self.status_var.set("Nothing to send: this desktop's analysis settings already match the server's.")
                return
            self._push_dialog(mat, url, [row for row in rows if row["key"] in changes], changes)

        self._analysis_page(then)

    def _push_dialog(self, mat, url, rows, changes):
        dialog = tk.Toplevel(self.frame)
        dialog.title("Send analysis settings")
        dialog.transient(self.frame.winfo_toplevel())
        ttk.Label(dialog, wraplength=560, justify=tk.LEFT, padding=10, text=(
            "These settings differ from the server's. Sending them changes how the server analyses this mat and "
            "when it raises alerts. The change is saved on the server as a new version with your name.")).pack(anchor="w")
        table = ttk.Treeview(dialog, columns=("setting", "server", "desktop"), show="headings", height=min(8, len(rows)))
        for key, title, width in (("setting", "Setting", 280), ("server", "Server now", 130), ("desktop", "This desktop", 130)):
            table.heading(key, text=title)
            table.column(key, width=width, anchor="w")
        for row in rows:
            table.insert("", tk.END, values=(row["label"], analysis_sync.describe(row["key"], row["server"]),
                                             analysis_sync.describe(row["key"], row["local"])))
        table.pack(fill=tk.X, padx=10)
        scope = tk.StringVar(value="mat")
        ttk.Radiobutton(dialog, text="For this mat only (recommended)", variable=scope, value="mat").pack(anchor="w", padx=10, pady=(8, 0))
        ttk.Radiobutton(dialog, text="As the default for every mat on this server", variable=scope, value="site").pack(anchor="w", padx=10)
        reason, pin, error = tk.StringVar(), tk.StringVar(), tk.StringVar()
        form = ttk.Frame(dialog, padding=10)
        form.pack(fill=tk.X)
        ttk.Label(form, text="Reason (optional)").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(form, textvariable=reason, width=44).grid(row=0, column=1, padx=8)
        ttk.Label(form, text="Your PIN").grid(row=1, column=0, sticky="w", pady=2)
        pin_entry = ttk.Entry(form, textvariable=pin, show="*", width=20)
        pin_entry.grid(row=1, column=1, sticky="w", padx=8)
        ttk.Label(dialog, textvariable=error, padding=(10, 0)).pack(anchor="w")

        def send():
            if not pin.get():
                error.set("Enter your PIN.")
                return
            chip, why, secret = (mat if scope.get() == "mat" else None), reason.get().strip()[:200], pin.get()
            pin.set("")
            dialog.destroy()
            self.status_var.set("Sending ...")

            def done(result):
                ok, data = result
                if ok and isinstance(data, dict):
                    self.status_var.set(f"Saved by {data.get('user')}: settings version {data.get('stamp')}")
                    self._refresh_marker()
                else:
                    self.status_var.set(f"Not saved: {data}")

            self._run(lambda: ServerClient(url).put_config(chip, changes, secret, why), done)

        buttons = ttk.Frame(dialog, padding=10)
        buttons.pack()
        ttk.Button(buttons, text="Send", command=send).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=4)
        dialog.bind("<Return>", lambda _: send())
        dialog.bind("<Escape>", lambda _: dialog.destroy())
        pin_entry.focus_set()
        dialog.grab_set()

    def _pull(self):
        def then(mat, url, page):
            try:
                settings = analysis_sync.settings_from_server(page)
            except ValueError as error:
                self.status_var.set(f"The server's settings are not a valid preset here: {error}")
                return
            differing = [row for row in analysis_sync.compare(self.app.current_settings(), page) if row["differs"]]
            if not differing:
                self.status_var.set("Nothing to get: this desktop's analysis settings already match the server's.")
                return
            names = ", ".join(row["label"] for row in differing[:6]) + (" ..." if len(differing) > 6 else "")
            if not messagebox.askyesno("Get analysis settings", f"Replace {len(differing)} analysis setting(s) here with "
                                       f"the server's for this mat?\n\n{names}", parent=self.frame):
                self.status_var.set("Nothing changed.")
                return
            try:
                self.app.apply_engineering_settings(settings, f"Server {page.get('stamp', '')}".strip())
            except (ValueError, KeyError, TypeError) as error:
                self.status_var.set(f"Could not apply them: {error}")
                return
            self.status_var.set(f"Applied the server's analysis settings (version {page.get('stamp', '?')}).")

        self._analysis_page(then)

    def _preview(self):
        def then(mat, url, page):
            rows = analysis_sync.compare(self.app.current_settings(), page)
            changes = analysis_sync.changes_to_push(rows)
            if not changes:
                self.status_var.set("Nothing differs from the server, so a preview would show the same thing twice.")
                return
            options = {"parent": self.frame, "title": "Pick a recording to replay",
                       "filetypes": [("Recordings", "*.json"), ("All files", "*.*")]}
            if RECORDINGS_DIR.exists():
                options["initialdir"] = str(RECORDINGS_DIR)
            path = filedialog.askopenfilename(**options)
            if not path:
                self.status_var.set("Preview cancelled.")
                return
            try:
                frames, times = load_session(path, with_timestamps=True)
            except (OSError, ValueError, KeyError, TypeError) as error:
                self.status_var.set(f"Could not read the recording: {error}")
                return
            self.status_var.set("Reading the mat's calibration from the server ...")

            def got_profile(result):
                ok, data = result
                profile = data.get("profile") if ok and isinstance(data, dict) else None
                self._start_preview(mat, page, changes, frames, times, profile, Path(path).name)

            self._run(lambda: ServerClient(url).get_profile(mat), got_profile)

        self._analysis_page(then)

    def _start_preview(self, mat, page, changes, frames, times, profile, name):
        """Replay the recording twice through the server's own analysis, in small steps on this (the main) thread:
        the server's engine briefly sets the global grid size, which must not overlap the live analysis"""
        try:
            before = analysis_sync.server_values(page)
            after = analysis_sync.values_after_push(page, changes)
            replays = [analysis_sync.Replay(frames, times, before, profile, max_s=PREVIEW_MAX_S, name="Now"),
                       analysis_sync.Replay(frames, times, after, profile, max_s=PREVIEW_MAX_S, name="With these settings")]
        except (ValueError, KeyError, TypeError) as error:
            self.status_var.set(f"Could not start the preview: {error}")
            return
        window = tk.Toplevel(self.frame)
        window.title("Preview")
        window.transient(self.frame.winfo_toplevel())
        ttk.Label(window, padding=12, text=f"Replaying {name} through the server's analysis "
                                           f"(the first {PREVIEW_MAX_S // 60} minutes, twice) ...").pack()
        bar = ttk.Progressbar(window, length=360, maximum=100)
        bar.pack(padx=12)
        cancelled = []

        def cancel():
            cancelled.append(True)
            window.destroy()
            self.status_var.set("Preview cancelled.")

        ttk.Button(window, text="Cancel", command=cancel).pack(pady=12)
        window.protocol("WM_DELETE_WINDOW", cancel)
        state = {"index": 0}

        def step():
            if cancelled or not window.winfo_exists():
                return
            replay = replays[state["index"]]
            try:
                fraction = replay.step(4)
            except (ValueError, KeyError, TypeError, ArithmeticError) as error:
                window.destroy()
                self.status_var.set(f"The preview stopped: {error}")
                return
            bar["value"] = (state["index"] + fraction) / len(replays) * 100
            if replay.done():
                state["index"] += 1
            if state["index"] >= len(replays):
                window.destroy()
                self.status_var.set("Preview done.")
                self._show_preview(mat, changes, [replay.result() for replay in replays], name)
                return
            window.after(1, step)

        window.after(1, step)

    def _show_preview(self, mat, changes, results, name):
        before, after = results
        window = tk.Toplevel(self.frame)
        window.title(f"Preview: {mat}")
        window.geometry("680x460")
        ttk.Label(window, padding=8, justify=tk.LEFT, text=f"Recording: {name}\n" + "\n".join(
            analysis_sync.summary_lines(before, after))).pack(side=tk.TOP, anchor="w")
        ttk.Label(window, padding=(8, 0), wraplength=650, justify=tk.LEFT, text=(
            "Settings tested: " + ", ".join(analysis_sync.label(key) for key in changes))).pack(side=tk.TOP, anchor="w")
        ttk.Label(window, padding=8, wraplength=650, justify=tk.LEFT, text=(
            "The replay uses the server's own analysis and alert rules and this mat's calibration on the server. "
            "Nothing was sent to the server.")).pack(side=tk.BOTTOM, anchor="w")
        table = ttk.Treeview(window, columns=("run", "kind", "raised", "cleared"), show="headings")
        for key, title, width in (("run", "Run", 170), ("kind", "Alert", 110), ("raised", "Raised after", 120), ("cleared", "Cleared after", 120)):
            table.heading(key, text=title)
            table.column(key, width=width, anchor="w")
        for result in (before, after):
            for alert in result["alerts"]:
                table.insert("", tk.END, values=(
                    result["name"], alert["kind"].replace("_", " "), analysis_sync.format_seconds(alert["t_raised"]),
                    "still open" if alert["t_cleared"] is None else analysis_sync.format_seconds(alert["t_cleared"])))
        if not before["alerts"] and not after["alerts"]:
            table.insert("", tk.END, values=("", "no alerts in either run", "", ""))
        table.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8)
