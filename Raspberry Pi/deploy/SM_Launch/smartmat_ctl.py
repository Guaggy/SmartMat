#!/usr/bin/env python3
"""SmartMat config and control for the Raspberry Pi (standard library only).

    smartmat                 menu          smartmat status      one-page report          smartmat help   all commands
Every menu entry is also a command, so it works over ssh and in scripts too.
"""

import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent.parent                      # the "Raspberry Pi" folder of the checkout
REPO = APP.parent
SERVICE = "smartmat-server"
UNIT_DEST = Path("/etc/systemd/system") / (SERVICE + ".service")
ENV_FILE = Path("/etc/default") / SERVICE      # SMARTMAT_ARGS="--demo 2" for the service
AUTOSTART = Path.home() / ".config/autostart/smartmat-kiosk.desktop"
KIOSK_SH = APP / "deploy/smartmat-kiosk.sh"
STATE = Path.home() / ".cache/smartmat"
API = "http://localhost:8000"
PY = str(APP / ".venv/bin/python")
PIO = str(Path.home() / "pio/bin/pio")
FIRMWARE = {"real": ("ESP32_China", "esp32-s3-devkitc-1"), "sim": ("ESP32_China", "esp32-s3-simulate"),
            "dump": ("ESP32_China", "esp32-s3-dump"), "resistive": ("ESP32_Resistive", "esp32doit-devkit-v1")}

COLOR = sys.stdout.isatty()
def paint(code, text): return f"\033[{code}m{text}\033[0m" if COLOR else text
ok = lambda text: paint("32", text)
bad = lambda text: paint("31", text)
dim = lambda text: paint("90", text)
bold = lambda text: paint("1", text)


