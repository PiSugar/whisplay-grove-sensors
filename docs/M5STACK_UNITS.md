# M5Stack I²C/UART Grove Unit inventory

This inventory is based on the M5Stack UIFlow2 `m5stack/libs/unit` package
reviewed on 2026-09-09. It intentionally excludes GPIO, ADC-only, CAN, I²S,
DMX and direct RS-485 field devices that cannot communicate through Port.X in
its I²C or TTL-UART modes.

The Python catalog is authoritative and can be printed with:

```bash
whisplay-grove list
```

## I²C Units

Environmental and sensing:

- ENV, ENV II, ENV III, ENV IV, ENV Pro and BPS
- CO2, CO2L, TVOC/eCO2, MQ Gas
- NCIR, NCIR2, Thermal, Thermal2 and TMOS
- ToF/ToF90, ToF4M and Ultrasonic I2C
- DLight, Color, Gesture, Heart, IMU, IMU Pro and Accel

Input, measurement and identification:

- Angle8, Byte Button/Byte Switch, CardKB, Encoder8, ExtEncoder and Joystick2
- ID, NFC, RFID and QRCode I²C
- AC Measure, ADC, ADC v1.1, DAC, 4-20mA Input, Ammeter, INA226, K-Meter,
  K-Meter ISO, Mini Scale, Scales, Voltmeter and Weight I2C

Displays, actuators and expansion:

- ACSSR/DCSSR, BLDC Driver, H-Bridge, 4-Relay, 8-Servo and Step16
- DAC2, DDS, Digi Clock, Glass, Glass2, LCD, Mini OLED and OLED
- EXT.IO, EXT.IO2, Makey, TRACE, PaHUB, PbHUB, RTC8563 and TimerPWR

## UART Units

- UnitV, UnitV2, M5Camera, ESP32CAM, TimerCam and Butterfly
- GPS, GPS v1.1, CatM GNSS and UWB
- ASR, Audio Player and Synth
- Finger, Fingerprint2, QRCode UART, UHF RFID and CardKB UART
- Cat.1, Cat-M, NB-IoT, NB-IoT2 and MQTT
- Gateway H2, Zigbee, LoRa E220 433/JP, LoRaWAN and LoRaWAN RUI3
- Laser RX/TX, RS485, ISO485 and Roller485

Some products support two transports and therefore have two catalog entries.
Configurable addresses and baud rates must be checked against the exact SKU.

## Meaning of support levels

| Level | What works on Linux |
|---|---|
| `decoded` | Presence check plus structured sensor values |
| `monitor` | Read-only UART line/byte monitoring |
| `probe` | Safe I²C presence check; specialized register API is pending |

`probe` is deliberate: arbitrary reads and especially writes are unsafe for
actuators, radios and bootloader-backed Units. Each can still be detected and
has a runnable demo through the common CLI.

## Reference implementation

Protocol names, default addresses and serial rates were cross-checked against
the MIT-licensed M5Stack UIFlow MicroPython implementation:

- <https://github.com/m5stack/uiflow-micropython/tree/587e134c61b31431335351e04ebfc05f69064bb7/m5stack/libs/unit>
- <https://github.com/m5stack/uiflow-micropython/tree/587e134c61b31431335351e04ebfc05f69064bb7/m5stack/libs/driver>

M5Stack names and trademarks belong to M5Stack Technology Co., Ltd.

