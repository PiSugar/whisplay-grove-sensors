"""Command-line demos for all cataloged I2C and UART Units."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict

from .bus import I2CBus, SerialPort
from .catalog import PERIPHERALS, find_conflicts, get_peripheral
from .drivers import DRIVERS, NMEAParser
from .nfc import ST25R3916
from .triple_demo import run as run_triple_demo


def _address(value: str) -> int:
    address = int(value, 0)
    if not 0x03 <= address <= 0x77:
        raise argparse.ArgumentTypeError("I2C address must be between 0x03 and 0x77")
    return address


def _list(args: argparse.Namespace) -> int:
    for item in PERIPHERALS:
        if args.transport and item.transport != args.transport:
            continue
        detail = ",".join(f"0x{x:02x}" for x in item.addresses)
        if item.baudrate:
            detail = str(item.baudrate)
        print(f"{item.slug:20} {item.transport:4} {item.support:7} {detail:13} {item.name}")
    return 0


def _scan(args: argparse.Namespace) -> int:
    with I2CBus(args.bus) as bus:
        addresses = bus.scan()
    print(" ".join(f"0x{x:02x}" for x in addresses) or "no I2C devices found")
    for address in addresses:
        matches = find_conflicts(address)
        names = ", ".join(item.name for item in matches) or "unknown"
        print(f"0x{address:02x}: {names}")
    return 0


def _conflicts(args: argparse.Namespace) -> int:
    addresses = list(args.address)
    if args.rtc_address is not None:
        addresses.append(args.rtc_address)
    if not addresses:
        raise SystemExit("provide an address, for example: conflicts 0x58")
    for address in addresses:
        matches = find_conflicts(address)
        print(f"0x{address:02x}: " + (", ".join(x.name for x in matches) or "no catalog match"))
    return 0


def _demo_i2c(args: argparse.Namespace, item) -> int:
    if item.driver == "nfc":
        return _demo_nfc(args, item)
    address = args.address
    if address is None and len(item.addresses) == 1:
        address = item.addresses[0]
    with I2CBus(args.bus) as bus:
        if item.driver in DRIVERS:
            driver_type = DRIVERS[item.driver]
            sensor = driver_type(bus, address)
            while True:
                value = sensor.read()
                if value is not None:
                    print(json.dumps(value, ensure_ascii=False), flush=True)
                time.sleep(args.interval)
        addresses = (address,) if address is not None else item.addresses
        if not addresses:
            print(f"{item.name}: address is revision-dependent; full bus scan follows")
            addresses = tuple(bus.scan())
        for candidate in addresses:
            state = "present" if bus.probe(candidate) else "not found"
            print(f"{item.name} at 0x{candidate:02x}: {state}")
    return 0


def _beep() -> None:
    try:
        subprocess.run(
            (
                "sox", "-q", "-n", "-t", "alsa", "plughw:CARD=whisplaysound",
                "synth", "0.08", "sine", "1200",
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        print("\a", end="", flush=True)


def _demo_nfc(args: argparse.Namespace, item) -> int:
    address = args.address if args.address is not None else item.addresses[0]
    last_uid: bytes | None = None
    last_seen = 0.0
    with I2CBus(args.bus) as bus:
        reader = ST25R3916(bus, address)
        chip_type, revision = reader.begin()
        print(
            f"{item.name} ready at 0x{address:02x} "
            f"(type={chip_type}, revision={revision}); present a card",
            flush=True,
        )
        try:
            while True:
                card = reader.detect()
                now = time.monotonic()
                if card is not None:
                    if card.uid != last_uid:
                        print(
                            f"card UID={card.uid_hex} ATQA=0x{card.atqa:04x} "
                            f"SAK=0x{card.sak:02x}",
                            flush=True,
                        )
                        _beep()
                    last_uid = card.uid
                    last_seen = now
                elif last_uid is not None and now - last_seen >= 0.8:
                    last_uid = None
                time.sleep(max(0.05, args.interval))
        finally:
            reader.close()


def _demo_uart(args: argparse.Namespace, item) -> int:
    baudrate = args.baud or item.baudrate
    if baudrate is None:
        raise SystemExit(f"{item.name} baud rate is revision-dependent; supply --baud")
    parser = NMEAParser() if item.driver == "nmea" else None
    with SerialPort(args.port, baudrate, timeout=1) as port:
        while True:
            data = port.readline()
            if not data:
                continue
            text = data.decode("ascii", errors="replace").strip()
            if parser:
                fix = parser.feed(text)
                if text[3:6] in ("RMC", "GGA"):
                    print(json.dumps(asdict(fix), ensure_ascii=False), flush=True)
            else:
                print(text if text else data.hex(" "), flush=True)


def _demo(args: argparse.Namespace) -> int:
    try:
        item = get_peripheral(args.device)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc
    return _demo_i2c(args, item) if item.transport == "i2c" else _demo_uart(args, item)


def _triple_demo(args: argparse.Namespace) -> int:
    return run_triple_demo(args.bus, args.interval)


def _dashboard(args: argparse.Namespace) -> int:
    from .dashboard import DashboardApp, DashboardBackend

    backend = DashboardBackend(args.mode, args.bus, args.port, sound=not args.mute)
    return DashboardApp(
        backend, args.windowed, args.width, args.height
    ).run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="whisplay-grove")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="list supported M5Stack Grove Units")
    list_parser.add_argument("--transport", choices=("i2c", "uart"))
    list_parser.set_defaults(func=_list)

    scan = sub.add_parser("scan", help="scan an I2C bus and identify known Units")
    scan.add_argument("--bus", type=int, default=1)
    scan.set_defaults(func=_scan)

    conflicts = sub.add_parser("conflicts", help="show Units using one or more addresses")
    conflicts.add_argument("address", nargs="*", type=_address)
    conflicts.add_argument("--rtc-address", type=_address,
                           help="also check the configured PiSugar RTC address")
    conflicts.set_defaults(func=_conflicts)

    demo = sub.add_parser("demo", help="run the demo for a cataloged Unit")
    demo.add_argument("device", help="slug printed by the list command")
    demo.add_argument("--bus", type=int, default=1)
    demo.add_argument("--address", type=_address)
    demo.add_argument("--port", default="/dev/serial0")
    demo.add_argument("--baud", type=int)
    demo.add_argument("--interval", type=float, default=1.0)
    demo.set_defaults(func=_demo)

    triple = sub.add_parser(
        "triple-demo", help="test NFC, Joystick2 and Scroll together"
    )
    triple.add_argument("--bus", type=int, default=1)
    triple.add_argument("--interval", type=float, default=0.1)
    triple.set_defaults(func=_triple_demo)

    dashboard = sub.add_parser(
        "dashboard", help="open the aggregate touch UI for every Grove Unit"
    )
    dashboard.add_argument("--mode", choices=("i2c", "uart"), default="i2c")
    dashboard.add_argument("--bus", type=int, default=1)
    dashboard.add_argument("--port", default="/dev/serial0")
    dashboard.add_argument("--windowed", action="store_true")
    dashboard.add_argument("--width", type=int, default=720)
    dashboard.add_argument("--height", type=int, default=720)
    dashboard.add_argument("--mute", action="store_true")
    dashboard.set_defaults(func=_dashboard)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except PermissionError as exc:
        raise SystemExit(f"device permission denied: {exc}") from exc
    except OSError as exc:
        raise SystemExit(f"device I/O failed: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