# ---------- helpers ----------
def run(cmd, timeout=30, **kw):
    """Output text of a command; '' if it is missing or fails."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""

def call(cmd, **kw):
    """Run a command with its output on screen; True if it succeeded."""
    try:
        return subprocess.run(cmd, **kw).returncode == 0
    except (OSError, subprocess.SubprocessError) as error:
        print(bad(f"{cmd[0]}: {error}"))
        return False

def sudo(cmd): return cmd if os.geteuid() == 0 else ["sudo"] + cmd
def running(pattern): return subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0
def git(*args, **kw): return run(["git", "-C", str(REPO), *args], **kw)

def api(path, timeout=3):
    try:
        with urllib.request.urlopen(API + path, timeout=timeout) as reply:
            return json.load(reply)
    except Exception:
        return None

def broker_login():
    """host, user, password for mosquitto_sub etc., from config.py (the same login the server uses)"""
    text = (APP / "config.py").read_text(errors="replace") if (APP / "config.py").exists() else ""
    get = lambda name, default: (re.search(rf'^{name}\s*=\s*["\'](.*?)["\']', text, re.M) or [None, default])[1]
    return get("broker_host", "localhost"), get("mqtt_username", ""), get("mqtt_password", "")

def mosquitto(tool, *args):
    host, user, password = broker_login()
    cmd = [tool, "-h", host, "-p", "1883"] + (["-u", user, "-P", password] if user else []) + list(args)
    return cmd

def gui_env():
    env = dict(os.environ)
    env.setdefault("DISPLAY", ":0")
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return env

def background(cmd, **kw):
    subprocess.Popen(cmd, env=gui_env(), start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, **kw)

def ask(text):
    try:
        return input(text).strip()
    except EOFError:
        return ""

def confirm(text): return ask(f"{text} [y/N] ").lower() in ("y", "yes", "j", "ja")


# ---------- status ----------
def line(label, value, good=None):
    mark = "   " if good is None else (ok(" ok") if good else bad("BAD"))
    print(f"  {mark}  {label:<26}{value}")

def cmd_status(args=()):
    """status   one-page report: services, web UI, mats, ESP32, network, updates"""
    print(bold("SmartMat status"), dim(time.strftime("  %Y-%m-%d %H:%M:%S")))
    try:
        model = Path("/proc/device-tree/model").read_text(errors="replace").strip(chr(0))
    except OSError:
        model = "?"
    line("Computer", f"{model}, up {run(['uptime', '-p']).replace('up ', '')}")
    temp = run(["vcgencmd", "measure_temp"]).replace("temp=", "")
    throttled = run(["vcgencmd", "get_throttled"]).replace("throttled=", "")
    line("Temperature", temp or "?", None if not temp else float(temp.replace("'C", "") or 0) < 75)
    if throttled and throttled != "0x0":
        bits = int(throttled, 16)
        for bit, text in ((0, "UNDER-VOLTAGE now: weak power supply or cable"), (2, "throttled now"), (3, "too hot, speed capped now"),
                          (16, "under-voltage has happened since boot"), (18, "throttling has happened since boot"),
                          (19, "overheating has happened since boot: add a heatsink or fan")):
            if bits >> bit & 1:
                line("Power/heat", text, False)
    disk = shutil.disk_usage("/")
    line("Disk free", f"{disk.free / 1e9:.1f} GB of {disk.total / 1e9:.1f} GB", disk.free > 1e9)
    print()
    for name in (SERVICE, "mosquitto", "tailscaled", "ssh"):
        active = run(["systemctl", "is-active", name])
        enabled = run(["systemctl", "is-enabled", name])
        line(f"Service {name}", f"{active}, {enabled} at boot", active == "active")
    health = api("/api/health")
    line("Web server :8000", f"v{health['version']}, build {health['build']}" if health else "not answering", bool(health))
    overview = api("/api/overview")
    if overview:
        mats = overview["mats"]
        line("Mats online", f"{sum(m['online'] for m in mats)} of {len(mats)}   open alerts: {overview['open_alerts']}")
        for m in mats:
            line("", f"{m['id']}  {'online ' if m['online'] else 'offline'} {'(demo)' if m['demo'] else ''}")
    print()
    line("Web UI kiosk", "running" if running("[s]martmat-kiosk-profile") else "not running")
    line("Web UI at boot", "on" if AUTOSTART.exists() else "off")
    line("Desktop dashboard", "running" if running("[.]venv/bin/python main.py") else "not running")
    line("Demo mats in server", sim_args() or "off")
    line("Replay mat", "running" if replay_pid() else "off")
    ports = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    line("ESP32 on USB", ", ".join(ports) if ports else "none found")
    print()
    line("Addresses", run(["hostname", "-I"]))
    tailscale = run(["tailscale", "ip", "-4"])
    line("Tailscale", tailscale or "off")
    wifi = run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"]).splitlines()
    line("WiFi", run(["iwgetid", "-r"]) or next((l[4:] for l in wifi if l.startswith("yes:")), "?"))
    print()
    behind = ""
    if git("fetch", "-q", timeout=8) is not None:
        behind = git("rev-list", "--count", "HEAD..@{u}")
    line("Code version", f"{git('rev-parse', '--short', 'HEAD')} {git('log', '-1', '--format=%s')[:50]}")
    line("Updates", f"{behind} new commit(s) on GitHub: run  smartmat update" if behind not in ("", "0") else "up to date", behind in ("", "0"))
    dirty = git("status", "--porcelain", "--untracked-files=no")
    if dirty:
        line("Local changes", f"{len(dirty.splitlines())} file(s) edited on the Pi (update may refuse)", False)


# ---------- web UI and desktop dashboard ----------
def cmd_web(args=()):
    """web start|stop|restart   fullscreen web dashboard on the touchscreen"""
    action = args[0] if args else "start"
    if action in ("stop", "restart"):
        run(["pkill", "-f", "[s]martmat-kiosk-profile"])
        time.sleep(1)
        print("web dashboard closed")
    if action in ("start", "restart"):
        background(["sh", str(KIOSK_SH)])
        print("web dashboard starting on the touchscreen (it waits for the server if that is still starting)")
    if action not in ("start", "stop", "restart"):
        print("usage: web start|stop|restart")

def cmd_desktop(args=()):
    """desktop start|stop   the advanced desktop dashboard (closes the web kiosk first)"""
    action = args[0] if args else "start"
    if action == "stop":
        run(["pkill", "-f", "[.]venv/bin/python main.py"])
        print("desktop dashboard closed")
    elif action == "start":
        background(["sh", str(HERE / "desktop-dashboard.sh")])
        print("desktop dashboard starting on the touchscreen")
    else:
        print("usage: desktop start|stop")


# ---------- boot options ----------
def cmd_boot(args=()):
    """boot [web|server] [on|off]   what starts by itself after power-on"""
    if len(args) < 2:
        print(f"  web UI kiosk at boot : {'on' if AUTOSTART.exists() else 'off'}")
        print(f"  server at boot       : {run(['systemctl', 'is-enabled', SERVICE])}")
        print("change with:  boot web on|off     boot server on|off")
        return
    what, state = args[0], args[1] == "on"
    if what == "web":
        if state:
            AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
            AUTOSTART.write_text(f'[Desktop Entry]\nType=Application\nName=SmartMat kiosk\nExec=sh "{KIOSK_SH}"\n')
        else:
            AUTOSTART.unlink(missing_ok=True)
        print(f"web UI at boot: {'on' if state else 'off'}  (takes effect at the next login/boot)")
    elif what == "server":
        call(sudo(["systemctl", "enable" if state else "disable", SERVICE]))
        print(f"server at boot: {'on' if state else 'off'}  (the running server is not stopped)")
    else:
        print("usage: boot web|server on|off")


# ---------- simulations ----------
def sim_args():
    try:
        match = re.search(r'SMARTMAT_ARGS="?([^"\n]*)', ENV_FILE.read_text())
        return match.group(1).strip() if match else ""
    except OSError:
        return ""

def replay_pid():
    try:
        pid = int((STATE / "replay.pid").read_text())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return 0

def cmd_sim(args=()):
    """sim [demo N|off] [replay on|off]   fake mats without hardware"""
    if not args:
        print(f"  demo mats in the server : {sim_args() or 'off'}   (sim demo 2 / sim demo off)")
        print(f"  replayed seat recording : {'running (mat demo-take1)' if replay_pid() else 'off'}   (sim replay on|off)")
        print("  ESP32 test pattern      : flash it with  esp32 flash sim  (back with  esp32 flash real)")
        return
    if args[0] == "demo":
        arg = args[1] if len(args) > 1 else "2"
        text = "" if arg == "off" else f'SMARTMAT_ARGS="--demo {int(arg)}"\n'
        if call(sudo(["tee", str(ENV_FILE)]), input=text, stdout=subprocess.DEVNULL, text=True):
            print(f"demo mats: {'off' if arg == 'off' else arg}; restarting the server")
            cmd_restart(["server"])
    elif args[0] == "replay":
        state = (args[1] if len(args) > 1 else "on") == "on"
        pid = replay_pid()
        if pid and not state:
            os.kill(pid, signal.SIGTERM)
            print("replay stopped (the mat shows offline after a while)")
        elif state and not pid:
            host, user, password = broker_login()
            STATE.mkdir(parents=True, exist_ok=True)
            cmd = [PY, str(APP / "tools/publish_demo_mat.py"), "--host", host, "--user", user, "--password", password]
            proc = subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=APP)
            (STATE / "replay.pid").write_text(str(proc.pid))
            print("replaying the seat recording as mat demo-take1 (stops with  sim replay off  or at reboot)")
        else:
            print("replay is already " + ("running" if pid else "off"))
    else:
        print("usage: sim demo N|off     sim replay on|off")


# ---------- restart, update ----------
def cmd_restart(args=()):
    """restart server|web|broker|all   (services only, no reboot; use  reboot  for the whole Pi)"""
    what = args[0] if args else "all"
    if what in ("broker", "all"):
        call(sudo(["systemctl", "restart", "mosquitto"]))
    if what in ("server", "all"):
        call(sudo(["systemctl", "restart", SERVICE]))
    if what in ("web", "all"):
        cmd_web(["restart"])
    if what not in ("server", "web", "broker", "all"):
        print("usage: restart server|web|broker|all")
    elif what in ("server", "all"):
        for _ in range(15):
            if api("/api/health"):
                print(ok("server is back"))
                return
            time.sleep(1)
        print(bad("the server did not answer within 15 s: smartmat logs server"))

def cmd_reboot(args=()):
    """reboot   restart the whole Pi"""
    if confirm("Reboot the whole Pi now?"):
        call(sudo(["reboot"]))

def cmd_shutdown(args=()):
    """shutdown   power the Pi off (it must be unplugged and replugged to start again)"""
    if confirm("Shut the Pi down? It will not come back until the power is cycled."):
        call(sudo(["shutdown", "-h", "now"]))

def service_unit_text():
    text = (APP / "deploy/smartmat-server.service").read_text()
    return text.replace("User=pi", f"User={os.environ.get('USER', 'pi')}").replace("/home/pi/SmartMat", str(REPO))

def install_service():
    """Copy the repo's unit file to systemd (paths and user filled in) when it differs from the installed one"""
    wanted = service_unit_text()
    try:
        current = UNIT_DEST.read_text()
    except OSError:
        current = ""
    if current == wanted:
        return False
    call(sudo(["tee", str(UNIT_DEST)]), input=wanted, stdout=subprocess.DEVNULL, text=True)
    call(sudo(["systemctl", "daemon-reload"]))
    print("service file refreshed")
    return True

