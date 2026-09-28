"""Combined live demo for NFC Unit, Joystick2 and Scroll."""

from __future__ import annotations

import json
import time

from .bus import I2CBus
from .drivers import Joystick2, Scroll
from .nfc import ST25R3916


ADDRESSES = {"scroll": 0x40, "nfc": 0x50, "joystick2": 0x63}


def run(bus_number: int = 1, interval: float = 0.1) -> int:
    """Continuously print readings from all three Units as JSON lines."""
    with I2CBus(bus_number) as bus:
        missing = [name for name, address in ADDRESSES.items() if not bus.probe(address)]
        if missing:
            details = ", ".join(f"{name}=0x{ADDRESSES[name]:02x}" for name in missing)
            raise RuntimeError(f"missing I2C Unit(s): {details}")

        joystick = Joystick2(bus)
        scroll = Scroll(bus)
        nfc = ST25R3916(bus)
        chip_type, nfc_revision = nfc.begin()

        # Visible proof that both input Unit controllers accepted writes.
        joystick.set_rgb(0, 48, 96)
        scroll.set_rgb(0, 96, 32)
        print(json.dumps({
            "event": "ready",
            "addresses": {name: f"0x{address:02x}" for name, address in ADDRESSES.items()},
            "joystick2_firmware": joystick.firmware_version(),
            "scroll_firmware": scroll.firmware_version(),
            "nfc_chip_type": chip_type,
            "nfc_revision": nfc_revision,
        }), flush=True)

        last_uid: bytes | None = None
        last_seen = 0.0
        try:
            while True:
                now = time.monotonic()
                card = nfc.detect()
                if card is not None:
                    last_uid = card.uid
                    last_seen = now
                elif last_uid is not None and now - last_seen >= 0.8:
                    last_uid = None

                print(json.dumps({
                    "joystick2": joystick.read(),
                    "scroll": scroll.read(),
                    "nfc": None if card is None else {
                        "uid": card.uid_hex,
                        "atqa": f"0x{card.atqa:04x}",
                        "sak": f"0x{card.sak:02x}",
                    },
                    "nfc_card_present": last_uid is not None,
                }), flush=True)
                time.sleep(max(0.05, interval))
        finally:
            joystick.set_rgb(0, 0, 0)
            scroll.set_rgb(0, 0, 0)
            nfc.close()

