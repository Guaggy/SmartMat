"""Short, scrollable operating guide for the desktop dashboard."""

import tkinter as tk
from tkinter import ttk


SECTIONS = (
    ("SMARTMAT Quick Start", """1. Select Serial, MQTT, Simulation, or Playback.
2. Connect and confirm the heatmap updates.
3. Open Diagnostics and check sensor response.
4. Unload the mat, then capture Tare.
5. Open Pressure calibration.
6. Apply a known load or pressure and add calibration points.
7. Repeat for the sensors and load levels you need.
8. Save the calibration.
9. Select Calibrated pressure and check the readings.
10. Check contact detection and sensor health.
11. Start Recording if the session should be saved.
12. The mat is ready for monitoring and analysis."""),
    ("Recommended Calibration Workflow", """Start SMARTMAT
  ↓  Select data source
  ↓  Connect and verify live data
  ↓  Check Diagnostics
  ↓  Unload the mat and capture Tare
  ↓  Open Pressure calibration
  ↓  Apply known load or pressure
  ↓  Add calibration points
  ↓  Repeat for sensors and load levels
  ↓  Save calibration
  ↓  Select Calibrated pressure
  ↓  Verify readings and contact detection
Ready for use"""),
    ("Main Data Modes", """Raw / received — values received by the Raspberry Pi.
Processed — received values after Raspberry Pi processing.
Baseline subtracted — values relative to the current tare.
Calibrated pressure — values converted to kPa using sensor calibration."""),
    ("Main Tools", """Pressure calibration — create, load, and save sensor calibration.
Diagnostics — inspect noise, drift, saturation, calibration, and sensor health.
Analysis — ROI, distributions, load balance, and symmetry.
Temporal — pressure-time exposure, burden, and relief.
Hotspots — connected regions of elevated pressure.
Movement — pressure redistribution and reposition detection.
Engineering — thresholds, presets, annotations, validation, and session summaries.
Recording / Playback — save experiments or replay recorded sessions."""),
    ("Important Notes", """• Tare only while the mat is unloaded.
• Use calibrated pressure for physical pressure measurements.
• Interpolation improves the display; it does not add sensors.
• Engineering thresholds and burden metrics are experimental, not diagnoses.
• If readings look wrong, check Diagnostics, tare, and calibration first."""),
)


class HelpWindow:
    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.title("SMARTMAT Help / Quick Start")
        self.window.geometry("650x610")

        panel = ttk.Frame(self.window, padding=10)
        panel.pack(fill=tk.BOTH, expand=True)
        text = tk.Text(panel, wrap=tk.WORD, padx=12, pady=10, relief=tk.FLAT,
                       background=self.window.cget("background"))
        scrollbar = ttk.Scrollbar(panel, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        text.tag_configure("heading", font=("TkDefaultFont", 11, "bold"), spacing1=12, spacing3=5)
        for heading, body in SECTIONS:
            text.insert(tk.END, heading + "\n", "heading")
            text.insert(tk.END, body + "\n\n")
        text.configure(state=tk.DISABLED)