def cmd_update(args=()):
    """update   git pull, new packages if needed, refresh launchers and service, restart the server"""
    dirty = git("status", "--porcelain", "--untracked-files=no")
    if dirty:
        print(bad("These files were edited on the Pi, the update would clash with them:"))
        print(dirty)
        print("Discard them with  git -C", REPO, "checkout -- <file>  and run update again.")
        return
    before = git("rev-parse", "HEAD")
    if not call(["git", "-C", str(REPO), "pull", "--ff-only"]):
        print(bad("git pull failed (network? local commits?)"))
        return
    after = git("rev-parse", "HEAD")
    if before == after:
        print("Already up to date.")
    else:
        print(git("log", "--oneline", f"{before}..{after}"))
        if "requirements-server.txt" in git("diff", "--name-only", before, after):
            call([str(APP / ".venv/bin/pip"), "install", "-q", "-r", str(APP / "requirements-server.txt")])
    call(["sh", str(HERE / "install_launchers.sh")], stdout=subprocess.DEVNULL)
    install_service()
    cmd_restart(["server"])
    print("The web kiosk reloads itself when the server is back. A running desktop dashboard needs  desktop stop / start.")


# ---------- information ----------
def cmd_logs(args=()):
    """logs [server|broker] [lines]   recent log lines (Ctrl+C stops, add -f to follow)"""
    which = args[0] if args else "server"
    unit = {"server": SERVICE, "broker": "mosquitto"}.get(which)
    if not unit:
        print("usage: logs server|broker [lines] [-f]")
        return
    count = next((a for a in args[1:] if a.isdigit()), "40")
    call(["journalctl", "-u", unit, "-n", count, "--no-pager"] + (["-f"] if "-f" in args else []))

