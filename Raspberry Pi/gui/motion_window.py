"""Movement components and before/after reposition measurements."""

import tkinter as tk
from tkinter import ttk
from datetime import datetime


def _time_label(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S") if timestamp > 1_000_000_000 else f"{timestamp:.1f}s"


class MotionWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Movement and reposition")
        self.window.geometry("900x560")
        self.score_var = tk.StringVar()
        ttk.Label(self.window, textvariable=self.score_var, padding=8).pack(fill=tk.X)
        ttk.Button(self.window, text="Annotate known reposition...",
                   command=lambda: self.app._open_annotation("Known reposition")).pack(anchor="w", padx=8)
        tabs = ttk.Notebook(self.window)
        tabs.pack(fill=tk.BOTH, expand=True)
        movement_tab = ttk.Frame(tabs)
        reposition_tab = ttk.Frame(tabs)
        timeline_tab = ttk.Frame(tabs)
        tabs.add(movement_tab, text="Movement events")
        tabs.add(reposition_tab, text="Repositions")
        tabs.add(timeline_tab, text="Timeline")
        self.movements = tk.Listbox(movement_tab)
        self.movements.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.repositions = tk.Listbox(reposition_tab, height=8)
        self.repositions.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.repositions.bind("<<ListboxSelect>>", lambda _event: self._details())
        self.details_var = tk.StringVar(value="Select a reposition")
        ttk.Label(reposition_tab, textvariable=self.details_var, wraplength=860,
                  padding=8).pack(fill=tk.X)
        ttk.Button(reposition_tab, text="Show after - before on main heatmap",
                   command=self._show_difference).pack(anchor="w", padx=8, pady=6)
        self.timeline = tk.Listbox(timeline_tab)
        self.timeline.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.timeline.bind("<<ListboxSelect>>", lambda _event: self._timeline_details())
        self.timeline_detail_var = tk.StringVar(value="Select an event")
        ttk.Label(timeline_tab, textvariable=self.timeline_detail_var,
                  wraplength=860, padding=8).pack(fill=tk.X)
        self.refresh()

    def refresh(self):
        if not self.window.winfo_exists():
            return
        score = self.app.motion.last_score
        self.score_var.set(
            f"{score['category']} | score {score['score']:.2f} = max(map change {score['map_change']:.2f}, "
            f"CoP travel {score['cop_cells']:.2f} cells / scale, area change {score['area_change']:.2f})")
        self.movements.delete(0, tk.END)
        for event in self.app.motion.movements:
            self.movements.insert(tk.END,
                f"{_time_label(event['timestamp'])} | {event['category']} | score {event['score']:.2f} | "
                f"CoP {event['cop_cells']:.1f} cells | area {event['area_change']:.2f}")
        selection = self.repositions.curselection()
        self.repositions.delete(0, tk.END)
        for record in self.app.motion.repositions:
            self.repositions.insert(tk.END,
                f"{_time_label(record['timestamp'])} | redistribution {record['redistribution']:.2f} | "
                f"movement {record['movement']['score']:.2f}")
        if selection and selection[0] < self.repositions.size():
            self.repositions.selection_set(selection[0])
        timeline_selection = self.timeline.curselection()
        self.timeline.delete(0, tk.END)
        for event in self.app.timeline.events[-200:]:
            self.timeline.insert(tk.END,
                f"{_time_label(event['timestamp'])} | {event['kind'].replace('_', ' ')} | {event.get('note', '')}")
        if timeline_selection and timeline_selection[0] < self.timeline.size():
            self.timeline.selection_set(timeline_selection[0])
        self._details()

    def _selected(self):
        selection = self.repositions.curselection()
        records = list(self.app.motion.repositions)
        return records[selection[0]] if selection and selection[0] < len(records) else None

    def _details(self):
        record = self._selected()
        if record is None:
            self.details_var.set("Select a reposition")
            return
        before, after = record["before"], record["after"]
        def pair(key, unit=""):
            first, second = before[key], after[key]
            if first is None or second is None:
                return "-"
            return f"{first:.1f} → {second:.1f}{unit}"
        self.details_var.set(
            f"Peak {pair('peak_kpa', ' kPa')} | mean contact {pair('mean_kpa', ' kPa')} | "
            f"contact {pair('contact_cells', ' cells')} | "
            f"contact area {pair('contact_area_m2', ' m²')} | "
            f"high-pressure area {pair('high_pressure_cells', ' cells')}\n"
            f"Hotspots {pair('hotspot_count')} | persistent {pair('persistent_count')} | "
            f"max burden {pair('max_burden')} | exposure {pair('exposure', ' kPa·min')} | "
            f"hotspot exposure rate {pair('hotspot_exposure_rate', ' kPa')}\n"
            f"Left load {pair('left_percent', '%')} | upper load {pair('upper_percent', '%')} | "
            f"CoP travel {record['cop_displacement_cells']} cells")

    def _show_difference(self):
        record = self._selected()
        if record is not None:
            self.app.show_reposition_difference(record)

    def _timeline_details(self):
        selection = self.timeline.curselection()
        events = self.app.timeline.events[-200:]
        if not selection or selection[0] >= len(events):
            self.timeline_detail_var.set("Select an event")
            return
        event = events[selection[0]]
        payload = event.get("payload")
        if event["kind"] in ("calibration_changed", "calibration_loaded"):
            detail = "Calibration snapshot stored with this event"
        elif event["kind"] == "tare_captured":
            detail = "Tare grid stored with this event"
        else:
            detail = str(payload) if payload is not None else event.get("note", "")
        self.timeline_detail_var.set(detail)
