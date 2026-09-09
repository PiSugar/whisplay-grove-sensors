from whisplay_grove.drivers import NMEAParser, UltrasonicI2C, sensirion_crc


class FakeBus:
    def __init__(self, response: bytes):
        self.response = response
        self.writes = []

    def write(self, address: int, data: bytes):
        self.writes.append((address, data))

    def read(self, address: int, length: int) -> bytes:
        assert len(self.response) == length
        return self.response


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