def cmd_mats(args=()):
    """mats | mats forget <id>   list mats; forget clears a retired mat's retained broker entries"""
    if args[:1] == ["forget"] and len(args) > 1:
        for topic in ("meta", "status"):
            call(mosquitto("mosquitto_pub", "-t", f"smartmat/{args[1]}/{topic}", "-r", "-n"))
        print(f"cleared the broker's memory of {args[1]} (also remove it in the dashboard settings if it stays listed)")
        return
    overview = api("/api/overview")
    if not overview:
        print(bad("the server does not answer"))
        return
    for m in overview["mats"]:
        print(f"  {m['id']:<16}{'online ' if m['online'] else 'offline'}  {m['name']!s:<16} risk {m['risk']:<6} posture {m['posture']}")
    topics = run(mosquitto("mosquitto_sub", "-t", "smartmat/+/status", "-v", "-W", "2")).splitlines()
    print(dim("broker knows: " + ", ".join(t.replace("smartmat/", "").replace("/status", "") for t in topics)))

def cmd_watch(args=()):
    """watch [topic]   live MQTT traffic (default smartmat/+/status and meta; Ctrl+C stops)"""
    topic = args[0] if args else "smartmat/+/#"
    print(dim("Ctrl+C to stop; frames are long lines, use  watch 'smartmat/+/status'  for a quiet view"))
    try:
        subprocess.run(mosquitto("mosquitto_sub", "-t", topic, "-v"))
    except KeyboardInterrupt:
        pass

def cmd_ip(args=()):
    """ip   the addresses to reach the dashboard on"""
    tailscale = run(["tailscale", "ip", "-4"])
    for address in run(["hostname", "-I"]).split():
        if ":" not in address:
            print(f"  http://{address}:8000" + ("   (Tailscale, works from anywhere)" if address == tailscale else "   (this network)"))

def cmd_backup(args=()):
    """backup   save the database, profiles and users (/var/lib/smartmat) to your home folder"""
    target = Path.home() / time.strftime("smartmat-backup-%Y%m%d-%H%M.tgz")
    if call(sudo(["tar", "czf", str(target), "-C", "/var/lib", "smartmat"])):
        call(sudo(["chown", f"{os.getuid()}:{os.getgid()}", str(target)]))
        print(ok(f"saved {target}  ({target.stat().st_size // 1024} kB)"))


# ---------- ESP32 on USB ----------
def esp32_port():
    ports = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    return ports[0] if ports else None

READ_SERIAL = """
import serial, sys, time
s = serial.Serial(sys.argv[1], 115200, timeout=1)
if sys.argv[3] == "reset":
    s.dtr = False; s.rts = True; time.sleep(0.1); s.rts = False
end = time.time() + float(sys.argv[2])
while time.time() < end:
    data = s.readline()
    if data: print(data.decode("latin1").rstrip(), flush=True)
"""

