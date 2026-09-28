import errno

from whisplay_grove.bus import I2CBus
from whisplay_grove.drivers import Joystick2, NMEAParser, Scroll, UltrasonicI2C, sensirion_crc
from whisplay_grove.nfc import NFCCard


class FakeBus:
    def __init__(self, response: bytes):
        self.response = response
        self.writes = []

    def write(self, address: int, data: bytes):
        self.writes.append((address, data))

    def read(self, address: int, length: int) -> bytes:
        assert len(self.response) == length
        return self.response


class FakeRegisterBus:
    def __init__(self, registers: dict[int, bytes]):
        self.registers = registers
        self.writes = []
        self.current_register = None

    def read_register(self, address: int, register: int, length: int) -> bytes:
        value = self.registers[register]
        assert len(value) == length
        return value

    def write(self, address: int, data: bytes):
        self.writes.append((address, data))
        if len(data) == 1:
            self.current_register = data[0]

    def read(self, address: int, length: int) -> bytes:
        value = self.registers[self.current_register]
        assert len(value) == length
        return value


def test_sensirion_crc_reference_vector():
    assert sensirion_crc(bytes.fromhex("BEEF")) == 0x92


def test_ultrasonic_conversion(monkeypatch):
    monkeypatch.setattr("whisplay_grove.drivers.time.sleep", lambda _: None)
    bus = FakeBus((123400).to_bytes(3, "big"))
    value = UltrasonicI2C(bus).read()
    assert bus.writes == [(0x57, b"\x01")]
    assert value == {"distance_mm": 123.4, "distance_cm": 12.34}


def test_nmea_gga_and_rmc():
    parser = NMEAParser()
    parser.feed("$GNGGA,123519.00,2233.0000,N,11403.0000,E,1,08,0.9,12.3,M,,M,,*00")
    fix = parser.feed("$GNRMC,123520.00,A,2233.0000,N,11403.0000,E,0.0,0.0,090926,,,A*00")
    assert fix.valid
    assert fix.satellites == 8
    assert fix.latitude == 22.55
    assert fix.longitude == 114.05
    assert fix.altitude_m == 12.3


def test_nfc_uid_hex():
    card = NFCCard(bytes.fromhex("04 A1 B2 C3 D4 E5 F6"), 0x4400, 0x00)
    assert card.uid_hex == "04A1B2C3D4E5F6"


def test_joystick2_decoded_reading_and_rgb():
    bus = FakeRegisterBus({
        0x00: b"\x34\x12\xcd\xab",
        0x50: b"\x00\x10\x00\xf0",
        0x20: b"\x00",
    })
    joystick = Joystick2(bus)
    assert joystick.read() == {
        "raw_x": 0x1234,
        "raw_y": 0xABCD,
        "x": 4096,
        "y": -4096,
        "pressed": True,
    }
    joystick.set_rgb(1, 2, 3)
    assert bus.writes == [(0x63, b"\x30\x03\x02\x01")]


def test_scroll_decoded_reading_and_rgb():
    bus = FakeRegisterBus({0x10: b"\xfe\xff", 0x50: b"\x03\x00", 0x20: b"\x01"})
    scroll = Scroll(bus)
    assert scroll.read() == {"value": -2, "increment": 3, "pressed": False}
    bus.writes.clear()
    scroll.set_rgb(1, 2, 3)
    assert bus.writes == [(0x40, b"\x31\x01\x02\x03")]


def test_i2c_retries_transient_remote_io(monkeypatch):
    monkeypatch.setattr("whisplay_grove.bus.time.sleep", lambda _: None)
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OSError(errno.EREMOTEIO, "temporary I2C failure")
        return b"ok"

    bus = object.__new__(I2CBus)
    assert bus._retry(operation) == b"ok"
    assert attempts == 3
