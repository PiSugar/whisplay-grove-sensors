# whisplay-grove-sensors

Linux/Python support for M5Stack I²C and UART Grove Units connected to the
Whisplay Grove Port.X. Port.X is selected by GPIO27 (`0 = UART`, `1 = I²C`)
and by the `whisplay-plus` device-tree overlay.

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
# I2C: GPIO27 high
dtoverlay=whisplay-plus,port_x_i2c

# UART: GPIO27 low
dtoverlay=whisplay-plus,port_x_uart
```

Use only one of those parameters and reboot after changing it. On the tested
Whisplay system, I²C is `/dev/i2c-1` and UART is `/dev/serial0`.

## Install

```bash
sudo apt install python3-venv i2c-tools
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
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

whisplay-grove demo gps-v11 --port /dev/serial0
whisplay-grove demo uhf-rfid --port /dev/serial0 --baud 115200
```

`demo` runs continuously until Ctrl-C. For a Unit whose proprietary protocol
has not yet been decoded, the demo deliberately performs only a safe I²C
address probe or a read-only UART monitor.

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

