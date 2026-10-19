"""Expression builder: type a formula over the signals and watch the result on its own heatmap."""

import tkinter as tk
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import app_settings
from gui import theme
from gui.page import make_window
from processing.expressions import EXAMPLES, compile_expression, variables
from processing.signals import SIGNALS


class ExpressionWindow:
    def __init__(self, parent, app):
        self.app = app
        self.expression = None
        self.window = make_window(parent)
        self.window.title("Expression")
        self.window.geometry("820x700")
        ttk.Label(self.window, wraplength=800, padding=(8, 6), text=(
            "Write your own formula over the signals below, for example  pressure * exposure_15 / 300.  Use + - * / ** %, "
            "comparisons (> < >= <= == !=), and / or, 'a if cond else b', and abs, sqrt, log, exp, min, max, clip, where. "
            "Double-click a name to insert it. An engineering experiment, not a validated score.")
                  ).pack(side=tk.TOP, fill=tk.X)

        row = ttk.Frame(self.window, padding=(8, 0))
        row.pack(fill=tk.X)
        self.text_var = tk.StringVar(value=app_settings.expression() or EXAMPLES[1])
        self.entry = ttk.Entry(row, textvariable=self.text_var, font=("Consolas", 11))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", lambda _event: self.apply())
        ttk.Button(row, text="Apply", command=self.apply).pack(side=tk.LEFT, padx=4)
        examples = ttk.Combobox(row, values=EXAMPLES, state="readonly", width=14)
        examples.set("Examples")
        examples.pack(side=tk.LEFT)
        examples.bind("<<ComboboxSelected>>", lambda _event: (self.text_var.set(examples.get()), self.apply()))
        self.message_var = tk.StringVar()
        self.message = ttk.Label(self.window, textvariable=self.message_var, padding=(8, 2))
        self.message.pack(fill=tk.X)

        body = ttk.Frame(self.window)
        body.pack(fill=tk.BOTH, expand=True)
        self.names = ttk.Treeview(body, columns=("unit", "kind"), show="tree headings", height=8)
        self.names.heading("#0", text="Name")
        self.names.heading("unit", text="Unit")
        self.names.heading("kind", text="Kind")
        self.names.column("#0", width=150)
        self.names.column("unit", width=60, anchor="center")
        self.names.column("kind", width=50, anchor="center")
        for name, (key, minutes) in variables().items():
            signal = SIGNALS[key]
            self.names.insert("", tk.END, iid=name, text=name,
                              values=(signal.unit, "grid" if signal.level == "cell" else "number"))
        self.names.bind("<Double-1>", self._insert_name)
        self.names.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=4)
        self.figure = theme.figure(figsize=(6, 4.5))
        self.canvas = FigureCanvasTkAgg(self.figure, master=body)
        self.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.apply()

    def _insert_name(self, _event):
        name = self.names.focus()
        if name:
            self.entry.insert(tk.INSERT, name)
            self.entry.focus_set()

    def apply(self):
        """Check the formula; a bad one keeps the previous result on screen and says why"""
        text = self.text_var.get()
        try:
            self.expression = compile_expression(text)
        except ValueError as error:
            self.message_var.set(str(error))
            self.message.configure(foreground=theme.palette()["bad"])
            return
        self.message_var.set("")
        try:
            app_settings.save_expression(text.strip())
        except OSError:
            pass  # the formula just is not remembered
        self.refresh()

    def refresh(self):
        if not self.window.winfo_exists() or self.expression is None:
            return
        value = self.expression.evaluate(self.app._index_context()) if self.app.frame is not None else None
        self.figure.clear()
        axes = self.figure.add_subplot()
        title = self.expression.text
        if value is None:
            axes.set_title(f"{title}\nno pressure data yet")
        elif isinstance(value, float):
            axes.axis("off")
            axes.text(0.5, 0.5, "-" if np.isnan(value) else f"{value:.4g}", ha="center", va="center",
                      fontsize=40, color=theme.palette()["ink"])
            axes.set_title(title)
        else:
            finite = value[np.isfinite(value)]
            low, high = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
            image = axes.imshow(value, cmap=theme.heatmap_cmap(), vmin=low, vmax=high if high > low else low + 1,
                                aspect="auto")
            self.figure.colorbar(image, ax=axes, label="Formula value")
            axes.set_title(f"{title}\nmin {low:.4g}   max {high:.4g}")
        self.canvas.draw_idle()
