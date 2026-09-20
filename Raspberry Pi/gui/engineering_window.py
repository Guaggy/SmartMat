"""Threshold tuning, validation, readiness, and experiment export."""

import json
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from processing.session_summary import session_summary
from processing.reanalysis import compare_recording
from processing.settings import builtin_preset, load_preset, save_preset, validate_settings

FIELDS = {
    "Contact": [("Contact threshold (kPa)", None, "contact_threshold_kpa")],
    "Hotspots": [
        ("Activation (kPa)", "hotspots", "activate_kpa"),
        ("Deactivation (kPa)", "hotspots", "deactivate_kpa"),
        ("Minimum cells", "hotspots", "min_cells"),
        ("Persistence (s)", "hotspots", "persistence_s"),
        ("Relief before end (s)", "hotspots", "end_relief_s"),
        ("Max tracking move (cells)", "hotspots", "max_move_cells"),
    ],
    "Movement": [
        ("Small score", "movement", "small_score"),
        ("Significant score", "movement", "significant_score"),
        ("Major score", "movement", "major_score"),
        ("CoP scale (cells)", "movement", "cop_scale_cells"),
        ("Movement cooldown (s)", "movement", "movement_cooldown_s"),
    ],
    "Reposition": [
        ("Movement trigger", "movement", "reposition_min_score"),
        ("Settle (s)", "movement", "settle_s"),
        ("Before window (s)", "movement", "before_s"),
        ("After window (s)", "movement", "after_s"),
        ("Minimum redistribution", "movement", "reposition_min_change"),
        ("Minimum contact cells", "movement", "reposition_min_contact_cells"),
        ("Cooldown (s)", "movement", "reposition_cooldown_s"),
        ("High-pressure threshold (kPa)", "movement", "high_pressure_kpa"),
    ],
    "Temporal": [
        ("Exposure mode", "temporal", "exposure_mode"),
        ("Exposure threshold (kPa)", "temporal", "exposure_threshold_kpa"),
        ("Burden threshold (kPa)", "temporal", "burden_load_threshold_kpa"),
        ("Burden rate", "temporal", "burden_accumulation_rate"),
        ("Recovery time (s)", "temporal", "burden_recovery_time_s"),
        ("Partial relief ratio", "temporal", "relief_partial_ratio"),
        ("Full relief ratio", "temporal", "relief_full_ratio"),
        ("Minimum relief (s)", "temporal", "relief_min_duration_s"),
        ("ROI relief fraction", "temporal", "roi_relief_fraction"),
        ("Maximum data gap (s)", "temporal", "max_gap_s"),
        ("Rolling bucket (s)", "temporal", "bucket_s"),
    ],
}

EXPERIMENT_FIELDS = (
    ("Experiment name", "experiment_name"), ("Test ID", "test_id"),
    ("Mat version", "mat_version"), ("Sensor configuration", "sensor_configuration"),
    ("Foam/support material", "support_material"),
    ("Calibration ID", "calibration_id"), ("Operator note", "operator_note"),
)


class EngineeringWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Engineering tools")
        self.window.geometry("850x680")
        tabs = ttk.Notebook(self.window)
        tabs.pack(fill=tk.BOTH, expand=True)
        settings_tab = ttk.Frame(tabs, padding=8)
        validation_tab = ttk.Frame(tabs, padding=8)
        session_tab = ttk.Frame(tabs, padding=8)
        debug_tab = ttk.Frame(tabs, padding=8)
        experiment_tab = ttk.Frame(tabs, padding=8)
        for tab, label in ((settings_tab, "Thresholds & presets"),
                           (validation_tab, "Validation"), (session_tab, "Session & export"),
                           (debug_tab, "Algorithm debug"), (experiment_tab, "Experiment info")):
            tabs.add(tab, text=label)
        self._build_settings(settings_tab)
        self._build_validation(validation_tab)
        self._build_session(session_tab)
        self._build_debug(debug_tab)
        self._build_experiment(experiment_tab)
        self.refresh()

    def _build_settings(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill=tk.X, pady=4)
        self.preset_var = tk.StringVar(value=self.app.preset_name)
        ttk.Combobox(bar, textvariable=self.preset_var, state="readonly", width=15,
                     values=["Default", "Sensitive", "Conservative", "Experimental"]).pack(side=tk.LEFT)
        ttk.Button(bar, text="Use preset", command=self._use_preset).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Save preset...", command=self._save_preset).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Load preset...", command=self._load_preset).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Apply values", command=self._apply).pack(side=tk.LEFT, padx=4)
        self.settings_status = tk.StringVar(value="Changes apply to the current analysis session")
        ttk.Label(parent, textvariable=self.settings_status, wraplength=800).pack(fill=tk.X, pady=4)
        groups = ttk.Notebook(parent)
        groups.pack(fill=tk.BOTH, expand=True)
        self.variables = {}
        for group, fields in FIELDS.items():
            page = ttk.Frame(groups, padding=15)
            groups.add(page, text=group)
            for row, (label, section, key) in enumerate(fields):
                ttk.Label(page, text=label).grid(row=row, column=0, sticky="w", pady=5)
                value = self.app.current_settings()[section][key] if section else self.app.contact_threshold_kpa
                variable = tk.StringVar(value=str(value))
                if key == "exposure_mode":
                    widget = ttk.Combobox(page, textvariable=variable, state="readonly", width=20,
                                          values=["Full pressure", "Above threshold"])
                else:
                    widget = ttk.Entry(page, textvariable=variable, width=15)
                widget.grid(row=row, column=1, sticky="w", padx=8)
                self.variables[(section, key)] = variable
        self.threshold_overlay_var = tk.BooleanVar(value=self.app.show_hotspot_threshold)
        ttk.Checkbutton(parent, text="Show hotspot activation contour on 2D pressure map",
                        variable=self.threshold_overlay_var, command=self._toggle_overlay).pack(anchor="w", pady=6)

    def _form_settings(self):
        settings = self.app.current_settings()
        for (section, key), variable in self.variables.items():
            if section:
                settings[section][key] = variable.get()
            else:
                settings[key] = variable.get()
        return validate_settings(settings)

    def _show_settings(self, settings):
        for (section, key), variable in self.variables.items():
            variable.set(str(settings[section][key] if section else settings[key]))

    def _apply(self):
        try:
            settings = self._form_settings()
            self.app.apply_engineering_settings(settings, self.preset_var.get())
        except ValueError as error:
            self.settings_status.set(str(error))
            return
        self.settings_status.set("Applied; hotspot and movement tracking restarted with unknown earlier history")

    def _use_preset(self):
        try:
            settings = builtin_preset(self.preset_var.get())
            self._show_settings(settings)
            self._apply()
        except ValueError as error:
            self.settings_status.set(str(error))

    def _save_preset(self):
        try:
            settings = self._form_settings()
        except ValueError as error:
            self.settings_status.set(str(error))
            return
        path = filedialog.asksaveasfilename(parent=self.window, defaultextension=".json",
                                            filetypes=[("JSON preset", "*.json")])
        if path:
            try:
                save_preset(path, settings, self.preset_var.get())
                self.settings_status.set(f"Saved preset to {path}")
            except OSError as error:
                self.settings_status.set(str(error))

    def _load_preset(self):
        path = filedialog.askopenfilename(parent=self.window,
                                          filetypes=[("JSON preset", "*.json")])
        if path:
            try:
                name, settings = load_preset(path)
                self.preset_var.set(name)
                self._show_settings(settings)
                self.settings_status.set("Preset loaded into fields; choose Apply values to use it")
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                self.settings_status.set(f"Could not load preset: {error}")

    def _toggle_overlay(self):
        self.app.show_hotspot_threshold = self.threshold_overlay_var.get()
        self.app._update_plot()

    def _build_validation(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill=tk.X)
        ttk.Label(bar, text="Reposition match window (s):").pack(side=tk.LEFT)
        self.match_var = tk.StringVar(value=str(self.app.validation_match_window_s))
        ttk.Entry(bar, textvariable=self.match_var, width=8).pack(side=tk.LEFT, padx=5)
        ttk.Button(bar, text="Apply", command=self._apply_match_window).pack(side=tk.LEFT)
        ttk.Button(bar, text="Annotate known reposition...",
                   command=lambda: self.app._open_annotation("Known reposition")).pack(side=tk.LEFT, padx=12)
        self.validation_var = tk.StringVar()
        ttk.Label(parent, textvariable=self.validation_var, justify=tk.LEFT,
                  wraplength=790, padding=8).pack(fill=tk.BOTH, expand=True)

    def _apply_match_window(self):
        try:
            value = float(self.match_var.get())
            if not 0 < value <= 3600:
                raise ValueError
        except ValueError:
            self.validation_var.set("Match window must be between 0 and 3600 seconds")
            return
        self.app.validation_match_window_s = value
        if self.app.recorder is not None:
            self.app.recorder.metadata["validation_match_window_s"] = value
        self.refresh()

    def _build_session(self, parent):
        ttk.Button(parent, text="Export analysis summary...", command=self._export).pack(anchor="w", pady=4)
        ttk.Button(parent, text="Compare recorded and current settings",
                   command=self._compare).pack(anchor="w", pady=4)
        self.compare_var = tk.StringVar(value="Load a recording to compare event counts")
        ttk.Label(parent, textvariable=self.compare_var, justify=tk.LEFT).pack(anchor="w")
        self.session_var = tk.StringVar()
        ttk.Label(parent, textvariable=self.session_var, justify=tk.LEFT,
                  wraplength=790, padding=8).pack(fill=tk.BOTH, expand=True)

    def _export(self):
        path = filedialog.asksaveasfilename(parent=self.window, defaultextension=".json",
                                            filetypes=[("JSON analysis summary", "*.json")])
        if path:
            try:
                summary = session_summary(self.app, self.app.validation_match_window_s)
                with open(path, "w", encoding="utf-8") as file:
                    json.dump(summary, file, indent=2, allow_nan=False)
                self.session_var.set(f"Exported analysis summary to {path}")
            except (OSError, TypeError, ValueError) as error:
                self.session_var.set(f"Could not export: {error}")

    def _compare(self):
        source = self.app.source
        if source is None or not source.is_playback:
            self.compare_var.set("Load a recording before comparing settings")
            return
        frames = source._playback_frames
        timestamps = source._playback_timestamps
        metadata = self.app._playback_metadata.copy()
        events = list(self.app._recorded_state_events)
        settings = self.app._current_analysis_settings.copy()
        area = self.app.cell_area_m2
        self.compare_var.set("Comparing recording in background...")

        def work():
            try:
                result = compare_recording(frames, timestamps, metadata, events, settings, area)
                message = " | ".join(
                    f"{key}: recorded {result['recorded_settings'][key]}, current "
                    f"{result['current_settings'][key]} ({result['difference'][key]:+d})"
                    for key in ("hotspots", "movements", "repositions"))
            except Exception as error:
                message = f"Comparison failed: {error}"
            self.window.after(0, lambda: self.compare_var.set(message) if self.window.winfo_exists() else None)

        threading.Thread(target=work, daemon=True).start()

    def _build_debug(self, parent):
        self.debug_var = tk.StringVar()
        ttk.Label(parent, textvariable=self.debug_var, justify=tk.LEFT,
                  wraplength=790, padding=8).pack(fill=tk.BOTH, expand=True)

    def _build_experiment(self, parent):
        self.experiment_vars = {}
        for row, (label, key) in enumerate(EXPERIMENT_FIELDS):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=7)
            variable = tk.StringVar(value=self.app.experiment_info.get(key, ""))
            ttk.Entry(parent, textvariable=variable, width=60).grid(row=row, column=1, sticky="w", padx=8)
            self.experiment_vars[key] = variable
        ttk.Button(parent, text="Save experiment info", command=self._save_experiment).grid(
            row=len(EXPERIMENT_FIELDS), column=1, sticky="e", pady=12)

    def _save_experiment(self):
        self.app.experiment_info = {key: variable.get().strip()
                                    for key, variable in self.experiment_vars.items() if variable.get().strip()}
        if self.app.recorder is not None:
            self.app.recorder.metadata["experiment"] = self.app.experiment_info.copy()
            self.app.add_event("experiment_info_changed", payload=self.app.experiment_info.copy())

    def refresh(self):
        if not self.window.winfo_exists():
            return
        summary = session_summary(self.app, self.app.validation_match_window_s)
        quality = summary["data_quality"]
        events = summary["algorithm_events"]
        validation = summary["reposition_validation"]
        hotspot_annotations = [event for event in self.app.timeline.events if event.get("kind") == "annotation"
                               and event.get("payload", {}).get("type") == "Known hotspot"]
        timing_errors = ", ".join(
            f"{item['timing_error_s']:+.1f}s" for item in validation["matches"]) or "-"
        self.validation_var.set(
            f"Known repositions: {events['manual_repositions']} | matched {validation['matched']} | "
            f"missed {validation['missed']} | unpaired automatic {validation['unpaired']}\n"
            f"Timing errors (automatic - manual): "
            f"{timing_errors}\n\n"
            f"Known hotspot ROI annotations: {len(hotspot_annotations)}\n" +
            "\n".join(f"{event['timestamp']:.1f}: overlap "
                      f"{event['payload'].get('comparison', {}).get('overlap', 0) * 100:.0f}% | "
                      f"centroid difference "
                      f"{event['payload'].get('comparison', {}).get('centroid_distance_cells')} cells"
                      for event in hotspot_annotations[-10:]))
        warnings = summary["readiness_warnings"]
        self.session_var.set(
            f"Observed session: {quality['observed_duration_s']} s | valid packets "
            f"{quality['valid_frames']}/{quality['received_frames']} "
            f"({quality['valid_frame_percent'] if quality['valid_frame_percent'] is not None else '-'}%) | malformed {quality['malformed_frames']} | "
            f"dropped {quality['dropped_frames']}\n"
            f"Longest arrival gap {quality['longest_arrival_gap_s']:.1f}s | "
            f"average arrival rate {quality['average_arrival_fps']:.1f} fps\n"
            f"Calibration {quality['calibrated_percent']:.0f}% | baseline "
            f"{'yes' if quality['baseline_present'] else 'no'} | sensor warnings "
            f"{quality['sensor_health_warnings']} | temporal state unknown "
            f"{quality['unknown_temporal_percent']:.0f}%\n\n"
            f"Hotspots {events['hotspots_observed']} (persistent {events['persistent_hotspots']}), "
            f"longest observed {events['longest_observed_hotspot_s']:.1f}s | "
            f"movement events {events['movement_events']} (major {events['major_movements']}) | "
            f"repositions {events['reposition_events']}\n"
            f"Total cell exposure {events['total_cell_exposure_kpa_min']:.1f} kPa·min | "
            f"maximum burden {events['maximum_cell_burden']:.1f}\n\n"
            f"Readiness: {'; '.join(warnings) if warnings else 'No current warnings'}")
        score = self.app.motion.last_score
        debug = self.app.motion.debug
        self.debug_var.set(
            f"Movement: {score['category']} | final score {score['score']:.3f}\n"
            f"Map change {score['map_change']:.3f} | CoP {score['cop_cells']:.2f} cells "
            f"→ normalized {score['cop_score']:.3f} | contact-area change {score['area_change']:.3f}\n"
            f"Thresholds: small {self.app.motion.small_score:.2f}, "
            f"significant {self.app.motion.significant_score:.2f}, "
            f"major {self.app.motion.major_score:.2f}; movement cooldown "
            f"{self.app.motion.movement_cooldown_s:.1f}s\n\n"
            f"Reposition stage: {debug.get('stage')} | {debug.get('reason')}\n"
            f"Candidate start: {debug.get('candidate_start', '-')} | "
            f"settle {self.app.motion.settle_s}s | before {self.app.motion.before_s}s | "
            f"after {self.app.motion.after_s}s\n"
            f"Before: {debug.get('before', '-')}\nAfter: {debug.get('after', '-')}\n"
            f"Redistribution: {debug.get('redistribution', '-')} | "
            f"current difference: {debug.get('current_change', '-')} | "
            f"threshold: {self.app.motion.reposition_min_change}")
        self.window.after(1000, self.refresh)
