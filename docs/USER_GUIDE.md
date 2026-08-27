# User Guide — ATS Mini Hamlib Bridge

This guide explains how `bridgemb.py` connects **WSJT-X** and **MSHV** to an **ATS Mini** receiver so those programs can change frequency and mode on the radio.

## 1. What the bridge does

Amateur digital-mode programs expect a CAT radio they can drive through **Hamlib**. The usual choice in both WSJT-X and MSHV is:

- Rig model: **Hamlib NET rigctl**
- Server: `127.0.0.1:4532`

That protocol is what a real `rigctld` daemon speaks. The ATS Mini does not run Hamlib. It accepts single-letter **Ad hoc** commands over USB serial (or Bluetooth LE). The important ones used here are:

| Radio command | Meaning |
| --- | --- |
| `F14074000` | Tune to 14 074 000 Hz (must be inside the **current band**) |
| `M` / `m` | Next / previous modulation |
| `t` | Toggle the CSV monitor log on or off |

The bridge:

1. Opens the radio serial port and turns the monitor log on (`t`).
2. Listens on TCP port **4532** and answers Hamlib short commands (`F`, `f`, `M`, `m`, …) and long / extended commands (`\\set_freq`, `\\get_mode`, `+dump_state`, …).
3. Translates Hamlib frequency/mode into Ad hoc commands.
4. Parses the radio’s CSV log so the GUI and Hamlib `get_freq` / `get_level` stay in step with the front panel.

```
  +------------+   Hamlib NET      +-------------+   USB 115200     +----------+
  | WSJT-X or  |  127.0.0.1:4532   |  bridgemb   |   Ad hoc proto   | ATS Mini |
  |   MSHV     | ----------------->|   .py GUI   | ---------------->| receiver |
  +------------+                   +-------------+                  +----------+
        ^                                                                 |
        |  audio (3.5 mm -> PC sound card)                                |
        +-----------------------------------------------------------------+
```

### Receiver, not transceiver

The ATS Mini (Si4732) is a **broadcast / amateur receiver**. It cannot transmit.

- Frequency and mode control work.
- `set_ptt` / `T` are accepted and remembered so WSJT-X and MSHV do not throw CAT errors. Nothing is keyed on the ATS Mini.
- For a complete digital-mode station you either:
  - decode only (receive FT8/FT4 etc. from the ATS Mini audio), or
  - transmit with a **separate** transceiver and use VOX / hardware PTT on that radio.

Set PTT in WSJT-X / MSHV to **VOX** unless you have another CAT/PTT path.

## 2. Radio preparation

