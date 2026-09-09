"""Catalog of M5Stack Grove Units that use I2C or UART.

The inventory follows the M5Stack UIFlow2 unit package.  An empty address or
baud rate means that it is revision/configuration dependent; the CLI requires
the user to provide it rather than guessing.
"""

from dataclasses import dataclass
from typing import Literal

Transport = Literal["i2c", "uart"]
Support = Literal["decoded", "monitor", "probe"]


@dataclass(frozen=True, slots=True)
class Peripheral:
    slug: str
    name: str
    transport: Transport
    category: str
    addresses: tuple[int, ...] = ()
    baudrate: int | None = None
    support: Support = "probe"
    driver: str | None = None
    notes: str = ""


def _i(slug: str, name: str, category: str, *addresses: int,
       support: Support = "probe", driver: str | None = None,
       notes: str = "") -> Peripheral:
    return Peripheral(slug, name, "i2c", category, tuple(addresses), None,
                      support, driver, notes)


def _u(slug: str, name: str, category: str, baudrate: int | None = None,
       support: Support = "monitor", driver: str | None = None,
       notes: str = "") -> Peripheral:
    return Peripheral(slug, name, "uart", category, (), baudrate, support,
                      driver, notes)


PERIPHERALS: tuple[Peripheral, ...] = (
    # Environmental and ranging sensors.
    _i("env", "ENV Unit", "environment", notes="Product revision determines sensors"),
    _i("env-ii", "ENV II Unit", "environment", 0x44, 0x76),
    _i("env-iii", "ENV III Unit", "environment", 0x44, 0x70,
       support="decoded", driver="sht3x", notes="Decoded demo covers SHT30 temperature/humidity"),
    _i("env-iv", "ENV IV Unit", "environment", 0x44, 0x76,
       support="decoded", driver="sht4x", notes="Decoded demo covers SHT40 temperature/humidity"),
    _i("env-pro", "ENV Pro Unit", "environment", 0x77),
    _i("bps", "BPS Unit", "environment", 0x76),
    _i("co2", "CO2 Unit", "environment", 0x62, support="decoded", driver="scd4x"),
    _i("co2l", "CO2L Unit", "environment", 0x62),
    _i("tvoc", "TVOC/eCO2 Unit", "environment", 0x58,
       support="decoded", driver="sgp30", notes="Conflicts with PiSugar when RTC is 0x58"),
    _i("ncir", "NCIR Unit", "temperature", 0x5A,
       support="decoded", driver="mlx90614"),
    _i("ncir2", "NCIR2 Unit", "temperature", 0x5A),
    _i("thermal", "Thermal Unit", "thermal-camera", 0x33),
    _i("thermal2", "Thermal2 Unit", "thermal-camera", 0x32),
    _i("tmos", "TMOS PIR Unit", "presence", 0x5A),
    _i("tof", "ToF/ToF90 Unit", "distance", 0x29),
    _i("tof4m", "ToF4M Unit", "distance", 0x29),
    _i("ultrasonic-i2c", "Ultrasonic I2C Unit", "distance", 0x57,
       support="decoded", driver="ultrasonic"),
    _i("dlight", "DLight Unit", "light", 0x23,
       support="decoded", driver="bh1750"),
    _i("color", "Color Unit", "light", 0x29),
    _i("gesture", "Gesture Unit", "gesture", 0x73),
    _i("heart", "Heart Unit", "biometric", 0x57),
    _i("imu", "IMU Unit", "motion", 0x68),
    _i("imu-pro", "IMU Pro Unit", "motion", 0x68, 0x10),
    _i("accel", "Accel Unit", "motion", 0x53),

    # Input, measurement and identification Units.
    _i("angle8", "Angle8 Unit", "input", 0x43),
    _i("byte-button", "Byte Button/Switch Unit", "input", 0x47, 0x46),
    _i("cardkb", "CardKB Unit", "input", 0x5F),
    _i("encoder8", "Encoder8 Unit", "input", 0x41),
    _i("ext-encoder", "ExtEncoder Unit", "input", 0x59),
    _i("joystick2", "Joystick2 Unit", "input", 0x63),
    _i("id", "ID Unit", "identification"),
    _i("nfc", "NFC Unit (ST25R3916 family)", "identification", 0x28),
    _i("rfid", "RFID Unit", "identification", 0x28),
    _i("qrcode-i2c", "QRCode Unit (I2C mode)", "identification", 0x21),
    _i("ac-measure", "AC Measure Unit", "measurement", 0x42),
    _i("adc-v11", "ADC Unit v1.1", "measurement", 0x48),
    _i("ain-4-20ma", "4-20mA Input Unit", "measurement", 0x55),
    _i("ameter", "Ammeter Unit", "measurement", 0x48, 0x51),
    _i("ina226", "INA226 Unit", "measurement", 0x40),
    _i("kmeter", "K-Meter Unit", "measurement", 0x66),
    _i("kmeter-iso", "K-Meter ISO Unit", "measurement", 0x66),
    _i("miniscale", "Mini Scale Unit", "measurement", 0x26),
    _i("scales", "Scales Unit", "measurement", 0x26),
    _i("vmeter", "Voltmeter Unit", "measurement", 0x49, 0x53),
    _i("weight-i2c", "Weight I2C Unit", "measurement", 0x26),
    _i("mq", "MQ Gas Unit", "gas", 0x11),
    _i("adc", "ADC Unit (legacy ADS1100)", "measurement", 0x48),
    _i("dac", "DAC Unit (legacy MCP4725)", "output", 0x60),
    _i("extio", "EXT.IO Unit (legacy)", "expander", 0x27),
    _i("makey", "Makey Unit (legacy)", "input"),
    _i("trace", "TRACE Unit (legacy)", "measurement"),

    # I2C-controlled displays, actuators and expansion peripherals.
    _i("acssr", "ACSSR/DCSSR Unit", "actuator", 0x50),
    _i("bldc-driver", "BLDC Driver Unit", "actuator", 0x65),
    _i("dac2", "DAC2 Unit", "output", 0x59),
    _i("dds", "DDS Unit", "output", 0x31),
    _i("digi-clock", "Digi Clock Unit", "display", 0x30),
    _i("extio2", "EXT.IO2 Unit", "expander", 0x45),
    _i("glass", "Glass Unit", "display", 0x3D),
    _i("glass2", "Glass2 Unit", "display", 0x3C),
    _i("hbridge", "H-Bridge Unit", "actuator", 0x20),
    _i("lcd", "LCD Unit", "display", 0x3E),
    _i("minioled", "Mini OLED Unit", "display", 0x3C),
    _i("oled", "OLED Unit", "display", 0x3C),
    _i("pahub", "PaHUB I2C Multiplexer", "expander", 0x70),
    _i("pbhub", "PbHUB Unit", "expander", 0x61),
    _i("relay4", "4-Relay Unit", "actuator", 0x26),
    _i("rtc8563", "RTC8563 Unit", "time", 0x51),
    _i("servos8", "8-Servo Unit", "actuator", 0x25),
    _i("step16", "Step16 Unit", "actuator", 0x48),
    _i("timer-pwr", "TimerPWR Unit", "power", 0x56),

    # UART sensors, positioning, camera, radio and protocol peripherals.
    _u("unitv", "UnitV AI Camera", "camera", 115200),
    _u("unitv2", "UnitV2 AI Camera", "camera", 115200),
    _u("m5camera", "M5Camera Unit", "camera", 115200),
    _u("esp32cam", "ESP32CAM Unit", "camera", 115200),
    _u("timercam", "TimerCam Unit", "camera", 115200),
    _u("butterfly", "Butterfly Unit", "camera", 115200),
    _u("gps", "GPS Unit", "positioning", 9600,
       support="decoded", driver="nmea"),
    _u("gps-v11", "GPS Unit v1.1", "positioning", 115200,
       support="decoded", driver="nmea", notes="Built-in ceramic antenna"),
    _u("catm-gnss", "CatM GNSS Unit", "positioning", support="decoded", driver="nmea"),
    _u("uwb", "UWB Unit", "positioning"),
    _u("asr", "ASR Unit", "voice", 115200),
    _u("audio-player", "Audio Player Unit", "audio", 9600),
    _u("finger", "Finger Unit", "biometric", 19200),
    _u("fingerprint2", "Fingerprint2 Unit", "biometric", 115200),
    _u("qrcode-uart", "QRCode Unit (UART mode)", "identification", 115200),
    _u("uhf-rfid", "UHF RFID Unit", "identification", 115200),
    _u("cat1", "Cat.1 Unit", "cellular", 115200),
    _u("catm", "Cat-M Unit", "cellular", 115200),
    _u("nbiot", "NB-IoT Unit", "cellular", 115200),
    _u("nbiot2", "NB-IoT2 Unit", "cellular", 115200),
    _u("mqtt", "MQTT Unit", "network", 9600),
    _u("gateway-h2", "Gateway H2 Unit", "network"),
    _u("zigbee", "Zigbee Unit", "radio", 38400),
    _u("lora-e220-433", "LoRa E220 433 Unit", "radio", 9600),
    _u("lora-e220-jp", "LoRa E220 JP Unit", "radio", 9600),
    _u("lorawan", "LoRaWAN Unit", "radio", 115200),
    _u("lorawan-rui3", "LoRaWAN RUI3 Unit", "radio"),
    _u("laser-rx", "Laser RX Unit", "optical-link"),
    _u("laser-tx", "Laser TX Unit", "optical-link"),
    _u("rs485", "RS485 Unit", "bus-adapter", 9600),
    _u("rs485-iso", "ISO485 Unit", "bus-adapter"),
    _u("roller485", "Roller485 Unit", "actuator"),
    _u("synth", "Synth Unit", "audio", 31250),
    _u("cardkb-uart", "CardKB Unit (UART mode)", "input", 115200),
)

_BY_SLUG = {item.slug: item for item in PERIPHERALS}


def get_peripheral(slug: str) -> Peripheral:
    try:
        return _BY_SLUG[slug]
    except KeyError as exc:
        raise KeyError(f"unknown peripheral: {slug}") from exc


def find_conflicts(address: int) -> tuple[Peripheral, ...]:
    return tuple(p for p in PERIPHERALS if address in p.addresses)

