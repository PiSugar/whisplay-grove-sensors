"""Decoded drivers for common M5Stack Grove sensors."""

from __future__ import annotations

import time
from dataclasses import dataclass


def sensirion_crc(data: bytes) -> int:
    crc = 0xFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def _valid_word(data: bytes) -> int:
    if len(data) != 3 or sensirion_crc(data[:2]) != data[2]:
        raise ValueError("sensor CRC mismatch")
    return int.from_bytes(data[:2], "big")


class UltrasonicI2C:
    address = 0x57

    def __init__(self, bus, address: int | None = None):
        self.bus = bus
        self.address = address or self.address

    def read(self) -> dict[str, float]:
        self.bus.write(self.address, b"\x01")
        time.sleep(0.12)
        raw = self.bus.read(self.address, 3)
        millimetres = int.from_bytes(raw, "big") / 1000.0
        return {"distance_mm": millimetres, "distance_cm": millimetres / 10.0}


class BH1750:
    address = 0x23

    def __init__(self, bus, address: int | None = None):
        self.bus = bus
        self.address = address or self.address
        self.bus.write(self.address, b"\x01")  # power on

    def read(self) -> dict[str, float]:
        self.bus.write(self.address, b"\x20")  # one-time high resolution
        time.sleep(0.18)
        raw = int.from_bytes(self.bus.read(self.address, 2), "big")
        return {"illuminance_lux": round(raw / 1.2, 2)}


class SHT3x:
    address = 0x44

    def __init__(self, bus, address: int | None = None):
        self.bus = bus
        self.address = address or self.address

    def read(self) -> dict[str, float]:
        self.bus.write(self.address, b"\x24\x00")
        time.sleep(0.02)
        data = self.bus.read(self.address, 6)
        temperature = _valid_word(data[:3])
        humidity = _valid_word(data[3:])
        return {
            "temperature_c": round(-45 + 175 * temperature / 65535, 2),
            "humidity_percent": round(100 * humidity / 65535, 2),
        }


class SHT4x:
    address = 0x44

    def __init__(self, bus, address: int | None = None):
        self.bus = bus
        self.address = address or self.address

    def read(self) -> dict[str, float]:
        self.bus.write(self.address, b"\xFD")
        time.sleep(0.01)
        data = self.bus.read(self.address, 6)
        temperature = _valid_word(data[:3])
        humidity = _valid_word(data[3:])
        return {
            "temperature_c": round(-45 + 175 * temperature / 65535, 2),
            "humidity_percent": round(max(0, min(100, -6 + 125 * humidity / 65535)), 2),
        }


class MLX90614:
    address = 0x5A

    def __init__(self, bus, address: int | None = None):
        self.bus = bus
        self.address = address or self.address

    def _temperature(self, register: int) -> float:
        data = self.bus.read_register(self.address, register, 3)
        raw = int.from_bytes(data[:2], "little")
        return round(raw * 0.02 - 273.15, 2)

    def read(self) -> dict[str, float]:
        return {
            "ambient_temperature_c": self._temperature(0x06),
            "object_temperature_c": self._temperature(0x07),
        }


class SCD4x:
    address = 0x62

    def __init__(self, bus, address: int | None = None):
        self.bus = bus
        self.address = address or self.address
        self.bus.write(self.address, b"\x21\xB1")

    def read(self) -> dict[str, float] | None:
        self.bus.write(self.address, b"\xE4\xB8")
        time.sleep(0.002)
        ready = self.bus.read(self.address, 3)
        if not (_valid_word(ready) & 0x07FF):
            return None
        self.bus.write(self.address, b"\xEC\x05")
        time.sleep(0.002)
        data = self.bus.read(self.address, 9)
        co2 = _valid_word(data[0:3])
        temperature = _valid_word(data[3:6])
        humidity = _valid_word(data[6:9])
        return {
            "co2_ppm": co2,
            "temperature_c": round(-45 + 175 * temperature / 65535, 2),
            "humidity_percent": round(100 * humidity / 65535, 2),
        }


class SGP30:
    address = 0x58

    def __init__(self, bus, address: int | None = None):
        self.bus = bus
        self.address = address or self.address
        self.bus.write(self.address, b"\x20\x03")
        time.sleep(0.01)

    def read(self) -> dict[str, int]:
        self.bus.write(self.address, b"\x20\x08")
        time.sleep(0.02)
        data = self.bus.read(self.address, 6)
        return {"eco2_ppm": _valid_word(data[:3]), "tvoc_ppb": _valid_word(data[3:])}


DRIVERS = {
    "ultrasonic": UltrasonicI2C,
    "bh1750": BH1750,
    "sht3x": SHT3x,
    "sht4x": SHT4x,
    "mlx90614": MLX90614,
    "scd4x": SCD4x,
    "sgp30": SGP30,
}


@dataclass(slots=True)
class NMEAFix:
    utc: str | None = None
    valid: bool = False
    latitude: float | None = None
    longitude: float | None = None
    satellites: int = 0
    altitude_m: float | None = None


def _coordinate(value: str, hemisphere: str) -> float | None:
    if not value or not hemisphere:
        return None
    degree_digits = 2 if hemisphere in ("N", "S") else 3
    result = float(value[:degree_digits]) + float(value[degree_digits:]) / 60
    return -result if hemisphere in ("S", "W") else result


class NMEAParser:
    def __init__(self):
        self.fix = NMEAFix()

    def feed(self, sentence: str) -> NMEAFix:
        sentence = sentence.strip()
        if not sentence.startswith("$"):
            return self.fix
        fields = sentence.split("*")[0].split(",")
        kind = fields[0][-3:]
        try:
            if kind == "RMC" and len(fields) >= 7:
                self.fix.utc = fields[1] or self.fix.utc
                self.fix.valid = fields[2] == "A"
                self.fix.latitude = _coordinate(fields[3], fields[4])
                self.fix.longitude = _coordinate(fields[5], fields[6])
            elif kind == "GGA" and len(fields) >= 10:
                self.fix.utc = fields[1] or self.fix.utc
                self.fix.valid = fields[6] not in ("", "0")
                self.fix.satellites = int(fields[7] or 0)
                self.fix.altitude_m = float(fields[9]) if fields[9] else None
        except (ValueError, IndexError):
            pass
        return self.fix