Use firmware **2.34 or newer**. Direct tune (`F`) and USB Ad hoc remote control were introduced around that series. Check [ATS Mini releases](https://github.com/esp32-si4732/ats-mini/releases).

On the radio:

1. **Settings → USB Port → Ad hoc**  
   Remote control is off by default. If this stays Off, the COM port may appear but commands will be ignored.
2. **Band = ALL** (or a band that already contains the frequency you will request).  
   The firmware `F` command **will not leave the current band**. If you stay on “20M” and WSJT-X asks for 7.074 MHz, the radio will not QSY. Band ALL avoids that trap for HF digital work.
3. Mode **USB** for FT8/FT4/MSK144 on HF.
4. Plug in a **data-capable** USB-C cable (charge-only cables give no serial port).
5. Optional but useful: plug the 3.5 mm audio output into the PC line-in or a USB sound card. USB power can inject hum; a short, decent lead and a USB isolator or battery power help.

Default serial settings: **115200 8N1**. 9600 is offered in the GUI if 115200 is unreliable on your cable.

Typical port names:

| OS | Device |
| --- | --- |
| Windows | `COMx` (USB JTAG / USB Serial) |
| Linux | `/dev/ttyACM0` or `/dev/ttyUSB0` |
| macOS | `/dev/tty.usbmodem*` |

On Linux, add your user to the `dialout` (or `uucp`) group if permission is denied:

```bash
sudo usermod -aG dialout $USER
```

Then log out and back in.

## 3. Install and start the proxy

```bash
git clone https://github.com/wzx72jdfd8-sketch/ats-mini-hamlib-bridge.git
cd ats-mini-hamlib-bridge
python3 -m pip install -r requirements.txt
python3 bridgemb.py
```

Windows (from Command Prompt or PowerShell, after Python is on PATH):

```text
py -m pip install -r requirements.txt
py bridgemb.py
```

In the window:

1. Click **Refresh** and select the ATS Mini serial port.
2. Baud: **115200** (or 9600).
3. Listen: **127.0.0.1** (stay on localhost unless you know you need LAN access).
4. Port: **4532** (Hamlib default).
5. Click **Start**. Status should turn green: `Running on 127.0.0.1:4532`.

The **Radio:** line updates when the monitor log is flowing. If it stays `-`, the radio is not in Ad hoc mode, firmware is too old, or the wrong COM port is open.

Do not leave port 4532 exposed to the public internet. Hamlib has no authentication.

## 4. WSJT-X setup

1. Start the bridge first, then WSJT-X.
2. **File → Settings → Radio**
   - Rig: **Hamlib NET rigctl**
   - Network Server: `127.0.0.1:4532`
   - PTT Method: **VOX** (recommended) or CAT if you only need the program to believe PTT succeeded
   - Mode: **USB** (or Data/Pkt if you prefer; the bridge maps PKTUSB/DIGU onto radio USB)
   - Split: **None** or **Fake It** (the proxy accepts split commands but does not implement a second VFO on the radio)
3. **File → Settings → Audio**
   - Input: the sound device fed by the ATS Mini headphone/line jack
   - Output: only needed if you transmit with another radio
4. Click **Test CAT**. It should report OK.
5. Choose a band/frequency in WSJT-X. The proxy **WSJT-X:** label and the radio dial should follow.

Polling: a 1–2 second poll interval is plenty. The radio also pushes frequency via the CSV log, so the GUI Radio line can move when you tune the encoder by hand.

## 5. MSHV setup

MSHV speaks Hamlib over TCP and prefers the **extended / long** command set. This proxy accepts both the old short protocol (`F 14074000`) and long names (`\\set_freq`, `\\get_mode`) including the `+` extended-response prefix.

In MSHV:

1. Start the bridge first.
2. Open **Options → Interface Control** (wording varies slightly by MSHV version).
3. Set the CAT / rig port to **Network** (not a raw COM port — the ATS Mini COM port is already owned by the proxy).
4. Server: `127.0.0.1`
5. Port: `4532`
6. Rig / protocol: **Hamlib** / **NET rigctl** if a list is offered.
7. PTT method: **VOX**, or **PTT via CAT command** only if you accept that PTT is acknowledged but not physically keyed on the ATS Mini.
8. Enable frequency/mode follow from the mode buttons so band changes in MSHV call `F` / `M`.
9. Sound input: same ATS Mini audio device as for WSJT-X.

Connect, then change band in MSHV. The proxy **WSJT-X:** label is simply “frequency requested by the Hamlib client”; it updates for MSHV as well.

Only one program should own the TCP port at a time in practice. You can run WSJT-X **or** MSHV against 4532. Running both at once is possible in theory (the server accepts multiple sockets) but they will fight over frequency.

## 6. Audio notes

- Sample rate in WSJT-X / MSHV: 48 000 Hz, 16-bit.
- Keep PC and radio clocks in mind for FT8: the radio does not discipline the computer clock. Use NTP or Meinberg as usual.
- USB-powered ATS Mini audio can carry switcher noise. If the waterfall is dirty, try battery power, a different USB port/cable, or a small audio isolator.

## 7. How frequency and mode are translated

### Frequency in

Hamlib `set_freq` arrives in hertz. The proxy sends `F<hz>` and stores that value for `get_freq`.

### Frequency out (log parser)

The radio monitor line is a CSV. Fields used by the proxy:

| Index | Field | Use |
| --- | --- | --- |
| 0 | firmware / app version digits | line recognition |
| 1 | `currentFrequency` | kHz (AM/SSB) or 10 kHz units (FM), unless already in Hz |
| 2 | `currentBFO` | Hz, added for SSB |
| 5 | mode | USB / LSB / AM / FM |
| 10 | RSSI | `get_level STRENGTH` = RSSI − 73 |
| 11 | SNR | stored, not currently exposed as a Hamlib level |

Reconstruction:

- FM: raw `> 100000` → already Hz; otherwise raw × 10 000
- Other modes: raw `> 100000` → already Hz; otherwise raw × 1000 + BFO

That matches the firmware rule: SSB display frequency = kHz × 1000 + BFO.

### Mode

The radio only has USB, LSB, AM and FM. Hamlib names are folded:

- USB, PKTUSB, DIGU, CW, RTTY → USB
- LSB, PKTLSB, DIGL, CWR, RTTYR → LSB
- AM, AMS, SAM, DSB → AM
- FM, WFM, PKTFM → FM

Because the radio has no “set mode to X” command, the proxy sends `M` (next mode) up to six times until the log reports the requested mode.

## 8. Limitations

- **Band limits.** `F` cannot cross the band the radio is currently in. Use band ALL for HF digital hopping.
- **No TX.** PTT is a stub. Do not expect the ATS Mini to generate RF.
- **No real split VFO.** Split commands return OK; there is only one tuned frequency.
- **RIT/XIT** always report 0.
- **Passband** is stored for Hamlib (`get_mode` returns 2700 Hz by default) but the radio bandwidth buttons are not driven.
- One serial client at a time. Close other terminals or the web controller before Start.
- Bluetooth Ad hoc is not implemented in this GUI; use USB serial.

## 9. Troubleshooting

| Symptom | What to check |
| --- | --- |
| Start fails, serial error | Wrong port; cable is charge-only; port already open in another app |
| Running, but Radio stays `-` | USB Port is not Ad hoc; send `t` failed; firmware too old for the log format |
| CAT test fails in WSJT-X | Bridge not started; wrong host/port; firewall blocking localhost (rare); another `rigctld` already on 4532 |
| Frequency does not change | Radio not on band ALL; requested QRG outside current band; still in a menu not on the VFO |
| Mode never becomes USB | Cycle modes on the radio once so the log is live; then retry |
| Dirty FT8 waterfall | USB noise on the audio jack; use battery / isolator |
| Permission denied on Linux | `dialout` group, or snap/flatpak WSJT-X sandbox cannot see 127.0.0.1 — use the system package |
| Port 4532 in use | Another Hamlib server. Change the listen port in the GUI and in WSJT-X/MSHV together |

Manual Hamlib check (with the bridge running):

```bash
echo "f" | nc -w 1 127.0.0.1 4532
echo "\\get_info" | nc -w 1 127.0.0.1 4532
```

You should see a frequency in hertz and the string `ATS Mini`.

## 10. Legal and operating notes

Operate only where your licence allows. The ATS Mini is a receiver; transmitting is a separate station with its own power, identification and EMF obligations. In the UK follow the current Ofcom amateur licence and the RSGB band plan (FT8/FT4 segments on each band).

## 11. References

- ATS Mini remote protocol: https://esp32-si4732.github.io/ats-mini/remote.html
- ATS Mini firmware: https://github.com/esp32-si4732/ats-mini
- Hamlib `rigctld` NET protocol: https://hamlib.sourceforge.net/html/rigctld.1.html
- WSJT-X user guide (Radio / Hamlib section): https://wsjt.sourceforge.io/wsjtx-main_en.html
- MSHV: https://www.lz2hv.org/mshv
