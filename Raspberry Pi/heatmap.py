import matplotlib.pyplot as plt
import matplotlib.widgets as widgets
import numpy as np
import serial
import serial.tools.list_ports
from matplotlib.colors import LinearSegmentedColormap


# These values must match src/main.cpp.
TOTAL_ROWS = 16
TOTAL_COLS = 15
BAUD_RATE = 115200

# Each timer tick drains all complete serial lines and displays only the newest
# valid grid, preventing an ever-growing backlog of stale frames.
UPDATE_INTERVAL_MS = 50
MAX_RECEIVE_BUFFER_BYTES = 16 * 1024

VALUE_MIN_DEFAULT = 0
VALUE_MAX_DEFAULT = 1000

HEATMAP_COLORS = LinearSegmentedColormap.from_list(
    "relative_pressure", ["white", "green", "red"]
)


def parse_frame(raw_line):
    """Convert one firmware frame into a validated 16 x 15 NumPy grid."""
    if isinstance(raw_line, bytes):
        try:
            line = raw_line.decode("ascii")
        except UnicodeDecodeError:
            return None
    elif isinstance(raw_line, str):
        line = raw_line
    else:
        return None

    line = line.strip()
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
        # Boot messages and damaged serial lines are not data frames.
        return None

    if not np.all(np.isfinite(values)):
        return None
    if np.any(values < VALUE_MIN_DEFAULT) or np.any(values > VALUE_MAX_DEFAULT):
        return None

    return values.reshape(TOTAL_ROWS, TOTAL_COLS)


def find_port():
    """Return a serial device name or raise a readable startup error."""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        raise RuntimeError(
            "Fant ingen seriellport. Koble til ESP32-en og start programmet på nytt."
        )

    if len(ports) == 1:
        print(f"Using {ports[0].device}: {ports[0].description}")
        return ports[0].device

    print("Available ports")
    for index, port in enumerate(ports):
        print(f"{index}: {port.device} - {port.description}")

    while True:
        try:
            selection = int(input("Select a port number: "))
        except (EOFError, KeyboardInterrupt) as error:
            raise RuntimeError("Port selection cancelled.") from error
        except ValueError:
            print("Invalid input, try again ...")
            continue

        if 0 <= selection < len(ports):
            return ports[selection].device
        print("Invalid input, try again ...")


def read_latest_frame(connection, receive_buffer):
    """Drain serial data, preserve a partial line, and return the newest grid."""
    available = connection.in_waiting
    if available:
        receive_buffer.extend(connection.read(available))

    last_newline = receive_buffer.rfind(b"\n")
    if last_newline < 0:
        if len(receive_buffer) > MAX_RECEIVE_BUFFER_BYTES:
            receive_buffer.clear()
            print("Discarded an oversized partial serial frame")
        return None

    complete_data = bytes(receive_buffer[:last_newline])
    del receive_buffer[: last_newline + 1]

    # Search newest-to-oldest so an invalid boot/debug line cannot hide the
    # newest valid frame, while old valid frames are discarded immediately.
    for raw_line in reversed(complete_data.split(b"\n")):
        grid = parse_frame(raw_line)
        if grid is not None:
            return grid

    return None


def main():
    try:
        port = find_port()
        connection = serial.Serial(port, BAUD_RATE, timeout=0)
    except (RuntimeError, serial.SerialException, OSError) as error:
        raise SystemExit(str(error)) from error

    print(f"Connected to {port} at {BAUD_RATE} baud")

    current_grid = np.zeros((TOTAL_ROWS, TOTAL_COLS))
    receive_buffer = bytearray()
    serial_error = None
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

    fig.suptitle("SmartMat pressure heatmap", y=0.97)
    stats_text = fig.text(
        0.5, 0.90, "Waiting for the first complete grid ...", ha="center", va="top"
    )

    ax_vmin = fig.add_axes([0.15, 0.17, 0.7, 0.03])
    ax_vmax = fig.add_axes([0.15, 0.12, 0.7, 0.03])
    slider_vmin = widgets.Slider(
        ax_vmin, "Min", 0, 1000, valinit=VALUE_MIN_DEFAULT
    )
    slider_vmax = widgets.Slider(
        ax_vmax, "Max", 0, 1000, valinit=VALUE_MAX_DEFAULT
    )

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

    def poll_serial():
        nonlocal current_grid, has_received_grid, serial_error

        if serial_error is None:
            try:
                latest_grid = read_latest_frame(connection, receive_buffer)
                if latest_grid is not None:
                    current_grid = latest_grid
                    has_received_grid = True
            except (serial.SerialException, OSError) as error:
                serial_error = f"Serial connection lost: {error}"
                print(serial_error)
                connection.close()

        image.set_data(current_grid)
        if serial_error is not None:
            stats_text.set_text(serial_error)
        elif has_received_grid:
            stats_text.set_text(
                f"avg {current_grid.mean():.0f}   "
                f"max {current_grid.max():.0f}   "
                f"min {current_grid.min():.0f}"
            )
        fig.canvas.draw_idle()

    timer = fig.canvas.new_timer(interval=UPDATE_INTERVAL_MS)
    timer.add_callback(poll_serial)
    timer.start()

    try:
        plt.show()
    except KeyboardInterrupt:
        pass
    finally:
        timer.stop()
        if connection.is_open:
            connection.close()


if __name__ == "__main__":
    main()
