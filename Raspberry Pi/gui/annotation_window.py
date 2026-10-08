"""Manual engineering annotations saved on the session timeline."""

import tkinter as tk
from tkinter import ttk

ANNOTATION_TYPES = (
    "Load applied", "Load removed", "Known reposition", "Known hotspot",
    "Known posture", "Calibration weight applied", "Material changed",
    "Test started", "Test stopped", "Note",
)


class AnnotationWindow:
    def __init__(self, parent, app, initial_type="Note"):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Add experiment annotation")
        self.window.geometry("450x255")
        panel = ttk.Frame(self.window, padding=12)
        panel.pack(fill=tk.BOTH, expand=True)
        self.type_var = tk.StringVar(value=initial_type)
        self.note_var = tk.StringVar()
        self.before_var = tk.StringVar()
        self.after_var = tk.StringVar()
        ttk.Label(panel, text="Type:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(panel, textvariable=self.type_var, values=ANNOTATION_TYPES,
                     state="readonly", width=28).grid(row=0, column=1, sticky="w")
        ttk.Label(panel, text="Description:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(panel, textvariable=self.note_var, width=38).grid(row=1, column=1, sticky="w")
        ttk.Label(panel, text="Before note:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(panel, textvariable=self.before_var, width=38).grid(row=2, column=1, sticky="w")
        ttk.Label(panel, text="After note:").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(panel, textvariable=self.after_var, width=38).grid(row=3, column=1, sticky="w")
        self.roi_var = tk.StringVar()
        ttk.Label(panel, textvariable=self.roi_var, wraplength=400).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Button(panel, text="Add marker", command=self._save).grid(row=5, column=1, sticky="e")
        self._update_roi_note()
        self.type_var.trace_add("write", lambda *_: self._update_roi_note())

    def _update_roi_note(self):
        if self.type_var.get() == "Known hotspot":
            self.roi_var.set("Uses the ROI currently applied in the ROI window" if self.app.roi is not None
                             else "Apply an ROI in the ROI window first")
        else:
            self.roi_var.set("Before/after notes are optional; useful for a known reposition")

    def _save(self):
        kind = self.type_var.get()
        if kind == "Known hotspot" and self.app.roi is None:
            self.roi_var.set("Apply an ROI in the ROI window first")
            return
        self.app.add_annotation(kind, self.note_var.get(), self.before_var.get(), self.after_var.get())
        self.window.destroy()
