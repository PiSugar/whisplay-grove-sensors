"""Minimal ST25R3916 ISO14443A reader for the M5Stack NFC Unit."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .bus import I2CBus


OP_READ = 0x40
CMD_SPACE_B = 0xFB
CMD_SET_DEFAULT = 0xC1
CMD_STOP_ALL_ACTIVITIES = 0xC2
CMD_TRANSMIT_WITH_CRC = 0xC4
CMD_TRANSMIT_WITHOUT_CRC = 0xC5
CMD_TRANSMIT_REQA = 0xC6
CMD_TRANSMIT_WUPA = 0xC7
CMD_NFC_INITIAL_FIELD_ON = 0xC8
CMD_RESET_RX_GAIN = 0xD5
CMD_ADJUST_REGULATORS = 0xD6
CMD_CLEAR_FIFO = 0xDB
CMD_TEST_ACCESS = 0xFC
CMD_LOAD_FIFO = 0x80
CMD_READ_FIFO = 0x9F

REG_IO_CONFIGURATION_1 = 0x00
REG_IO_CONFIGURATION_2 = 0x01
REG_OPERATION_CONTROL = 0x02
REG_MODE_DEFINITION = 0x03
REG_BITRATE_DEFINITION = 0x04
REG_ISO14443A_SETTINGS = 0x05
REG_NFCIP_1_PASSIVE_TARGET_DEFINITION = 0x08
REG_AUXILIARY_DEFINITION = 0x0A
REG_RECEIVER_CONFIGURATION_1 = 0x0B
REG_RECEIVER_CONFIGURATION_2 = 0x0C
REG_RECEIVER_CONFIGURATION_3 = 0x0D
REG_RECEIVER_CONFIGURATION_4 = 0x0E
REG_NO_RESPONSE_TIMER_1 = 0x10
REG_TIMER_AND_EMV_CONTROL = 0x12
REG_MASK_MAIN_INTERRUPT = 0x16
REG_MAIN_INTERRUPT = 0x1A
REG_FIFO_STATUS_1 = 0x1E
REG_NUMBER_OF_TRANSMITTED_BYTES_1 = 0x22
REG_ANTENNA_TUNING_CONTROL_1 = 0x26
REG_ANTENNA_TUNING_CONTROL_2 = 0x27
REG_TX_DRIVER = 0x28
REG_PASSIVE_TARGET_MODULATION = 0x29
REG_EXTERNAL_FIELD_DETECTOR_ACTIVATION_THRESHOLD = 0x2A
REG_EXTERNAL_FIELD_DETECTOR_DEACTIVATION_THRESHOLD = 0x2B
REG_AUXILIARY_DISPLAY = 0x31
REG_IC_IDENTITY = 0x3F

REG_SPACE_B_EMD_SUPPRESSION = 0x05
REG_SPACE_B_RESISTIVE_AM = 0x2A
REG_SPACE_B_CORRELATOR_CONFIGURATION_1 = 0x0C
REG_SPACE_B_CORRELATOR_CONFIGURATION_2 = 0x0D
REG_SPACE_B_OVERSHOOT_PROTECTION_CONFIGURATION_1 = 0x30
REG_SPACE_B_OVERSHOOT_PROTECTION_CONFIGURATION_2 = 0x31
REG_SPACE_B_UNDERSHOOT_PROTECTION_CONFIGURATION_1 = 0x32
REG_SPACE_B_UNDERSHOOT_PROTECTION_CONFIGURATION_2 = 0x33

I_OSC = 0x80
OSC_OK = 0x10
OP_EN = 0x80
TX_EN = 0x08
RX_EN = 0x40
WU = 0x04
AAT_EN = 0x20
NO_CRC_RX = 0x80
ANTCL = 0x01
DIS_CORR = 0x04
CASCADE_TAG = 0x88
SAK_CASCADE_FLAG = 0x04
FC_HZ = 13_560_000


@dataclass(frozen=True, slots=True)
class NFCCard:
    uid: bytes
    atqa: int
    sak: int

    @property
    def uid_hex(self) -> str:
        return self.uid.hex().upper()


class ST25R3916:
    """Read ISO14443A UIDs from an ST25R3916 connected over Linux I2C."""

    def __init__(self, bus: I2CBus, address: int = 0x50):
        self.bus = bus
        self.address = address

    def _write(self, data: bytes) -> None:
        self.bus.write(self.address, data)

    def _read_register(self, register: int) -> int:
        return self.bus.read_register(self.address, register | OP_READ, 1)[0]

    def _write_register(self, register: int, value: int) -> None:
        self._write(bytes((register, value & 0xFF)))

    def _write_register16(self, register: int, value: int) -> None:
        self._write_register(register, value >> 8)
        self._write_register(register + 1, value)

    def _write_register32(self, register: int, value: int) -> None:
        for offset, shift in enumerate((24, 16, 8, 0)):
            self._write_register(register + offset, value >> shift)

    def _write_space_b(self, register: int, value: int) -> None:
        self._write(bytes((CMD_SPACE_B, register, value & 0xFF)))
        time.sleep(0.00005)

    def _command(self, command: int, payload: bytes = b"") -> None:
        self._write(bytes((command,)) + payload)
        time.sleep(0.002)

    def _set_bits(self, register: int, bits: int) -> None:
        self._write_register(register, self._read_register(register) | bits)

    def _clear_bits(self, register: int, bits: int) -> None:
        self._write_register(register, self._read_register(register) & ~bits)

    def _clear_interrupts(self) -> None:
        for register in range(REG_MAIN_INTERRUPT, REG_MAIN_INTERRUPT + 4):
            self._read_register(register)

    def _write_fifo(self, payload: bytes) -> None:
        self._write(bytes((CMD_LOAD_FIFO,)) + payload)
        time.sleep(0.00005)

    def _read_fifo(self, length: int) -> bytes:
        return self.bus.read_register(self.address, CMD_READ_FIFO, length)

    def _fifo_size(self) -> int:
        high = self._read_register(REG_FIFO_STATUS_1)
        low = self._read_register(REG_FIFO_STATUS_1 + 1)
        value = (high << 8) | low
        return (value >> 8) | ((value & 0x00C0) << 2)

    def _wait_fifo(self, minimum: int, timeout: float) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            length = self._fifo_size()
            if length >= minimum:
                return length
            time.sleep(0.001)
        return 0

    def _write_timeout(self, milliseconds: int) -> None:
        control = self._read_register(REG_TIMER_AND_EMV_CONTROL)
        step = 4096 if control & 1 else 64
        value = max(1, min(0xFFFF, (milliseconds * FC_HZ + step * 1000 - 1) // (step * 1000)))
        self._write_register16(REG_NO_RESPONSE_TIMER_1, value)

    def _write_tx_length(self, byte_count: int) -> None:
        self._write_register16(REG_NUMBER_OF_TRANSMITTED_BYTES_1, byte_count << 3)

    def _enable_oscillator(self) -> bool:
        if not self._read_register(REG_OPERATION_CONTROL) & OP_EN:
            mask = self._read_register(REG_MASK_MAIN_INTERRUPT)
            self._write_register(REG_MASK_MAIN_INTERRUPT, mask & ~I_OSC)
            self._clear_interrupts()
            self._set_bits(REG_OPERATION_CONTROL, OP_EN)
            deadline = time.monotonic() + 0.025
            started = False
            while time.monotonic() < deadline:
                time.sleep(0.001)
                if self._read_register(REG_MAIN_INTERRUPT) & I_OSC:
                    started = True
                    break
            self._set_bits(REG_MASK_MAIN_INTERRUPT, I_OSC)
            if not started:
                return False
        return bool(self._read_register(REG_AUXILIARY_DISPLAY) & OSC_OK)

    def begin(self) -> tuple[int, int]:
        identity = self._read_register(REG_IC_IDENTITY)
        chip_type, revision = (identity >> 3) & 0x1F, identity & 0x07
        if chip_type != 5 or revision == 0 or identity == 0xFF:
            raise RuntimeError(f"unexpected ST25R3916 identity 0x{identity:02x}")

        self._command(CMD_SET_DEFAULT)
        time.sleep(0.01)
        self._command(CMD_TEST_ACCESS, b"\x04\x10")
        self._write_register16(REG_IO_CONFIGURATION_1, 0x1084)
        self._write_register(REG_TX_DRIVER, 0xD0)
        value = self._read_register(REG_IO_CONFIGURATION_1)
        self._write_register(REG_IO_CONFIGURATION_1, (value & ~0x07) | 0x07)
        self._write_space_b(REG_SPACE_B_RESISTIVE_AM, 0x80)
        self._set_bits(REG_IO_CONFIGURATION_2, AAT_EN)
        self._write_space_b(REG_SPACE_B_RESISTIVE_AM, 0x00)
        self._write_register(REG_EXTERNAL_FIELD_DETECTOR_ACTIVATION_THRESHOLD, 0x13)
        self._write_register(REG_EXTERNAL_FIELD_DETECTOR_DEACTIVATION_THRESHOLD, 0x02)
        value = self._read_register(REG_NFCIP_1_PASSIVE_TARGET_DEFINITION)
        self._write_register(REG_NFCIP_1_PASSIVE_TARGET_DEFINITION, (value & ~0xF0) | 0x50)
        self._write_register(REG_PASSIVE_TARGET_MODULATION, 0x5F)
        self._write_space_b(REG_SPACE_B_EMD_SUPPRESSION, 0x40)
        self._write_register(REG_ANTENNA_TUNING_CONTROL_1, 0x82)
        self._write_register(REG_ANTENNA_TUNING_CONTROL_2, 0x82)
        self._set_bits(REG_OPERATION_CONTROL, 0x03)
        self._command(CMD_CLEAR_FIFO)
        self._write_register32(REG_MASK_MAIN_INTERRUPT, 0xFFFF00FF)
        self._clear_interrupts()
        if not self._enable_oscillator():
            raise RuntimeError("ST25R3916 oscillator failed to start")
        self._write_register32(REG_MASK_MAIN_INTERRUPT, 0)
        self._command(CMD_ADJUST_REGULATORS)
        time.sleep(0.005)

        self._command(CMD_STOP_ALL_ACTIVITIES)
        self._clear_bits(REG_OPERATION_CONTROL, WU)
        self._write_register(REG_MODE_DEFINITION, 0x09)
        self._write_register(REG_BITRATE_DEFINITION, 0)
        self._write_register(REG_ISO14443A_SETTINGS, 0)
        self._clear_bits(REG_AUXILIARY_DEFINITION, DIS_CORR)
        for register, value in (
            (REG_SPACE_B_OVERSHOOT_PROTECTION_CONFIGURATION_1, 0x40),
            (REG_SPACE_B_OVERSHOOT_PROTECTION_CONFIGURATION_2, 0x03),
            (REG_SPACE_B_UNDERSHOOT_PROTECTION_CONFIGURATION_1, 0x40),
            (REG_SPACE_B_UNDERSHOOT_PROTECTION_CONFIGURATION_2, 0x03),
            (REG_SPACE_B_CORRELATOR_CONFIGURATION_1, 0x47),
            (REG_SPACE_B_CORRELATOR_CONFIGURATION_2, 0x00),
        ):
            self._write_space_b(register, value)
        for register, value in (
            (REG_RECEIVER_CONFIGURATION_1, 0x08),
            (REG_RECEIVER_CONFIGURATION_2, 0x2D),
            (REG_RECEIVER_CONFIGURATION_3, 0xD8),
            (REG_RECEIVER_CONFIGURATION_4, 0x22),
        ):
            self._write_register(register, value)
        self._write_register32(REG_MASK_MAIN_INTERRUPT, 0)
        self._command(CMD_RESET_RX_GAIN)
        self._command(CMD_NFC_INITIAL_FIELD_ON)
        time.sleep(0.005)
        self._set_bits(REG_OPERATION_CONTROL, TX_EN | RX_EN)
        return chip_type, revision

    def close(self) -> None:
        self._command(CMD_STOP_ALL_ACTIVITIES)
        self._clear_bits(REG_OPERATION_CONTROL, TX_EN | RX_EN)

    def _request(self, wakeup: bool) -> int | None:
        self._write_timeout(12)
        self._write_register(REG_ISO14443A_SETTINGS, ANTCL)
        self._set_bits(REG_AUXILIARY_DEFINITION, NO_CRC_RX)
        self._clear_interrupts()
        self._command(CMD_CLEAR_FIFO)
        self._command(CMD_TRANSMIT_WUPA if wakeup else CMD_TRANSMIT_REQA)
        length = self._wait_fifo(2, 0.012)
        if length < 2:
            return None
        response = self._read_fifo(length)
        atqa = (response[1] << 8) | response[0]
        return atqa if atqa not in (0, 0xFFFF) else None

    def _anticollision(self, command: int) -> tuple[int, int, int, int, int] | None:
        self._write_timeout(8)
        self._write_register(REG_ISO14443A_SETTINGS, ANTCL)
        self._clear_bits(REG_AUXILIARY_DEFINITION, NO_CRC_RX)
        self._clear_interrupts()
        self._command(CMD_CLEAR_FIFO)
        self._write_fifo(bytes((command, 0x20)))
        self._write_tx_length(2)
        self._command(CMD_TRANSMIT_WITHOUT_CRC)
        length = self._wait_fifo(5, 0.008)
        if length < 5:
            return None
        response = self._read_fifo(length)
        values = tuple(response[:5])
        if values[0] ^ values[1] ^ values[2] ^ values[3] != values[4]:
            return None
        return values

    def _select(self, command: int, values: tuple[int, int, int, int, int]) -> int | None:
        frame = bytes((command, 0x70, *values))
        self._write_timeout(8)
        self._write_register(REG_ISO14443A_SETTINGS, 0)
        self._clear_bits(REG_AUXILIARY_DEFINITION, NO_CRC_RX)
        self._clear_interrupts()
        self._command(CMD_CLEAR_FIFO)
        self._write_fifo(frame)
        self._write_tx_length(len(frame))
        self._command(CMD_TRANSMIT_WITH_CRC)
        length = self._wait_fifo(1, 0.008)
        return self._read_fifo(length)[0] if length else None

    def detect(self) -> NFCCard | None:
        atqa = self._request(True)
        if atqa is None:
            atqa = self._request(False)
        if atqa is None:
            return None
        level1 = self._anticollision(0x93)
        if level1 is None:
            return None
        sak1 = self._select(0x93, level1)
        if sak1 is None:
            return None
        if level1[0] != CASCADE_TAG:
            return NFCCard(bytes(level1[:4]), atqa, sak1)
        if not sak1 & SAK_CASCADE_FLAG:
            return None
        level2 = self._anticollision(0x95)
        if level2 is None or level2[0] == CASCADE_TAG:
            return None
        sak2 = self._select(0x95, level2)
        if sak2 is None:
            return None
        uid = bytes((*level1[1:4], *level2[:4]))
        return NFCCard(uid, atqa, sak2)
