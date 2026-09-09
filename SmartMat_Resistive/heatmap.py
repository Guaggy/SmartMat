import matplotlib.pyplot as plt
import matplotlib.widgets as widgets
import numpy as np
import serial
import serial.tools.list_ports
from matplotlib.colors import LinearSegmentedColormap

# these three have to match src/main.cpp or the numbers won't line up right
total_rows = 16
total_cols = 15
baud_rate = 115200

update_delay = 0.5  # how often we check for a new frame, in seconds

# starting color scale range - the sliders let us change this after connecting
value_min_default = 0
value_max_default = 1000

# white where nothing is pressing on the mat, green for a normal amount of pressure, red for a lot
pressure_cmap = LinearSegmentedColormap.from_list("pressure_risk", ["white", "green", "red"])

# always holds the newest full grid we've received - the heatmap, the stats text
# and the auto calibrate button all just read from this
current_grid = np.zeros((total_rows, total_cols))


def parse_frame(line):
    # the ESP32 sends one line per frame, something like "12,34,0,...,999,"
    # it ends with a trailing comma, so splitting on "," leaves one empty string at the end
    pieces = line.strip().split(",")

    numbers = []
    for piece in pieces:
        if piece == "":
            continue  # this is the empty bit after the trailing comma, just skip it
        try:
            numbers.append(float(piece))
        except ValueError:
            return None  # not a number, so this line probably isn't a real frame (e.g. a boot message)

    if len(numbers) != total_rows * total_cols:
        return None  # wrong amount of values, must be a partial/corrupted line

    return np.array(numbers).reshape(total_rows, total_cols)


def find_port():
    port = 0
    ports = serial.tools.list_ports.comports()
    if len(ports) == 1:
        port = ports[0]
    else:
        print("Available ports")
        for i in range(len(ports)):
            p = ports[i]
            print(f"{i}: {p}")
        while True:
            try:
                selection = int(input("Select a port number: "))
                port = ports[selection]
                break
            except:
                print("Invalid input, try again ...")
    return port


def read_next_frame():
    # tries to read one line from serial - if it turns out to be a real frame,
    # we replace current_grid with it, otherwise we just leave current_grid as it was
    global current_grid
    line = ser.readline().decode("utf-8", errors="ignore")
    grid = parse_frame(line)
    if grid is not None:
        current_grid = grid


def refresh_plot():
    # pushes current_grid onto the heatmap image and updates the stats line above it
    im.set_data(current_grid)
    stats_text.set_text(
        f"avg {current_grid.mean():.0f}   max {current_grid.max():.0f}   min {current_grid.min():.0f}"
    )


def on_slider_change(_value):
    # both sliders call this, so we just re-read whatever they're both set to now
    vmin = slider_vmin.val
    vmax = slider_vmax.val
    if vmin < vmax:
        im.set_clim(vmin, vmax)
    fig.canvas.draw_idle()


def auto_calibrate(_event):
    # stretches the color scale to fit whatever the mat is reading right now -
    # the lowest value on the grid becomes white, the highest becomes red
    lowest = current_grid.min()
    highest = current_grid.max()
    if lowest < highest:
        slider_vmin.set_val(lowest)
        slider_vmax.set_val(highest)


# connect to the board
port = find_port()
ser = serial.Serial(port.device, baud_rate, timeout=0.1)

# build the window
plt.ion()
fig, ax = plt.subplots(figsize=(7, 8))
plt.subplots_adjust(bottom=0.32, top=0.85)

im = ax.imshow(current_grid, cmap=pressure_cmap, vmin=value_min_default, vmax=value_max_default, aspect="auto")
fig.colorbar(im, ax=ax, label="Pressure (relative units)")

fig.suptitle("SmartMat pressure heatmap", y=0.97)
stats_text = fig.text(0.5, 0.90, "", ha="center", va="top")

# sliders for manually setting the color scale range
ax_vmin = fig.add_axes([0.15, 0.17, 0.7, 0.03])
ax_vmax = fig.add_axes([0.15, 0.12, 0.7, 0.03])
slider_vmin = widgets.Slider(ax_vmin, "Min", 0, 1000, valinit=value_min_default)
slider_vmax = widgets.Slider(ax_vmax, "Max", 0, 1000, valinit=value_max_default)
slider_vmin.on_changed(on_slider_change)
slider_vmax.on_changed(on_slider_change)

# button that sets the sliders automatically from the current grid
ax_button = fig.add_axes([0.4, 0.03, 0.2, 0.05])
calibrate_button = widgets.Button(ax_button, "Auto calibrate")
calibrate_button.on_clicked(auto_calibrate)

# keep reading frames and redrawing until the window gets closed
while plt.fignum_exists(fig.number):
    try:
        read_next_frame()
    except Exception:
        print("Failed to read serial data")

    refresh_plot()
    plt.pause(update_delay)

ser.close()
