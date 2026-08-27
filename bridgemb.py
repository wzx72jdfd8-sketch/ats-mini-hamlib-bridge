#!/usr/bin/env python3
"""
ATS Mini Hamlib proxy GUI
WSJT-X: Rig = Hamlib NET rigctl, Network Server = 127.0.0.1:4532
"""

import re
import socket
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import serial
import serial.tools.list_ports

RIG_OK = 0
RIG_EINVAL = -1
RIG_ENAVAIL = -11

# Bound incomplete serial / TCP fragments so a stream without newlines cannot grow forever.
MAX_LINE_BUF = 65536
UI_FLUSH_MS = 200

HAMLIB_TO_ATS = {
    "USB": "USB", "PKTUSB": "USB", "DIGU": "USB", "CW": "USB", "RTTY": "USB",
    "LSB": "LSB", "PKTLSB": "LSB", "DIGL": "LSB", "CWR": "LSB", "RTTYR": "LSB",
    "AM": "AM", "AMS": "AM", "SAM": "AM", "DSB": "AM",
    "FM": "FM", "WFM": "FM", "PKTFM": "FM",
}

DUMP_STATE = """\
0
2
1
150000.000000 30000000.000000 0x2d -1 -1 0x10000003 0x1
0 0 0 0 0 0 0
0 0 0 0 0 0 0
0 0
0 0
0
0
0
0
0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0
0x00000000
0x00000000
0x00000000
0x00000000
0x00000000
0x00000000
"""


