"""Engineering > Connection > "Passport on the mat": the calibration kept on the mat's own ESP32 (ESP32_China/PASSPORT.md).

Show what the mat carries, use its custom or factory calibration here, or save this mat's current calibration to its
custom slot (a backup, or before shipping it). Talks to the MQTT broker directly, so it works without a server. The
logic is passport_sync.py; this file is only the window. Every network call runs in a thread; Tk is only touched from the
main thread. The factory slot is not written from here (that needs the service key: tools/passport_tool.py).
"""

import threading
import tkinter as tk
from tkinter import messagebox, ttk

import config
import passport_sync
from gui.server_panel import apply_profile_to_app
from processing import calibration

NO_MAT_HINT = "Connect a mat over MQTT to see or change the passport it carries."


class PassportPanel:
    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.LabelFrame(parent, text="Passport on the mat", padding=8)
        self.status_var = tk.StringVar(value="")
        self.lines_var = tk.StringVar(value="")
        self.note_var = tk.StringVar(value="")
        self.busy = False
        ttk.Label(self.frame, wraplength=760, justify=tk.LEFT, text=(
            "The mat's own memory keeps its calibration, so it can travel with the mat: save it here before shipping, "
            "or use it again later. It does not need the server.")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        bar = ttk.Frame(self.frame)
        bar.grid(row=1, column=0, columnspan=4, sticky="w")
        self.buttons = [ttk.Button(bar, text=text, command=command) for text, command in (
            ("Show", self._show), ("Use custom", lambda: self._use("custom")), ("Use factory", lambda: self._use("factory")),
            ("Save current to mat", self._save))]
        for button in self.buttons:
            button.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(self.frame, text="Note").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(self.frame, textvariable=self.note_var, width=40).grid(row=2, column=1, sticky="w", padx=8)
        for row, variable in ((3, self.lines_var), (4, self.status_var)):
            ttk.Label(self.frame, textvariable=variable, wraplength=760, justify=tk.LEFT).grid(row=row, column=0, columnspan=4, sticky="w")
        self._tick()

    def _mat(self):
        return self.app._profile_mat_id()

    def _tick(self):
        if not self.frame.winfo_exists():
            return
        self._set_states()
        self.frame.after(1000, self._tick)

    def _set_states(self):
        enabled = bool(self._mat()) and not self.busy
        for button in self.buttons:
            button.state(["!disabled"] if enabled else ["disabled"])
        if not self._mat():
            self.status_var.set(NO_MAT_HINT)

    def _run(self, work, done):
        """work(link) in a thread (it connects to the broker first); done(result) on the main thread"""
        self.busy = True
        self._set_states()

        def thread():
            ok, link = passport_sync.connect()
            try:
                result = work(link) if ok else (False, link)
            finally:
                if ok:
                    link.close()
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

        self.status_var.set("Asking the mat ...")
        threading.Thread(target=thread, daemon=True).start()

    def _show(self):
        mat = self._mat()

        def done(result):
            ok, data = result
            self.lines_var.set("\n".join(data) if ok else "")
            self.status_var.set("" if ok else data)

        self._run(lambda link: passport_sync.slot_lines(link, mat), done)

    def _use(self, slot):
        mat = self._mat()
        shape = (config.TOTAL_ROWS, config.TOTAL_COLS)

        def done(result):
            ok, data = result
            if not ok:
                self.status_var.set(data)
            elif self._mat() == mat and messagebox.askyesno(
                    "Use passport", f"Replace this mat's tare and calibration here with its {slot} passport "
                                    f"(version {data['version']}, {data['written_by'] or 'unknown'})?", parent=self.frame):
                self.status_var.set(apply_profile_to_app(self.app, mat, data["profile"], f"the mat's {slot} passport"))
            else:
                self.status_var.set("Nothing changed.")

        self._run(lambda link: passport_sync.fetch(link, mat, slot, shape), done)

    def _save(self):
        mat = self._mat()
        self.app._save_profile()
        profile = calibration.load_profile(mat)
        if profile is None:
            self.status_var.set("This mat has no calibration profile to save yet.")
            return
        if not messagebox.askyesno("Save to mat", "Replace the custom passport on the mat with this calibration?", parent=self.frame):
            return
        note = self.note_var.get().strip()[:120]
        by = getattr(self.app, "operator_name", "") or "desktop"

        def done(result):
            ok, data = result
            self.status_var.set(f"Saved to the mat (custom, version {data['version']})." if ok else f"Not saved: {data}")

        self._run(lambda link: passport_sync.save_custom(link, mat, profile, by, note), done)
