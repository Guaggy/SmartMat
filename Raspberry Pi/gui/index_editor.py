"""Table editor for user-defined index definitions (Engineering window > Indices)."""

import copy
import tkinter as tk
from tkinter import ttk

from processing.indices import REDUCERS, REGIONS, validate_indices
from processing.signals import SIGNALS, WINDOWS_MIN

SOURCE_PREFIX = "index: "
TERM_COLUMNS = ("input", "window", "reducer", "region", "reference", "weight", "inverted")


def _window_text(minutes):
    return "Session" if minutes is None else f"{minutes} min"


class IndexEditor:
    def __init__(self, parent, definitions):
        self.definitions = []
        self.current = None  # position of the index being edited
        self.status_var = tk.StringVar()

        left = ttk.Frame(parent)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.index_list = tk.Listbox(left, height=12, width=26, exportselection=False)
        self.index_list.pack(fill=tk.Y, expand=True)
        self.index_list.bind("<<ListboxSelect>>", lambda _event: self._list_clicked())
        for text, command in (("New map index", lambda: self._add_index("map")),
                              ("New summary index", lambda: self._add_index("summary")),
                              ("Delete index", self._delete_index)):
            ttk.Button(left, text=text, command=command).pack(fill=tk.X, pady=2)

        right = ttk.Frame(parent)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        header = ttk.Frame(right)
        header.pack(fill=tk.X)
        self.name_var, self.threshold_var, self.near_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.layer_var = tk.StringVar()
        for label, variable, width in (("Name", self.name_var, 22), ("Threshold", self.threshold_var, 7),
                                       ("Near margin (0-1)", self.near_var, 7)):
            ttk.Label(header, text=label).pack(side=tk.LEFT)
            ttk.Entry(header, textvariable=variable, width=width).pack(side=tk.LEFT, padx=(3, 10))
        ttk.Label(header, textvariable=self.layer_var).pack(side=tk.LEFT)

        self.terms = ttk.Treeview(right, columns=TERM_COLUMNS, show="headings", height=6)
        for column, width in zip(TERM_COLUMNS, (190, 70, 105, 55, 80, 60, 65)):
            self.terms.heading(column, text=column.capitalize())
            self.terms.column(column, width=width, anchor="center")
        self.terms.pack(fill=tk.X, pady=6)

        form = ttk.Frame(right)
        form.pack(fill=tk.X)
        self.input_var, self.window_var = tk.StringVar(), tk.StringVar(value="Session")
        self.reducer_var, self.region_var = tk.StringVar(value="peak"), tk.StringVar(value="mat")
        self.reducer_value_var = tk.StringVar(value="1.0")
        self.reference_var, self.weight_var = tk.StringVar(), tk.StringVar(value="1.0")
        self.inverted_var = tk.BooleanVar(value=False)
        self.input_menu = ttk.Combobox(form, textvariable=self.input_var, state="readonly", width=24)
        self.input_menu.bind("<<ComboboxSelected>>", lambda _event: self._input_chosen())
        widgets = (
            ("Signal / map index", self.input_menu),
            ("Window", ttk.Combobox(form, textvariable=self.window_var, state="readonly", width=9,
                                    values=[_window_text(minutes) for minutes in WINDOWS_MIN])),
            ("Reduce by (summary)", ttk.Combobox(form, textvariable=self.reducer_var, state="readonly",
                                                 width=14, values=REDUCERS)),
            ("Fraction above", ttk.Entry(form, textvariable=self.reducer_value_var, width=7)),
            ("Over", ttk.Combobox(form, textvariable=self.region_var, state="readonly", width=6,
                                  values=REGIONS)),
            ("Reference (= 1.0)", ttk.Entry(form, textvariable=self.reference_var, width=9)),
            ("Weight", ttk.Entry(form, textvariable=self.weight_var, width=6)),
        )
        for row, (label, widget) in enumerate(widgets):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
            widget.grid(row=row, column=1, sticky="w", padx=6)
        ttk.Checkbutton(form, text="Inverted (more of this lowers the index)",
                        variable=self.inverted_var).grid(row=len(widgets), column=0, columnspan=2, sticky="w")
        buttons = ttk.Frame(right)
        buttons.pack(fill=tk.X, pady=6)
        ttk.Button(buttons, text="Add term", command=self._add_term).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Remove selected term", command=self._remove_term).pack(side=tk.LEFT, padx=6)
        ttk.Label(right, textvariable=self.status_var, wraplength=560).pack(fill=tk.X)
        self.set_definitions(definitions)

    # ---- whole set

    def set_definitions(self, definitions):
        self.definitions = copy.deepcopy(definitions)
        self.current = None
        self._refresh_list()
        self._select(0 if self.definitions else None)

    def get_definitions(self):
        """The edited definitions, validated (raises ValueError naming the index)"""
        self._store_header()
        return validate_indices(self.definitions)

    # ---- index list

    def _refresh_list(self):
        self.index_list.delete(0, tk.END)
        for definition in self.definitions:
            self.index_list.insert(tk.END, f"{definition['name']}  [{definition['layer']}]")

    def _list_clicked(self):
        chosen = self.index_list.curselection()
        if chosen and chosen[0] != self.current:
            self._store_header()
            self._refresh_list()
            self._select(chosen[0])

    def _store_header(self):
        if self.current is not None:
            self.definitions[self.current].update(
                name=self.name_var.get().strip(), threshold=self.threshold_var.get(),
                near_fraction=self.near_var.get())

    def _select(self, position):
        self.current = position
        self.terms.delete(*self.terms.get_children())
        if position is None:
            for variable in (self.name_var, self.threshold_var, self.near_var, self.layer_var):
                variable.set("")
            self.input_menu.configure(values=[])
            return
        definition = self.definitions[position]
        self.index_list.selection_clear(0, tk.END)
        self.index_list.selection_set(position)
        self.name_var.set(definition["name"])
        self.threshold_var.set(str(definition["threshold"]))
        self.near_var.set(str(definition["near_fraction"]))
        self.layer_var.set(f"Layer: {definition['layer']}")
        for term in definition["terms"]:
            self.terms.insert("", tk.END, values=self._term_row(term))
        if definition["layer"] == "map":
            choices = [name for name, signal in SIGNALS.items() if signal.level == "cell"]
        else:
            choices = list(SIGNALS) + [SOURCE_PREFIX + item["name"] for item in self.definitions
                                       if item["layer"] == "map"]
        self.input_menu.configure(values=choices)
        self.input_var.set(choices[0])
        self._input_chosen()

    def _add_index(self, layer):
        self._store_header()
        taken = {definition["name"] for definition in self.definitions}
        name = next(f"New {layer} index {number}" for number in range(1, len(taken) + 2)
                    if f"New {layer} index {number}" not in taken)
        self.definitions.append({"name": name, "layer": layer, "threshold": 1.0,
                                 "near_fraction": 0.8, "terms": []})
        self._refresh_list()
        self._select(len(self.definitions) - 1)

    def _delete_index(self):
        if self.current is None:
            return
        del self.definitions[self.current]
        self.current = None
        self._refresh_list()
        self._select(0 if self.definitions else None)

    # ---- terms of the selected index

    @staticmethod
    def _term_row(term):
        return (SOURCE_PREFIX + term["source"] if "source" in term else term["signal"],
                "-" if "source" in term else _window_text(term.get("window_min")),
                term.get("reducer", "-") + (f" > {term['reducer_value']:g}" if "reducer_value" in term else ""),
                term.get("region", "-"), f"{float(term['reference']):g}", f"{float(term['weight']):g}",
                "yes" if term.get("inverted") else "no")

    def _input_chosen(self):
        """Pre-fill the reference with the signal's default"""
        choice = self.input_var.get()
        self.reference_var.set("1.0" if choice.startswith(SOURCE_PREFIX) else f"{SIGNALS[choice].reference:g}")
        if choice.startswith(SOURCE_PREFIX) or not SIGNALS[choice].windowed:
            self.window_var.set("Session")

    def _add_term(self):
        if self.current is None:
            self.status_var.set("Create or select an index first")
            return
        definition = self.definitions[self.current]
        choice = self.input_var.get()
        try:
            term = {"reference": float(self.reference_var.get()), "weight": float(self.weight_var.get()),
                    "inverted": self.inverted_var.get()}
            if choice.startswith(SOURCE_PREFIX):
                term["source"] = choice[len(SOURCE_PREFIX):]
                reduced = True
            else:
                text = self.window_var.get()
                term["signal"] = choice
                term["window_min"] = (None if text == "Session" or not SIGNALS[choice].windowed
                                      else int(text.split()[0]))
                reduced = definition["layer"] == "summary" and SIGNALS[choice].level == "cell"
            if reduced:
                term.update(reducer=self.reducer_var.get(), region=self.region_var.get())
                if term["reducer"] == "fraction_above":
                    term["reducer_value"] = float(self.reducer_value_var.get())
        except ValueError:
            self.status_var.set("Reference, weight and fraction-above value must be numbers")
            return
        definition["terms"].append(term)
        self.terms.insert("", tk.END, values=self._term_row(term))
        self.status_var.set("Term added; choose Apply values to use the new definitions")

    def _remove_term(self):
        chosen = self.terms.selection()
        if self.current is None or not chosen:
            return
        del self.definitions[self.current]["terms"][self.terms.index(chosen[0])]
        self.terms.delete(chosen[0])