def cmd_esp32(args=()):
    """esp32 status|reset|log|flash <real|sim|dump|resistive>   the ESP32 on the Pi's USB"""
    action = args[0] if args else "status"
    port = esp32_port()
    if action == "flash":
        which = args[1] if len(args) > 1 else ""
        if which not in FIRMWARE:
            print("usage: esp32 flash real|sim|dump|resistive   (real = Maxrays mat, sim = test pattern, dump = raw bytes)")
            return
        folder, env = FIRMWARE[which]
        if not (REPO / folder / "src/secrets.h").exists():
            print(bad(f"{folder}/src/secrets.h is missing (copy secrets.h.example and fill in WiFi and broker)"))
            return
        call([PIO, "run", "-e", env, "-t", "upload"], cwd=REPO / folder)
    elif not port:
        print(bad("no ESP32 found on USB (checked /dev/ttyACM* and /dev/ttyUSB*): cable, power-only cable?"))
    elif action == "status" or action == "log" or action == "reset":
        seconds = args[1] if action == "log" and len(args) > 1 else ("12" if action != "status" else "4")
        print(f"{port}: " + ("resetting, " if action == "reset" else "") + f"reading {seconds} s (Ctrl+C stops)")
        try:
            call([PY, "-c", READ_SERIAL, port, seconds, "reset" if action == "reset" else "read"])
        except KeyboardInterrupt:
            pass
    else:
        print("usage: esp32 status|reset|log [s]|flash <env>")


# ---------- help and menu ----------
def cmd_help(args=()):
    """help   this list"""
    print(bold("smartmat <command>") + dim("   (no command = menu)\n"))
    for name, func in COMMANDS.items():
        first, _, rest = (func.__doc__ or "").partition("   ")
        print(f"  {first:<42}{rest}" if rest else f"  {first}")
    print(dim("\nExamples:  smartmat status | smartmat boot web off | smartmat sim demo 2 | smartmat update | smartmat restart all"))

COMMANDS = {"status": cmd_status, "web": cmd_web, "desktop": cmd_desktop, "boot": cmd_boot, "sim": cmd_sim,
            "restart": cmd_restart, "reboot": cmd_reboot, "shutdown": cmd_shutdown, "update": cmd_update, "logs": cmd_logs,
            "mats": cmd_mats, "watch": cmd_watch, "ip": cmd_ip, "backup": cmd_backup, "esp32": cmd_esp32, "help": cmd_help}

MENU = [
    ("Status report", "status"),
    ("Start the web dashboard (fullscreen)", "web start"),
    ("Close the web dashboard", "web stop"),
    ("Start the desktop dashboard (advanced)", "desktop start"),
    ("Web dashboard at boot: on", "boot web on"),
    ("Web dashboard at boot: off", "boot web off"),
    ("Demo mats in the server: 2 / off", "ask:sim demo"),
    ("Replay a fake mat: on / off", "ask:sim replay"),
    ("Restart server + web (partly)", "restart all"),
    ("Restart the whole Pi", "reboot"),
    ("Update from GitHub and restart", "update"),
    ("Show server log", "logs server 40"),
    ("List mats", "mats"),
    ("ESP32: reset and show its output", "esp32 reset"),
    ("Back up the data", "backup"),
    ("Help / all commands", "help"),
]

def dispatch(words):
    func = COMMANDS.get(words[0])
    if not func:
        print(bad(f"unknown command '{words[0]}'"), "- try:  help")
        return
    try:
        func(words[1:])
    except KeyboardInterrupt:
        print()

def cmd_menu():
    while True:
        print("\n" + bold("SmartMat config"))
        for number, (label, _) in enumerate(MENU, 1):
            print(f"  {number:>2}) {label}")
        print("   q) quit")
        choice = ask("> ")
        if choice in ("q", "quit", "exit"):
            return
        if choice.isdigit() and 1 <= int(choice) <= len(MENU):
            command = MENU[int(choice) - 1][1]
            if command.startswith("ask:"):
                command = command[4:] + " " + (ask("on/off (demo: number of mats or off): ") or "off")
            print()
            dispatch(command.split())
            ask(dim("\n[Enter] for the menu "))
        elif choice:
            dispatch(choice.split())   # the menu also takes typed commands


if __name__ == "__main__":
    if len(sys.argv) > 1:
        dispatch(sys.argv[1:])
    else:
        cmd_menu()