class ATSMini:
    def __init__(self, port, baud, radio_cb=None):
        self.ser = serial.Serial(port, baud, timeout=0.05)
        self.lock = threading.Lock()
        self.freq_hz = 14074000
        self.mode = "USB"
        self.bfo = 0
        self.rssi = 0
        self.snr = 0
        self.log_enabled = False
        self._rest = ""
        self._stop = False
        self.radio_cb = radio_cb
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        time.sleep(0.3)
        self.ensure_log()

    def close(self):
        self._stop = True
        try:
            self.ser.close()
        except Exception:
            pass

    def send(self, cmd):
        text = cmd.strip()
        if len(text) > 1:
            data = (text + "\r").encode("ascii", errors="ignore")
        else:
            data = text.encode("ascii", errors="ignore")
        with self.lock:
            self.ser.write(data)
            self.ser.flush()

    def ensure_log(self):
        time.sleep(0.4)
        if not self.log_enabled:
            self.send("t")
            time.sleep(0.3)

    def _reader(self):
        while not self._stop:
            try:
                chunk = self.ser.read(256)
            except Exception:
                time.sleep(0.2)
                continue
            if not chunk:
                continue
            self._rest += chunk.decode("ascii", errors="ignore")
            if len(self._rest) > MAX_LINE_BUF:
                self._rest = self._rest[-MAX_LINE_BUF // 2:]
            while "\n" in self._rest:
                line, self._rest = self._rest.split("\n", 1)
                self._handle_line(line.strip())

    def _handle_line(self, line):
        if not line:
            return
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 12 and re.fullmatch(r"\d{2,4}", parts[0] or ""):
            try:
                prev_hz = self.freq_hz
                raw_freq = int(float(parts[1]))
                bfo = int(float(parts[2]))
                self.mode = parts[5].upper()
                self.bfo = bfo
                self.rssi = int(float(parts[10]))
                self.snr = int(float(parts[11]))
                if self.mode == "FM":
                    if raw_freq > 100000:
                        self.freq_hz = raw_freq
                    else:
                        self.freq_hz = raw_freq * 10000
                elif raw_freq > 100000:
                    self.freq_hz = raw_freq
                else:
                    self.freq_hz = raw_freq * 1000 + bfo
                self.log_enabled = True
                if self.radio_cb and self.freq_hz != prev_hz:
                    self.radio_cb(self.freq_hz)
            except (ValueError, IndexError):
                pass

    def set_frequency(self, hz):
        hz = int(hz)
        self.send("F%d" % hz)
        self.freq_hz = hz
        return True

    def set_mode(self, hamlib_mode):
        want = HAMLIB_TO_ATS.get(hamlib_mode.upper())
        if not want:
            return False
        for _ in range(6):
            if self.mode == want:
                return True
            self.send("M")
            time.sleep(0.15)
        self.mode = want
        return True


class RigctldServer:
    def __init__(self, radio, host, port, wsjtx_cb=None):
        self.radio = radio
        self.host = host
        self.port = port
        self.wsjtx_cb = wsjtx_cb
        self.passband = 2700
        self.vfo = "VFOA"
        self.ptt = 0
        self.split = 0
        self._sock = None
        self._stop = False
        self._thread = None

    def start(self):
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop = True
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    def _serve(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)
        self._sock = sock
        try:
            sock.bind((self.host, self.port))
            sock.listen(8)
            while not self._stop:
                try:
                    client, addr = sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=self._client, args=(client,), daemon=True).start()
        except Exception:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _client(self, sock):
        sock.settimeout(120)
        rest = ""
        try:
            while not self._stop:
                data = sock.recv(4096)
                if not data:
                    break
                rest += data.decode("ascii", errors="ignore")
                if len(rest) > MAX_LINE_BUF:
                    rest = rest[-MAX_LINE_BUF // 2:]
                while "\n" in rest:
                    line, rest = rest.split("\n", 1)
                    reply = self.handle(line.strip())
                    if reply is None:
                        continue
                    sock.sendall(reply.encode("ascii", errors="ignore"))
        except OSError:
            pass
        finally:
            sock.close()

    def handle(self, raw):
        if not raw:
            return None
        if raw.startswith("+"):
            raw = raw[1:]
        if raw.startswith("\\"):
            parts = raw[1:].split()
            return self._dispatch_long(parts[0].lower() if parts else "", parts[1:])
        parts = raw.split()
        if not parts:
            return None
        return self._dispatch_short(parts[0], parts[1:])

    def _dispatch_long(self, cmd, args):
        mapping = {
            "set_freq": lambda: self._set_freq(args),
            "get_freq": lambda: self._get_freq(),
            "set_mode": lambda: self._set_mode(args),
            "get_mode": lambda: self._get_mode(),
            "set_vfo": lambda: self._ok(),
            "get_vfo": lambda: self.vfo + "\n",
            "set_ptt": lambda: self._set_ptt(args),
            "get_ptt": lambda: "%d\n" % self.ptt,
            "set_split_vfo": lambda: self._set_split(args),
            "get_split_vfo": lambda: "%d\nVFOA\n" % self.split,
            "set_split_freq": lambda: self._ok(),
            "get_split_freq": lambda: "%d\n" % self.radio.freq_hz,
            "set_rit": lambda: self._ok(),
            "get_rit": lambda: "0\n",
            "set_xit": lambda: self._ok(),
            "get_xit": lambda: "0\n",
            "get_powerstat": lambda: "1\n",
            "set_powerstat": lambda: self._ok(),
            "dump_state": lambda: DUMP_STATE,
            "dump_caps": lambda: DUMP_STATE,
            "chk_vfo": lambda: "0\n",
            "set_vfo_opt": lambda: self._ok(),
            "get_info": lambda: "ATS Mini\n",
            "get_dcd": lambda: "1\n",
            "get_level": lambda: self._get_level(args),
            "set_level": lambda: self._ok(),
        }
        fn = mapping.get(cmd)
        if fn is None:
            return "RPRT %d\n" % RIG_ENAVAIL
        return fn()

    def _dispatch_short(self, cmd, args):
        if args and args[0] in {
            "VFOA", "VFOB", "currVFO", "VFO", "Main", "Sub", "TX", "RX"
        }:
            if cmd not in {"V", "set_vfo"}:
                args = args[1:]
        table = {
            "F": lambda: self._set_freq(args),
            "f": lambda: self._get_freq(),
            "M": lambda: self._set_mode(args),
            "m": lambda: self._get_mode(),
            "V": lambda: self._ok(),
            "v": lambda: self.vfo + "\n",
            "T": lambda: self._set_ptt(args),
            "t": lambda: "%d\n" % self.ptt,
            "S": lambda: self._set_split(args),
            "s": lambda: "%d\nVFOA\n" % self.split,
            "I": lambda: self._ok(),
            "i": lambda: "%d\n" % self.radio.freq_hz,
            "J": lambda: self._ok(),
            "j": lambda: "0\n",
            "Z": lambda: self._ok(),
            "z": lambda: "0\n",
            "q": lambda: None,
            "Q": lambda: None,
            "_": lambda: "ATS Mini\n",
        }
        if cmd in {"dump_state", "\\dump_state"}:
            return DUMP_STATE
        fn = table.get(cmd)
        if fn is None:
            return "RPRT %d\n" % RIG_ENAVAIL
        return fn()

    def _ok(self):
        return "RPRT %d\n" % RIG_OK

    def _set_freq(self, args):
        if not args:
            return "RPRT %d\n" % RIG_EINVAL
        try:
            hz = int(float(args[0]))
        except ValueError:
            return "RPRT %d\n" % RIG_EINVAL
        self.radio.set_frequency(hz)
        if self.wsjtx_cb:
            self.wsjtx_cb(hz)
        return self._ok()

    def _get_freq(self):
        return "%d\n" % int(self.radio.freq_hz)

    def _set_mode(self, args):
        if not args:
            return "RPRT %d\n" % RIG_EINVAL
        if args[0] == "?":
            return "USB LSB AM FM\n"
        mode = args[0].upper()
        if len(args) >= 2:
            try:
                pb = int(float(args[1]))
                if pb > 0:
                    self.passband = pb
            except ValueError:
                pass
        if not self.radio.set_mode(mode):
            return "RPRT %d\n" % RIG_EINVAL
        return self._ok()

    def _get_mode(self):
        return "%s\n%d\n" % (self.radio.mode, self.passband)

    def _set_ptt(self, args):
        if args:
            try:
                self.ptt = 1 if int(args[0]) else 0
            except ValueError:
                return "RPRT %d\n" % RIG_EINVAL
        return self._ok()

    def _set_split(self, args):
        if args:
            token = args[0].upper()
            self.split = 0 if token in {"0", "OFF"} else 1
        return self._ok()

    def _get_level(self, args):
        name = args[0].upper() if args else ""
        if name == "STRENGTH":
            return "%d\n" % (self.radio.rssi - 73)
        if name in {"SQLSTAT", "RAWSTR"}:
            return "%d\n" % self.radio.rssi
        return "0\n"


def fmt_freq(hz):
    if hz is None:
        return "-"
    if hz >= 1000000:
        return "%.4f MHz" % (hz / 1000000.0)
    return "%.1f kHz" % (hz / 1000.0)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ATS Mini WSJT-X Proxy")
        self.geometry("520x280")
        self.minsize(420, 240)

        self.radio = None
        self.server = None
        self._pending_wsjtx = None
        self._pending_radio = None
        self._ui_job = None

        self._build()
        self._refresh_ports()

    def _build(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        row = ttk.Frame(frm)
        row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(row, text="Serial port").pack(side=tk.LEFT)
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(row, textvariable=self.port_var, width=28)
        self.port_cb.pack(side=tk.LEFT, padx=6)
        ttk.Button(row, text="Refresh", command=self._refresh_ports).pack(side=tk.LEFT)

        row2 = ttk.Frame(frm)
        row2.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(row2, text="Baud").pack(side=tk.LEFT)
        self.baud_var = tk.StringVar(value="115200")
        ttk.Combobox(
            row2, textvariable=self.baud_var, width=10,
            values=["9600", "115200"], state="readonly"
        ).pack(side=tk.LEFT, padx=6)
        ttk.Label(row2, text="Listen").pack(side=tk.LEFT, padx=(12, 0))
        self.listen_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(row2, textvariable=self.listen_var, width=14).pack(side=tk.LEFT, padx=4)
        ttk.Label(row2, text="Port").pack(side=tk.LEFT)
        self.tcp_var = tk.StringVar(value="4532")
        ttk.Entry(row2, textvariable=self.tcp_var, width=6).pack(side=tk.LEFT, padx=4)

        row3 = ttk.Frame(frm)
        row3.pack(fill=tk.X, pady=(0, 8))
        self.btn_start = ttk.Button(row3, text="Start", command=self.start)
        self.btn_start.pack(side=tk.LEFT)
        self.btn_stop = ttk.Button(row3, text="Stop", command=self.stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=6)
        self.status_lbl = ttk.Label(row3, text="Stopped", foreground="gray")
        self.status_lbl.pack(side=tk.LEFT, padx=12)

        info = ttk.LabelFrame(frm, text="Frequency", padding=8)
        info.pack(fill=tk.X, pady=(0, 8))
        self.wsjtx_lbl = ttk.Label(info, text="WSJT-X: -", font=("Segoe UI", 14, "bold"))
        self.wsjtx_lbl.pack(anchor=tk.W)
        self.radio_lbl = ttk.Label(info, text="Radio: -", font=("Segoe UI", 14, "bold"))
        self.radio_lbl.pack(anchor=tk.W)

        hint = ttk.Label(
            frm,
            text="WSJT-X Settings Radio: Hamlib NET rigctl  127.0.0.1:4532  PTT VOX  Mode USB\n"
                 "On the radio: band ALL, USB Port = Ad hoc, firmware 2.34 or newer",
            justify=tk.LEFT,
        )
        hint.pack(fill=tk.X)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def _on_wsjtx_freq(self, hz):
        self._pending_wsjtx = hz
        self._schedule_ui()

    def _on_radio_freq(self, hz):
        self._pending_radio = hz
        self._schedule_ui()

    def _schedule_ui(self):
        if self._ui_job is None:
            self._ui_job = self.after(UI_FLUSH_MS, self._flush_ui)

    def _flush_ui(self):
        self._ui_job = None
        if self._pending_wsjtx is not None:
            self.wsjtx_lbl.config(text="WSJT-X: %s" % fmt_freq(self._pending_wsjtx))
            self._pending_wsjtx = None
        if self._pending_radio is not None:
            self.radio_lbl.config(text="Radio: %s" % fmt_freq(self._pending_radio))
            self._pending_radio = None

    def _cancel_ui_job(self):
        if self._ui_job is not None:
            try:
                self.after_cancel(self._ui_job)
            except Exception:
                pass
            self._ui_job = None
        self._pending_wsjtx = None
        self._pending_radio = None

    def start(self):
        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("Error", "Select a serial port")
            return
        try:
            baud = int(self.baud_var.get())
            tcp = int(self.tcp_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid baud or TCP port")
            return
        host = self.listen_var.get().strip() or "127.0.0.1"
        try:
            self.radio = ATSMini(port, baud, radio_cb=self._on_radio_freq)
            self.server = RigctldServer(self.radio, host, tcp, wsjtx_cb=self._on_wsjtx_freq)
            self.server.start()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            if self.radio:
                self.radio.close()
                self.radio = None
            return
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.status_lbl.config(text="Running on %s:%s" % (host, tcp), foreground="green")

    def stop(self):
        self._cancel_ui_job()
        if self.server:
            self.server.stop()
            self.server = None
        if self.radio:
            self.radio.close()
            self.radio = None
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_lbl.config(text="Stopped", foreground="gray")
        self.wsjtx_lbl.config(text="WSJT-X: -")
        self.radio_lbl.config(text="Radio: -")

    def _on_close(self):
        self.stop()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
