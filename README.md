# whisplay-grove-sensors

Linux/Python support for M5Stack I²C and UART Grove Units connected to the
Whisplay Grove Port.X. Port.X is selected by GPIO27 (`0 = I²C`, `1 = UART`)
and by the `whisplay-plus` device-tree overlay. I²C is the default.

The project provides:

- a catalog of M5Stack I²C/UART Grove peripherals;
- I²C bus scanning and safe address-only demos for every cataloged I²C Unit;
- line/hex monitoring demos for every cataloged UART Unit;
- decoded readings for common sensors (Ultrasonic I²C, light, SHT3x/SHT4x,
  MLX90614, SCD4x, SGP30 and GPS/NMEA);
- explicit support levels: `decoded`, `monitor`, or `probe`;
- address-conflict reporting, including the PiSugar RTC address.

## Port.X configuration

Persistent selection is made in `/boot/firmware/config.txt`:

```ini
# I2C (default): GPIO27 low
dtoverlay=whisplay-plus

# UART: GPIO27 high
dtoverlay=whisplay-plus,port_x_uart
```

Use only one of those parameters and reboot after changing it. On the tested
Whisplay system, I²C is `/dev/i2c-1` and UART is `/dev/serial0`.

## Install

```bash
sudo ./install.sh
```

The installer deploys the demo to `/opt/whisplay-grove-sensors`, creates its
Python environment, grants the desktop user the required hardware groups, and
automatically creates both `~/Desktop/05-Grove-Sensor-Hub.desktop` and the
application-menu entry. Use `--desktop-user USER` when installing without
`sudo` preserving `SUDO_USER`.

For development directly from a checkout:

```bash
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -e '.[test,ui]'
```

The user running demos must have access to `i2c` and `dialout` devices.

## Discover and run demos

```bash
whisplay-grove list
whisplay-grove list --transport i2c
whisplay-grove scan --bus 1
whisplay-grove conflicts --rtc-address 0x58

whisplay-grove demo ultrasonic-i2c
whisplay-grove demo dlight
whisplay-grove demo env-iii
whisplay-grove demo co2
whisplay-grove demo tvoc
whisplay-grove demo ncir
whisplay-grove demo nfc --interval 0.1
whisplay-grove triple-demo --interval 0.1
whisplay-grove dashboard

whisplay-grove demo gps-v11 --port /dev/serial0
whisplay-grove demo uhf-rfid --port /dev/serial0 --baud 115200
```

`demo` runs continuously until Ctrl-C. For a Unit whose proprietary protocol
has not yet been decoded, the demo deliberately performs only a safe I²C
address probe or a read-only UART monitor.

The NFC demo continuously polls ISO14443A cards. It prints a newly presented
card's UID and emits one short speaker beep; keeping the same card in the field
does not cause repeated beeps.

`triple-demo` tests NFC (`0x50`), Joystick2 (`0x63`) and Scroll (`0x40`) at
the same time. It lights both input Units, continuously prints joystick axes,
buttons and rotary encoder values as JSON, and reports ISO14443A card UIDs.

## Aggregate touch dashboard

`whisplay-grove dashboard` opens a full-screen touch UI. The I2C/UART tabs
switch Port.X electrically through GPIO27, and panels appear as Units are
detected. Decoded Units show live engineering values; every other cataloged
I2C Unit gets an online/address/candidate panel. UART mode cycles the catalog's
common baud rates, decodes NMEA GPS data, and shows a safe raw monitor for all
other UART Units. Distinct non-blocking sound cues identify new NFC cards,
input/presence/environment events, UART traffic, and Unit insertion/removal;
pass `--mute` to disable them. Use `--windowed` when developing from a desktop
session.

The repository also includes `whisplay-grove-sensors.desktop` and
`run-dashboard.sh`; `install.sh` deploys both automatically. Reopening the
shortcut safely raises the single dashboard instance instead of starting
competing I2C users.

## Address notes

The tested PiSugar RTC has been moved to `0x58`. That avoids the M5Stack
Ultrasonic I²C address (`0x57`), but conflicts with the SGP30 used by the TVOC
Unit (`0x58`). Use only one at a time or place one behind an I²C multiplexer.

Addresses and product revisions change. Run `scan` and check the exact SKU
before connecting multiple Units. Raspberry Pi GPIO is not 5 V tolerant; the
Grove connector alone does not guarantee that an unknown third-party board has
3.3 V-safe SDA/SCL pull-ups.

## Support levels

- `decoded`: the CLI returns structured engineering values.
- `monitor`: serial data can be inspected without sending device commands.
- `probe`: the Unit is cataloged and its presence can be checked safely; a
  high-level Linux protocol implementation is still pending.

See [docs/M5STACK_UNITS.md](docs/M5STACK_UNITS.md) for the complete inventory.
