"""Small Linux bus adapters used by the drivers and CLI."""

from __future__ import annotations

from contextlib import AbstractContextManager


class I2CBus(AbstractContextManager["I2CBus"]):
    def __init__(self, bus: int = 1):
        try:
            from smbus2 import SMBus
        except ImportError as exc:
            raise RuntimeError("smbus2 is required: pip install smbus2") from exc
        self.number = bus
        self._bus = SMBus(bus)

    def close(self) -> None:
        self._bus.close()

    def __exit__(self, *args: object) -> None:
        self.close()

    def write(self, address: int, data: bytes) -> None:
        from smbus2 import i2c_msg

        self._bus.i2c_rdwr(i2c_msg.write(address, data))

    def read(self, address: int, length: int) -> bytes:
        from smbus2 import i2c_msg

        msg = i2c_msg.read(address, length)
        self._bus.i2c_rdwr(msg)
        return bytes(msg)

    def exchange(self, address: int, output: bytes, read_length: int) -> bytes:
        from smbus2 import i2c_msg

        write_msg = i2c_msg.write(address, output)
        read_msg = i2c_msg.read(address, read_length)
        self._bus.i2c_rdwr(write_msg, read_msg)
        return bytes(read_msg)

    def read_register(self, address: int, register: int, length: int) -> bytes:
        return self.exchange(address, bytes((register,)), length)

    def probe(self, address: int) -> bool:
        try:
            self._bus.write_quick(address)
            return True
        except OSError:
            try:
                self._bus.read_byte(address)
                return True
            except OSError:
                return False

    def scan(self) -> list[int]:
        return [address for address in range(0x03, 0x78) if self.probe(address)]


class SerialPort(AbstractContextManager["SerialPort"]):
    def __init__(self, port: str = "/dev/serial0", baudrate: int = 115200,
                 timeout: float = 1.0):
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("pyserial is required: pip install pyserial") from exc
        self._serial = serial.Serial(port, baudrate=baudrate, timeout=timeout)

    def close(self) -> None:
        self._serial.close()

    def __exit__(self, *args: object) -> None:
        self.close()

    def readline(self) -> bytes:
        return self._serial.readline()

    def read(self, size: int = 256) -> bytes:
        return self._serial.read(size)

    def write(self, data: bytes) -> int:
        return self._serial.write(data)

