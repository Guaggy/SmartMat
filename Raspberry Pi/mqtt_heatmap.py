import threading

import matplotlib.pyplot as plt
import matplotlib.widgets as widgets
import numpy as np
import paho.mqtt.client as mqtt
from matplotlib.colors import LinearSegmentedColormap

import config

# These values must match src/main.cpp.
TOTAL_ROWS = 16
TOTAL_COLS = 15

VALUE_MIN_DEFAULT = 0
VALUE_MAX_DEFAULT = 1000

HEATMAP_COLORS = LinearSegmentedColormap.from_list(
    "relative_pressure", ["white", "green", "red"]
)


def parse_frame(payload):
    """Convert one MQTT payload into a validated 16 x 15 NumPy grid."""
    try:
        line = payload.decode("ascii").strip()
    except UnicodeDecodeError:
        return None

    if line.endswith(","):
        line = line[:-1]

    pieces = line.split(",")
    if len(pieces) != TOTAL_ROWS * TOTAL_COLS:
        return None
    if any(piece.strip() == "" for piece in pieces):
        return None

    try:
        values = np.asarray([float(piece) for piece in pieces], dtype=float)
    except ValueError:
        return None

    if not np.all(np.isfinite(values)):
        return None
    if np.any(values < VALUE_MIN_DEFAULT) or np.any(values > VALUE_MAX_DEFAULT):
        return None

    return values.reshape(TOTAL_ROWS, TOTAL_COLS)


class LatestFrame:
    """Holds the newest grid received over MQTT, safe to read from another thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._grid = None

    def set(self, grid):
        with self._lock:
            self._grid = grid

    def take(self):
        """Return the newest grid and clear it, or None if nothing new arrived."""
        with self._lock:
            grid, self._grid = self._grid, None
            return grid


latest_frame = LatestFrame()


def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"Connected to {config.broker_host}:{config.broker_port}, subscribing to {config.mqtt_topic}")
    client.subscribe(config.mqtt_topic)


def on_message(client, userdata, message):
    grid = parse_frame(message.payload)
    if grid is not None:
        latest_frame.set(grid)


def build_mqtt_client():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smartmat-pi")
    client.username_pw_set(config.mqtt_username, config.mqtt_password)
    client.on_connect = on_connect
    client.on_message = on_message
    return client


def main():
    client = build_mqtt_client()
    client.connect(config.broker_host, config.broker_port)
    client.loop_start()

    current_grid = np.zeros((TOTAL_ROWS, TOTAL_COLS))
    has_received_grid = False

    fig, ax = plt.subplots(figsize=(7, 8))
    plt.subplots_adjust(bottom=0.32, top=0.85)

    image = ax.imshow(
        current_grid,
        cmap=HEATMAP_COLORS,
        vmin=VALUE_MIN_DEFAULT,
        vmax=VALUE_MAX_DEFAULT,
        aspect="auto",
    )
    fig.colorbar(image, ax=ax, label="Relative sensor value (0-1000)")

    fig.suptitle("SmartMat pressure heatmap (MQTT)", y=0.97)
    stats_text = fig.text(
        0.5, 0.90, "Waiting for the first complete grid ...", ha="center", va="top"
    )

    ax_vmin = fig.add_axes([0.15, 0.17, 0.7, 0.03])
    ax_vmax = fig.add_axes([0.15, 0.12, 0.7, 0.03])
    slider_vmin = widgets.Slider(ax_vmin, "Min", 0, 1000, valinit=VALUE_MIN_DEFAULT)
    slider_vmax = widgets.Slider(ax_vmax, "Max", 0, 1000, valinit=VALUE_MAX_DEFAULT)

    def on_slider_change(_value):
        vmin = slider_vmin.val
        vmax = slider_vmax.val
        if vmin < vmax:
            image.set_clim(vmin, vmax)
        fig.canvas.draw_idle()

    slider_vmin.on_changed(on_slider_change)
    slider_vmax.on_changed(on_slider_change)

    def auto_calibrate(_event):
        lowest = current_grid.min()
        highest = current_grid.max()
        if lowest < highest:
            slider_vmin.set_val(lowest)
            slider_vmax.set_val(highest)

    ax_button = fig.add_axes([0.4, 0.03, 0.2, 0.05])
    calibrate_button = widgets.Button(ax_button, "Auto calibrate")
    calibrate_button.on_clicked(auto_calibrate)

    def poll_mqtt():
        nonlocal current_grid, has_received_grid

        new_grid = latest_frame.take()
        if new_grid is not None:
            current_grid = new_grid
            has_received_grid = True

        image.set_data(current_grid)
        if has_received_grid:
            stats_text.set_text(
                f"avg {current_grid.mean():.0f}   "
                f"max {current_grid.max():.0f}   "
                f"min {current_grid.min():.0f}"
            )
        fig.canvas.draw_idle()

    timer = fig.canvas.new_timer(interval=50)
    timer.add_callback(poll_mqtt)
    timer.start()

    try:
        plt.show()
    except KeyboardInterrupt:
        pass
    finally:
        timer.stop()
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
