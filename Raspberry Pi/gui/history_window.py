"""Rough history of one mat from the SmartMat server: a heatmap you can scrub or play, an alert-marker strip, the
snapshot's numbers, an Instant / 5-min peak toggle and a Save button (recording JSON for the deep-analysis tools).

Opened from Engineering > Connection > SmartMat server > History. The logic (fetching, stepping, numbers, saving) is
in client/history_sync.py; this is only the window. Plain ttk widgets (the theme styles them). The server is read in a
thread and handed back with after(); Tk is only touched from the main thread. Nothing redraws while paused: one
after() timer runs only while playing, and a frame is one imshow set_data plus one draw_idle.

Values are indicative: snapshots every few minutes from a rough 8-bit picture, not a measurement or a diagnosis.
"""

import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from client import history_sync
from client.server_client import ServerClient
from gui import theme
from gui.page import make_window
from processing.recording import RECORDINGS_DIR

# risk -> theme palette token (a strip under the map: how the risk went over the range)
RISK_TOKEN = {"high": "bad", "medium": "warn", "low": "ok", "none": "idle", "offline": "line"}
NOTE = ("Rough history: the server keeps a snapshot every few minutes and at each alert. Values are indicative "
        "(an estimate, not a measurement or a diagnosis).")


class HistoryWindow:
    def __init__(self, parent, url, mats, mat=None):
        """`mats` is [(chip id, label)]; `mat` the one to preselect"""
        self.url, self.mats = url, list(mats)
        self.history = self.player = None
        self.loading = False
        self.cancel = False
        self.timer = None
        self.image = self.cursor = None
        self.shown_shape = None
        self._seeking = False

        self.window = make_window(parent)
        self.window.title("Server history")
        self.window.geometry("980x640")
        self.window.protocol("WM_DELETE_WINDOW", self._close)

        self.mat_var = tk.StringVar()
        self.range_var = tk.StringVar(value=history_sync.RANGES[1][0])
        self.mode_var = tk.StringVar(value=history_sync.MODE_LABELS["instant"])
        self.speed_var = tk.StringVar(value=f"{history_sync.SPEEDS[1]} / s")
        self.status_var = tk.StringVar(value="Pick a mat and a range, then Load.")
        self.time_var = tk.StringVar(value="")
        self.play_text = tk.StringVar(value="Play")

        top = ttk.Frame(self.window, padding=(8, 8, 8, 2))
        top.pack(fill=tk.X)
        labels = [label for _, label in self.mats]
        ttk.Label(top, text="Mat").pack(side=tk.LEFT)
        self.mat_box = ttk.Combobox(top, textvariable=self.mat_var, values=labels, state="readonly", width=24)
        self.mat_box.pack(side=tk.LEFT, padx=(4, 12))
        ids = [chip for chip, _ in self.mats]
        if labels:
            self.mat_box.current(ids.index(mat) if mat in ids else 0)
        ttk.Label(top, text="Range").pack(side=tk.LEFT)
        ttk.Combobox(top, textvariable=self.range_var, values=[name for name, _ in history_sync.RANGES],
                     state="readonly", width=14).pack(side=tk.LEFT, padx=(4, 12))
        self.load_button = ttk.Button(top, text="Load", command=self._load)
        self.load_button.pack(side=tk.LEFT)
        self.save_button = ttk.Button(top, text="Save as recording...", command=self._save)
        self.save_button.pack(side=tk.RIGHT)

        ttk.Label(self.window, text=NOTE, wraplength=940, padding=(8, 0, 8, 4)).pack(fill=tk.X)

        body = ttk.Frame(self.window)
        body.pack(fill=tk.BOTH, expand=True)
        self.figure = theme.figure(figsize=(6, 5))
        self.canvas = FigureCanvasTkAgg(self.figure, master=body)
        self.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.mpl_connect("button_press_event", self._click)

        side = ttk.Frame(body, padding=8)
        side.pack(side=tk.RIGHT, fill=tk.Y)
        self.number_vars = {}
        for row, label in enumerate(("Time", "Risk", "Peak pressure", "Contact area", "Load (indicative)", "Posture",
                                     "Time since movement", "Time in position", "Hotspots")):
            ttk.Label(side, text=label).grid(row=row, column=0, sticky="nw", padx=(0, 8), pady=1)
            var = self.number_vars[label] = tk.StringVar(value="-")
            ttk.Label(side, textvariable=var, wraplength=200, justify=tk.LEFT).grid(row=row, column=1, sticky="nw", pady=1)

        controls = ttk.Frame(self.window, padding=(8, 2, 8, 2))
        controls.pack(fill=tk.X)
        self.controls = []
        self.play_button = ttk.Button(controls, textvariable=self.play_text, command=self._toggle_play, width=7)
        self.play_button.pack(side=tk.LEFT)
        self.controls.append(self.play_button)
        for text, step in (("<", -1), (">", 1)):
            button = ttk.Button(controls, text=text, width=3, command=lambda s=step: self._step(s))
            button.pack(side=tk.LEFT, padx=(4, 0))
            self.controls.append(button)
        for text, step in (("Prev alert", -1), ("Next alert", 1)):
            button = ttk.Button(controls, text=text, command=lambda s=step: self._jump_alert(s))
            button.pack(side=tk.LEFT, padx=(8, 0))
            self.controls.append(button)
        self.scale = ttk.Scale(controls, from_=0, to=1, command=self._scrubbed)
        self.scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        ttk.Label(controls, text="Speed").pack(side=tk.LEFT)
        speed = ttk.Combobox(controls, textvariable=self.speed_var, state="readonly", width=7,
                             values=[f"{s} / s" for s in history_sync.SPEEDS])
        speed.pack(side=tk.LEFT, padx=(4, 10))
        speed.bind("<<ComboboxSelected>>", self._speed_changed)
        ttk.Label(controls, text="Show").pack(side=tk.LEFT)
        mode = ttk.Combobox(controls, textvariable=self.mode_var, state="readonly", width=11,
                            values=[history_sync.MODE_LABELS[m] for m in history_sync.MODES])
        mode.pack(side=tk.LEFT, padx=4)
        mode.bind("<<ComboboxSelected>>", self._mode_changed)
        self.controls += [self.scale, speed, mode]

        ttk.Label(self.window, textvariable=self.time_var, padding=(8, 0)).pack(fill=tk.X)
        ttk.Label(self.window, textvariable=self.status_var, padding=(8, 2, 8, 8), wraplength=940).pack(fill=tk.X)
        self._set_enabled()
        self._draw_empty()

    # ---- state

    def _alive(self):
        return self.window.winfo_exists()

    def _set_enabled(self):
        has = self.history is not None and len(self.history) > 0
        for widget in self.controls:
            widget.state(["!disabled"] if has else ["disabled"])
        self.save_button.state(["!disabled"] if has and not self.loading else ["disabled"])
        self.load_button.state(["disabled"] if self.loading else ["!disabled"])
        self.load_button.configure(text="Load")

    def _selected_mat(self):
        label = self.mat_var.get()
        for chip, name in self.mats:
            if name == label:
                return chip
        return None

    def _close(self):
        self.cancel = True
        self._stop_timer()
        self.window.destroy()

    # ---- loading (thread -> main thread)

    def _load(self):
        chip = self._selected_mat()
        if chip is None or self.loading:
            self.status_var.set("Choose a mat first." if chip is None else "Already loading.")
            return
        hours = dict(history_sync.RANGES).get(self.range_var.get(), 24)
        until = time.time()
        since = until - hours * 3600
        self._pause()
        self.loading, self.cancel = True, False
        self.status_var.set("Loading history ...")
        self._set_enabled()
        client = ServerClient(self.url, timeout=15)

        def progress(count):
            self._later(lambda: self.status_var.set(f"Loading history ... {count} snapshots"))

        def thread():
            result = history_sync.fetch_range(client, chip, since, until, progress, lambda: self.cancel)
            self._later(lambda: self._loaded(chip, result))

        threading.Thread(target=thread, daemon=True).start()

    def _later(self, callback):
        try:
            self.window.after(0, callback)
        except (tk.TclError, RuntimeError):
            pass

    def _loaded(self, chip, result):
        if not self._alive():
            return
        self.loading = False
        ok, data = result
        if not ok:
            self.status_var.set(f"Could not load the history: {data}")
            self._set_enabled()
            return
        self.history = data
        mode = self._mode()
        self.player = history_sync.Player(data, mode)
        self.scale.configure(to=max(len(data) - 1, 1))
        self._set_enabled()
        if not len(data):
            self.status_var.set("No snapshots in this range (the server keeps one every few minutes while the mat is online).")
            self._draw_empty()
            return
        alerts = len(data.alert_markers())
        self.status_var.set(f"{len(data)} snapshots, {alerts} alert marker(s)"
                            + (" - the range was cut at the limit, load a shorter range for the rest." if data.truncated else "."))
        self._build_plot()
        self._show()

    # ---- drawing

    def _mode(self):
        for mode, label in history_sync.MODE_LABELS.items():
            if label == self.mode_var.get():
                return mode
        return "instant"

    def _draw_empty(self):
        self.figure.clear()
        self.image = self.cursor = self.shown_shape = None
        self.figure.add_subplot().text(0.5, 0.5, "No history loaded", ha="center", va="center")
        self.canvas.draw_idle()

    def _build_plot(self):
        """Once per load: the map, the colour bar, the risk/alert strip. Frames afterwards only change data."""
        history, palette = self.history, theme.palette()
        self.tops = {mode: history.top(mode) for mode in history_sync.MODES}   # once: a frame must not rescan the range
        self.figure.clear()
        grid = next((history.grid(i, "instant") for i in range(len(history)) if history.grid(i, "instant") is not None), None)
        grid_axes, strip = self.figure.subplots(2, 1, gridspec_kw={"height_ratios": [10, 1]})
        shape = grid.shape if grid is not None else (1, 1)
        self.image = grid_axes.imshow(np.zeros(shape), cmap=theme.heatmap_cmap(), vmin=0, vmax=self.tops["peak"], aspect="auto")
        self.unit = history.unit()
        self.figure.colorbar(self.image, ax=grid_axes, label="Pressure (kPa)" if self.unit == "kPa" else "Pressure (relative)")
        grid_axes.set_xlabel("Column")
        grid_axes.set_ylabel("Row (front at the bottom)")
        self.grid_axes = grid_axes
        self.shown_shape = shape
        n = len(history)
        colours = [palette[RISK_TOKEN[r]] for r in history.risk_strip()]
        for i, colour in enumerate(colours):
            strip.axvspan(i - 0.5, i + 0.5, color=colour, linewidth=0)
        for index, kind, _ in history.alert_markers():
            strip.plot([index], [0.5], marker="v" if kind == "raised" else "^", color=palette["ink"], markersize=6, linestyle="None")
        self.cursor = strip.axvline(0, color=palette["ink"], linewidth=2)
        strip.set_xlim(-0.5, max(n - 0.5, 0.5))
        strip.set_ylim(0, 1)
        strip.set_yticks([])
        ticks = sorted({0, n // 2, max(n - 1, 0)})
        strip.set_xticks(ticks)
        strip.set_xticklabels([time.strftime("%d %b %H:%M", time.localtime(history.snapshots[i]["t"])) for i in ticks])
        strip.set_xlabel("Risk over time (marker v = alert raised, ^ = cleared)")
        self.strip = strip
        self.figure.tight_layout()

    def _show(self):
        """The current snapshot: one set_data, the cursor, the numbers, one draw_idle"""
        player = self.player
        if player is None or self.image is None or not len(self.history):
            return
        snap = player.current()
        grid = player.grid()
        self.image.set_clim(0, self.tops[player.mode])
        if grid is None:
            self.image.set_data(np.zeros(self.shown_shape))
        else:
            if grid.shape != self.shown_shape:    # a mat that changed size inside the range: show what fits
                fitted = np.zeros(self.shown_shape)
                rows, cols = (min(a, b) for a, b in zip(grid.shape, self.shown_shape))
                fitted[:rows, :cols] = grid[:rows, :cols]
                grid = fitted
            self.image.set_data(grid)
        note = ""
        if grid is None:
            note = " (no picture: the mat was offline)"
        elif player.mode == "peak" and not self.history.has_peak(player.index):
            note = " (no 5-min peak for this snapshot, instant shown)"
        self.grid_axes.set_title(f"{history_sync.MODE_LABELS[player.mode]}{note}")
        self.cursor.set_xdata([player.index, player.index])
        for label, text in history_sync.numbers(snap):
            if label in self.number_vars:
                self.number_vars[label].set(text)
        self.time_var.set(f"Snapshot {player.index + 1} of {len(self.history)}")
        self._seeking = True
        try:
            self.scale.set(player.index)
        finally:
            self._seeking = False
        self.canvas.draw_idle()

    # ---- controls

    def _toggle_play(self):
        if self.player is None:
            return
        if self.player.playing:
            self._pause()
        elif self.player.play():
            self.play_text.set("Pause")
            self._show()
            self._schedule()

    def _pause(self):
        if self.player is not None:
            self.player.pause()
        self._stop_timer()
        self.play_text.set("Play")

    def _schedule(self):
        self._stop_timer()
        self.timer = self.window.after(self.player.delay_ms(), self._tick)

    def _stop_timer(self):
        if self.timer is not None:
            try:
                self.window.after_cancel(self.timer)
            except (tk.TclError, RuntimeError):
                pass
            self.timer = None

    def _tick(self):
        self.timer = None
        if not self._alive() or self.player is None:
            return
        if self.player.tick():
            self._show()
        if self.player.playing:
            self._schedule()
        else:
            self.play_text.set("Play")

    def _step(self, step):
        if self.player is None:
            return
        self._pause()
        self.player.seek(self.player.index + step)
        self._show()

    def _jump_alert(self, step):
        if self.player is None:
            return
        target = self.player.next_alert(step)
        if target is None:
            self.status_var.set("No further alert marker in that direction.")
            return
        self._pause()
        self.player.seek(target)
        self._show()

    def _scrubbed(self, value):
        if self._seeking or self.player is None:
            return
        index = self.player.seek(float(value))
        if index != getattr(self, "_last_scrub", None):
            self._last_scrub = index
            self._show()

    def _click(self, event):
        """A click on the risk strip jumps there"""
        if self.player is not None and event.inaxes is self.strip and event.xdata is not None:
            self._pause()
            self.player.seek(event.xdata)
            self._show()

    def _speed_changed(self, _event=None):
        if self.player is None:
            return
        self.player.speed = int(self.speed_var.get().split()[0])
        if self.player.playing:
            self._schedule()

    def _mode_changed(self, _event=None):
        if self.player is None:
            return
        self.player.set_mode(self._mode())
        self._show()

    # ---- save

    def _save(self):
        if self.history is None or not len(self.history):
            return
        RECORDINGS_DIR.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M", time.localtime(self.history.snapshots[0]["t"]))
        path = filedialog.asksaveasfilename(parent=self.window, title="Save history as a recording",
                                            initialdir=str(RECORDINGS_DIR), defaultextension=".json",
                                            initialfile=f"{self.history.mat}_history_{stamp}.json",
                                            filetypes=[("Recording", "*.json")])
        if not path:
            return
        try:
            count = history_sync.save_recording(self.history, Path(path), self.player.mode)
        except (OSError, ValueError) as error:
            messagebox.showerror("Save as recording", f"Could not save: {error}", parent=self.window)
            return
        self.status_var.set(f"Saved {count} snapshots ({history_sync.MODE_LABELS[self.player.mode]}) to {path}. "
                            "Open it as a recording source to use the analysis tools; frames are minutes apart.")
