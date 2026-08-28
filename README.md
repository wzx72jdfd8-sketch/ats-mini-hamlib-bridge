# ATS Mini Hamlib Bridge

A small desktop proxy that lets **WSJT-X** and **MSHV** talk to an **ATS Mini** receiver as if it were a Hamlib radio.

The ATS Mini does not speak CAT or Hamlib. It speaks a simple USB serial “Ad hoc” protocol. This program sits in the middle:

```
WSJT-X / MSHV  --TCP 127.0.0.1:4532-->  bridgemb.py  --USB serial-->  ATS Mini
     Hamlib NET rigctl                    Hamlib server                 Ad hoc protocol
```

- Frequency changes in WSJT-X or MSHV (band buttons, DX spots, “Tune”) are sent to the radio with the `F` command.
- Mode requests such as USB / PKTUSB / DIGU are mapped onto the radio’s USB / LSB / AM / FM modes.
- Live frequency, RSSI and SNR from the radio’s monitor log are shown in the proxy window and returned to Hamlib clients.

The ATS Mini is a **receiver**. This bridge provides frequency and mode control. It accepts PTT commands so the software does not error, but it does **not** key a transmitter. Use **VOX** or a separate PTT path if you transmit with another radio.

## Features

- Tkinter GUI: serial port picker, baud, listen address and TCP port
- Built-in Hamlib `rigctld`-compatible server (short and long / extended protocol)
- Works with WSJT-X **Hamlib NET rigctl** and with MSHV network CAT
- Live **WSJT-X** and **Radio** frequency readouts
- Strength reports from the radio log (`STRENGTH` ≈ RSSI − 73)

## Requirements

- Python 3.8 or newer
- [pyserial](https://pyserial.readthedocs.io/)
- An ATS Mini on **firmware 2.34 or newer** (recommended; needed for reliable `F` direct tune)
- USB data cable
- On the radio: **Settings → USB Port → Ad hoc**, band **ALL**

```bash
python3 -m pip install -r requirements.txt
python3 bridgemb.py
```

On Debian/Ubuntu you may also need:

```bash
sudo apt install python3-tk python3-serial
```

## Quick start

1. On the ATS Mini set **USB Port = Ad hoc** and **band = ALL**.
2. Connect USB, start `bridgemb.py`, choose the COM / `/dev/ttyACM*` port, baud **115200**, listen **127.0.0.1**, port **4532**, click **Start**.
3. Point WSJT-X or MSHV at **Hamlib NET rigctl** / network CAT: `127.0.0.1:4532`.
4. Route radio audio (3.5 mm) into the computer sound device used by WSJT-X or MSHV.

Full setup, settings, limitations and troubleshooting are in the **[User Guide](docs/USER_GUIDE.md)**.

## Supported Hamlib commands

| Command | Behaviour |
| --- | --- |
| `F` / `set_freq`, `f` / `get_freq` | Set / read frequency (Hz) |
| `M` / `set_mode`, `m` / `get_mode` | Set / read mode and passband |
| `T` / `set_ptt`, `t` / `get_ptt` | Store PTT state only (not sent to the radio) |
| `dump_state`, `get_info` | Minimal caps so NET rigctl clients connect |
| `get_level STRENGTH` | RSSI converted toward an S-meter style value |

Mode mapping: USB, PKTUSB, DIGU, CW, RTTY → radio **USB**; LSB / PKTLSB / DIGL / CWR / RTTYR → **LSB**; AM family → **AM**; FM family → **FM**.

## Project files

| File | Purpose |
| --- | --- |
| `bridgemb.py` | GUI + serial driver + Hamlib TCP server |
| `docs/USER_GUIDE.md` | Step-by-step WSJT-X and MSHV setup |
| `requirements.txt` | Python dependencies |

## Licence

MIT. See [LICENSE](LICENSE).

ATS Mini firmware and protocol: [esp32-si4732/ats-mini](https://github.com/esp32-si4732/ats-mini) and [remote control docs](https://esp32-si4732.github.io/ats-mini/remote.html). WSJT-X and MSHV are separate projects and are not bundled here.
