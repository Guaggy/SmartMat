"""Current tracked hotspots and their measured properties."""

import tkinter as tk
from tkinter import ttk


class HotspotWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Hotspots")
        self.window.geometry("850x420")
        ttk.Label(self.window, text='Lists areas of high pressure being tracked, and how long each has lasted.', wraplength=760, padding=(8, 6)).pack(side=tk.TOP, fill=tk.X)
        columns = ("id", "state", "peak", "mean", "cells", "area", "observed", "exposure", "burden")
        self.list = ttk.Treeview(self.window, columns=columns, show="headings", height=10)
        for column, width in (("id", 45), ("state", 85), ("peak", 80), ("mean", 80),
                              ("cells", 55), ("area", 80), ("observed", 85),
                              ("exposure", 95), ("burden", 85)):
            self.list.heading(column, text=column.capitalize())
            self.list.column(column, width=width, anchor="center")
        self.list.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.list.bind("<<TreeviewSelect>>", lambda _event: self._details())
        self.status_var = tk.StringVar()
        ttk.Label(self.window, textvariable=self.status_var, padding=8).pack(fill=tk.X)
        self.details_var = tk.StringVar(value="Select a hotspot")
        ttk.Label(self.window, textvariable=self.details_var, wraplength=820, padding=8).pack(fill=tk.X)
        ttk.Button(self.window, text="Tracking debug...", command=self._open_debug).pack(anchor="w", padx=8, pady=4)
        self.debug_window = None
        self.refresh()

    def refresh(self):
        if not self.window.winfo_exists():
            return
        self.status_var.set("Current valid pressure" if self.app.hotspots.data_valid else
                            "Waiting for valid pressure after a gap or calibration change")
        selected = self.list.selection()
        selected_id = selected[0] if selected else None
        for item in self.list.get_children():
            self.list.delete(item)
        for track in sorted(self.app.hotspots.tracks.values(), key=lambda item: item["id"]):
            self.list.insert("", tk.END, iid=str(track["id"]), values=(
                track["id"], track["state"], f"{track['peak_kpa']:.1f}",
                f"{track['mean_kpa']:.1f}", track["cell_count"],
                "-" if track["area_cm2"] is None else f"{track['area_cm2']:.1f}",
                f"{track['total_active_s']:.1f}s", f"{track['total_exposure']:.2f}",
                f"{track['burden']:.2f}"))
        if selected_id in self.list.get_children():
            self.list.selection_set(selected_id)
        self._details()
        self._debug_details()

    def _details(self):
        selected = self.list.selection()
        if not selected:
            self.details_var.set("Select a hotspot; area needs configured cell dimensions")
            return
        track = self.app.hotspots.tracks.get(int(selected[0]))
        if track is None:
            return
        row, col = track["centroid"]
        force = "-" if track["force_n"] is None else f"{track['force_n']:.1f} N"
        self.details_var.set(
            f"Hotspot {track['id']} at row {row:.1f}, col {col:.1f} | "
            f"age {track['last_seen'] - track['first_seen']:.1f}s | "
            f"prior duration {'unknown' if track['started_before_session'] else 'observed from creation'} | "
            f"peak observed {track['peak_observed']:.1f} kPa | max size {track['max_cells']} cells | "
            f"force {force} | exposure of current cells {track['exposure_kpa_min']:.2f} kPa·min | "
            f"track exposure {track['total_exposure']:.2f} kPa·min | max burden {track['max_burden']:.2f} | "
            f"{track['relief_state']} | time since relief {track['since_relief_s']:.1f}s | "
            f"total active {track['total_active_s']:.1f}s")

    def _open_debug(self):
        if self.debug_window is not None and self.debug_window.winfo_exists():
            self.debug_window.lift()
        else:
            self.debug_window = tk.Toplevel(self.window)
            self.debug_window.title("Hotspot tracking debug")
            self.debug_window.geometry("500x270")
            self.debug_var = tk.StringVar()
            ttk.Label(self.debug_window, textvariable=self.debug_var,
                      wraplength=470, padding=12).pack(fill=tk.BOTH, expand=True)
        self._debug_details()

    def _debug_details(self):
        if self.debug_window is None or not self.debug_window.winfo_exists():
            return
        selected = self.list.selection()
        track = self.app.hotspots.tracks.get(int(selected[0])) if selected else None
        if track is None:
            self.debug_var.set("Select an active or relieved hotspot")
            return
        self.debug_var.set(
            f"Hotspot {track['id']} | cells {sorted(track['cells'])}\n"
            f"Centroid row {track['centroid'][0]:.2f}, col {track['centroid'][1]:.2f}\n"
            f"Activate ≥ {self.app.hotspots.activate_kpa:.1f} kPa; "
            f"deactivate < {self.app.hotspots.deactivate_kpa:.1f} kPa\n"
            f"Matched previous ID {track['matched_previous_id']} | "
            f"overlap {track['previous_overlap_cells']} cells | {track['tracking_decision']}\n"
            f"Observed active {track['active_s']:.1f}s / persistence {self.app.hotspots.persistence_s:.1f}s | "
            f"relief {track['relieved_s']:.1f}s / end {self.app.hotspots.end_relief_s:.1f}s\n"
            f"Prior duration {'unknown' if track['started_before_session'] else 'observed from creation'}")
