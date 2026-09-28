"""Touch-friendly aggregate dashboard for every Unit in the Grove catalog."""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .bus import I2CBus, SerialPort
from .catalog import PERIPHERALS, Peripheral, find_conflicts
from .drivers import DRIVERS, NMEAParser
from .nfc import ST25R3916


PORT_X_GPIO = 27
BOARD_I2C_ADDRESSES = {0x2C, 0x58, 0x68, 0x6B}
UART_BAUDS = (115200, 9600, 19200, 38400, 31250)


class AudioCues:
    """Serialize short, distinctive UI tones without blocking sensor polling."""

    PATTERNS = {
        "unit": ((620, 0.055), (820, 0.07)),
        "removed": ((700, 0.055), (440, 0.09)),
        "input": ((880, 0.06),),
        "environment": ((520, 0.055), (660, 0.07)),
        "proximity": ((1050, 0.055), (760, 0.075)),
        "motion": ((700, 0.05), (980, 0.06)),
        "uart": ((560, 0.045), (760, 0.045), (960, 0.065)),
        "nfc": ((1250, 0.065), (1650, 0.09)),
    }

    def __init__(self, enabled: bool = True):
        self.enabled = enabled and shutil.which("sox") is not None
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=12)
        self._stop = threading.Event()
        self._last_played: dict[str, float] = {}
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        if self.enabled:
            self._thread.start()

    def stop(self) -> None:
        if not self.enabled:
            return
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=2)

    def play(self, cue: str) -> None:
        if not self.enabled or cue not in self.PATTERNS:
            return
        now = time.monotonic()
        if now - self._last_played.get(cue, 0.0) < 0.25:
            return
        self._last_played[cue] = now
        try:
            self._queue.put_nowait(cue)
        except queue.Full:
            pass

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                cue = self._queue.get(timeout=0.4)
            except queue.Empty:
                continue
            if cue is None:
                return
            for frequency, duration in self.PATTERNS[cue]:
                if self._stop.is_set():
                    return
                try:
                    subprocess.run(
                        ("sox", "-q", "-n", "-t", "alsa",
                         "plughw:CARD=whisplaysound", "synth", str(duration),
                         "sine", str(frequency), "vol", "0.12"),
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, timeout=1, check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    break


@dataclass(slots=True)
class Panel:
    key: str
    title: str
    detail: str
    status: str = "online"
    values: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass(slots=True)
class DashboardState:
    mode: str = "i2c"
    status: str = "starting"
    panels: list[Panel] = field(default_factory=list)
    addresses: list[int] = field(default_factory=list)
    uart_baud: int = 115200
    updated: float = 0.0


def catalog_candidates(address: int) -> tuple[Peripheral, ...]:
    """Return every catalog entry that may use an I2C address."""
    return tuple(item for item in find_conflicts(address) if item.transport == "i2c")


def format_value(value: Any) -> str:
    if value is None:
        return "--"
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


class DashboardBackend:
    """Own the Port.X mode and collect hardware data off the UI thread."""

    def __init__(self, mode: str = "i2c", bus: int = 1,
                 port: str = "/dev/serial0", sound: bool = True):
        self.bus_number = bus
        self.port = port
        self._desired_mode = mode
        self._state = DashboardState(mode=mode)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._force_scan = True
        self._baud_index = 0
        self.audio = AudioCues(sound)
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.audio.start()
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=3)
        self.audio.stop()

    @staticmethod
    def _panel_cue(panel: Panel) -> str:
        if panel.key == "nfc":
            return "unit"
        item = next((item for item in PERIPHERALS if item.slug == panel.key), None)
        category = item.category if item else ""
        if category == "input":
            return "input"
        if category == "environment" or category == "temperature":
            return "environment"
        if category in ("distance", "presence", "gesture", "identification", "biometric"):
            return "proximity"
        if category == "motion":
            return "motion"
        return "unit"

    def set_mode(self, mode: str) -> None:
        if mode not in ("i2c", "uart"):
            raise ValueError("mode must be i2c or uart")
        self._desired_mode = mode
        self._force_scan = True
        self._publish(mode=mode, status=f"switching to {mode.upper()}", panels=[])
        self._wake.set()

    def request_scan(self) -> None:
        self._force_scan = True
        self._wake.set()

    def next_baud(self) -> None:
        self._baud_index = (self._baud_index + 1) % len(UART_BAUDS)
        self._force_scan = True
        self._wake.set()

    def snapshot(self) -> DashboardState:
        with self._lock:
            return DashboardState(
                mode=self._state.mode,
                status=self._state.status,
                panels=[Panel(**asdict(panel)) for panel in self._state.panels],
                addresses=list(self._state.addresses),
                uart_baud=self._state.uart_baud,
                updated=self._state.updated,
            )

    def _publish(self, **changes: Any) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(self._state, key, value)
            self._state.updated = time.monotonic()

    def _select_port(self, mode: str) -> None:
        level = "dl" if mode == "i2c" else "dh"
        subprocess.run(
            ("pinctrl", "set", str(PORT_X_GPIO), "op", level),
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.15)

    def _run(self) -> None:
        active_mode = ""
        while not self._stop.is_set():
            mode = self._desired_mode
            try:
                if mode != active_mode:
                    self._select_port(mode)
                    active_mode = mode
                    self._force_scan = True
                if mode == "i2c":
                    self._run_i2c_session()
                else:
                    self._run_uart_session()
            except Exception as exc:
                self._publish(mode=mode, status=f"hardware error: {exc}", panels=[])
                self._wake.wait(0.8)
                self._wake.clear()

    def _run_i2c_session(self) -> None:
        bus = I2CBus(self.bus_number)
        readers: dict[int, tuple[Peripheral, Any]] = {}
        failures: dict[int, int] = {}
        nfc_reader: ST25R3916 | None = None
        nfc_info: tuple[int, int] | None = None
        last_nfc_uid: bytes | None = None
        last_nfc_seen = 0.0
        announced_keys: set[str] = set()
        active_flags: dict[tuple[str, str], bool] = {}
        addresses: list[int] = []
        next_scan = 0.0
        try:
            while not self._stop.is_set() and self._desired_mode == "i2c":
                now = time.monotonic()
                if self._force_scan or now >= next_scan:
                    self._force_scan = False
                    addresses = [a for a in bus.scan() if a not in BOARD_I2C_ADDRESSES]
                    for address in list(readers):
                        if address not in addresses:
                            readers.pop(address, None)
                            failures.pop(address, None)
                    if nfc_reader is not None and 0x50 not in addresses:
                        try:
                            nfc_reader.close()
                        except OSError:
                            pass
                        nfc_reader = None
                        nfc_info = None
                    next_scan = now + 2.5

                panels: list[Panel] = []
                for address in addresses:
                    candidates = catalog_candidates(address)
                    if address == 0x50 and nfc_reader is None:
                        try:
                            candidate = ST25R3916(bus, address)
                            nfc_info = candidate.begin()
                            nfc_reader = candidate
                        except (OSError, RuntimeError):
                            nfc_reader = None

                    if address == 0x50 and nfc_reader is not None:
                        card = nfc_reader.detect()
                        if card is not None:
                            if card.uid != last_nfc_uid:
                                self.audio.play("nfc")
                            last_nfc_uid = card.uid
                            last_nfc_seen = now
                        elif last_nfc_uid is not None and now - last_nfc_seen >= 0.8:
                            last_nfc_uid = None
                        values: dict[str, Any] = {
                            "chip": f"ST25R3916 type {nfc_info[0]}",
                            "revision": nfc_info[1],
                            "card": "none" if card is None else card.uid_hex,
                        }
                        if card is not None:
                            values.update(atqa=f"0x{card.atqa:04x}", sak=f"0x{card.sak:02x}")
                        panels.append(Panel("nfc", "NFC Unit", "I2C 0x50 · decoded", values=values))
                        continue

                    if address not in readers:
                        decoded = [item for item in candidates if item.driver in DRIVERS]
                        for item in decoded:
                            driver_type = DRIVERS[item.driver]
                            if getattr(driver_type, "address", address) != address:
                                continue
                            try:
                                reader = driver_type(bus, address)
                                value = reader.read()
                                readers[address] = (item, reader)
                                failures[address] = 0
                                if value is not None:
                                    break
                            except (OSError, RuntimeError, ValueError):
                                readers.pop(address, None)

                    if address in readers:
                        item, reader = readers[address]
                        try:
                            value = reader.read()
                            failures[address] = 0
                            if value:
                                for flag in ("pressed", "presence", "detected", "motion",
                                             "occupied", "alarm"):
                                    if flag not in value:
                                        continue
                                    flag_key = (item.slug, flag)
                                    active = bool(value[flag])
                                    if active and not active_flags.get(flag_key, False):
                                        self.audio.play(self._panel_cue(Panel(
                                            item.slug, item.name, "", values=value
                                        )))
                                    active_flags[flag_key] = active
                            panels.append(Panel(
                                item.slug, item.name,
                                f"I2C 0x{address:02X} · decoded",
                                values=value or {"state": "warming up"},
                            ))
                            continue
                        except (OSError, RuntimeError, ValueError) as exc:
                            failures[address] = failures.get(address, 0) + 1
                            if failures[address] >= 3:
                                readers.pop(address, None)
                            panels.append(Panel(
                                item.slug, item.name, f"I2C 0x{address:02X}",
                                status="retrying", error=str(exc),
                            ))
                            continue

                    names = [item.name for item in candidates]
                    title = names[0] if len(names) == 1 else f"I2C Unit at 0x{address:02X}"
                    detail = f"I2C 0x{address:02X} · address detected"
                    values = {"possible models": ", ".join(names) if names else "unknown Unit"}
                    panels.append(Panel(f"i2c-{address:02x}", title, detail, values=values))

                priority = {"joystick2": 0, "scroll": 1}
                panels.sort(key=lambda panel: (priority.get(panel.key, 2), panel.title))
                current_keys = {panel.key for panel in panels}
                for panel in panels:
                    if panel.key not in announced_keys:
                        self.audio.play(self._panel_cue(panel))
                if announced_keys - current_keys:
                    self.audio.play("removed")
                announced_keys = current_keys
                found = len(panels)
                status = f"{found} Unit{'s' if found != 1 else ''} · scanning I2C-{self.bus_number}"
                self._publish(mode="i2c", status=status, panels=panels,
                              addresses=addresses)
                self._wake.wait(0.16)
                self._wake.clear()
        finally:
            if nfc_reader is not None:
                try:
                    nfc_reader.close()
                except OSError:
                    pass
            bus.close()

    def _run_uart_session(self) -> None:
        parser = NMEAParser()
        last_data = 0.0
        opened_at = time.monotonic()
        baud = UART_BAUDS[self._baud_index]
        serial = SerialPort(self.port, baud, timeout=0.12)
        raw_tail = bytearray()
        nmea_seen = False
        try:
            while not self._stop.is_set() and self._desired_mode == "uart":
                requested_baud = UART_BAUDS[self._baud_index]
                if self._force_scan or requested_baud != baud:
                    self._force_scan = False
                    return
                data = serial.read(256)
                now = time.monotonic()
                if data:
                    if last_data == 0.0:
                        self.audio.play("uart")
                    last_data = now
                    raw_tail.extend(data)
                    del raw_tail[:-512]
                    text = data.decode("ascii", errors="replace")
                    for line in text.splitlines():
                        if line.startswith("$") and line[3:6] in ("RMC", "GGA"):
                            parser.feed(line)
                            nmea_seen = True

                panels: list[Panel] = []
                if nmea_seen and now - last_data < 5:
                    panels.append(Panel(
                        "gps", "GPS / GNSS Unit", f"UART {baud} baud · NMEA decoded",
                        values=asdict(parser.fix),
                    ))
                elif raw_tail and now - last_data < 5:
                    candidates = [item.name for item in PERIPHERALS
                                  if item.transport == "uart" and item.baudrate == baud]
                    preview = bytes(raw_tail[-96:]).decode("ascii", errors="replace")
                    panels.append(Panel(
                        "uart-monitor", "UART Unit", f"{self.port} · {baud} baud",
                        values={
                            "possible models": ", ".join(candidates) or "unknown UART Unit",
                            "latest data": preview.replace("\r", " ").replace("\n", " "),
                            "bytes buffered": len(raw_tail),
                        },
                    ))

                status = (f"UART data at {baud} baud" if panels else
                          f"waiting for UART data · {baud} baud")
                self._publish(mode="uart", status=status, panels=panels,
                              addresses=[], uart_baud=baud)

                # With no traffic, automatically sample every catalog baud rate.
                if not data and not panels and now - opened_at > 2.2:
                    self._baud_index = (self._baud_index + 1) % len(UART_BAUDS)
                    return
        finally:
            serial.close()


class DashboardApp:
    BG = (10, 14, 20)
    PANEL = (24, 31, 42)
    PANEL_ALT = (31, 40, 53)
    LINE = (57, 72, 91)
    TEXT = (239, 243, 248)
    MUTED = (151, 164, 181)
    CYAN = (73, 211, 229)
    GREEN = (66, 211, 146)
    YELLOW = (245, 190, 74)
    RED = (255, 103, 112)

    def __init__(self, backend: DashboardBackend, windowed: bool = False,
                 width: int = 720, height: int = 720):
        os.environ.setdefault("SDL_ENABLE_SCREEN_KEYBOARD", "0")
        os.environ.setdefault("SDL_IME_SHOW_UI", "0")
        import pygame
        self.pg = pygame
        self.backend = backend
        # Keep the ALSA device free for AudioCues; this UI only needs display/font.
        pygame.display.init()
        pygame.font.init()
        pygame.key.stop_text_input()
        pygame.display.set_caption("Whisplay Grove Sensors")
        flags = 0 if windowed else pygame.FULLSCREEN
        size = (width, height) if windowed else (0, 0)
        self.screen = pygame.display.set_mode(size, flags)
        self.clock = pygame.time.Clock()
        self.title_font = pygame.font.SysFont("DejaVu Sans", 25, bold=True)
        self.body_font = pygame.font.SysFont("DejaVu Sans", 16)
        self.small_font = pygame.font.SysFont("DejaVu Sans", 13)
        self.value_font = pygame.font.SysFont("DejaVu Sans", 18, bold=True)
        self.running = True
        self.scroll = 0
        self.drag_y: int | None = None
        self.buttons: list[tuple[str, Any]] = []
        self.joystick_display = [0.0, 0.0]
        self.scroll_display_angle: float | None = None
        self.button_levels: dict[str, float] = {}

    def _button(self, label: str, rect: Any, active: bool = False) -> None:
        pg = self.pg
        fill = self.CYAN if active else self.PANEL_ALT
        text_color = self.BG if active else self.TEXT
        pg.draw.rect(self.screen, fill, rect, border_radius=9)
        pg.draw.rect(self.screen, self.LINE, rect, 1, border_radius=9)
        surface = self.small_font.render(label, True, text_color)
        self.screen.blit(surface, surface.get_rect(center=rect.center))

    def _text(self, value: str, x: int, y: int, font: Any,
              color: tuple[int, int, int], max_width: int = 0) -> None:
        text = value
        if max_width:
            while text and font.size(text + "…")[0] > max_width:
                text = text[:-1]
            if text != value:
                text += "…"
        self.screen.blit(font.render(text, True, color), (x, y))

    @staticmethod
    def _mix_color(a: tuple[int, int, int], b: tuple[int, int, int],
                   amount: float) -> tuple[int, int, int]:
        amount = max(0.0, min(1.0, amount))
        return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))

    def _button_indicator(self, key: str, rect: Any, pressed: bool) -> None:
        pg = self.pg
        target = 1.0 if pressed else 0.0
        level = self.button_levels.get(key, target)
        level += (target - level) * 0.24
        self.button_levels[key] = level
        color = self._mix_color(self.PANEL_ALT, self.GREEN, level)
        if level > 0.04:
            glow = rect.inflate(round(7 * level), round(7 * level))
            glow_color = self._mix_color(self.LINE, self.GREEN, level * 0.75)
            pg.draw.rect(self.screen, glow_color, glow, 2, border_radius=12)
        pg.draw.rect(self.screen, color, rect, border_radius=10)
        pg.draw.rect(self.screen, self.LINE, rect, 1, border_radius=10)
        label = "PRESSED" if pressed else "RELEASED"
        text_color = self._mix_color(self.MUTED, self.BG, level)
        surface = self.small_font.render(label, True, text_color)
        self.screen.blit(surface, surface.get_rect(center=rect.center))

    def _draw_joystick_panel(self, panel: Panel, rect: Any) -> None:
        pg = self.pg
        values = panel.values
        x_value = int(values.get("x", 0) or 0)
        y_value = int(values.get("y", 0) or 0)
        pressed = bool(values.get("pressed", False))
        radius = 42 if rect.width >= 390 else 36
        center = (rect.x + radius + 24, rect.y + 125)

        pg.draw.circle(self.screen, (13, 19, 27), center, radius + 7)
        pg.draw.circle(self.screen, self.LINE, center, radius + 7, 2)
        pg.draw.circle(self.screen, self.PANEL_ALT, center, radius)
        pg.draw.line(self.screen, self.LINE,
                     (center[0] - radius + 7, center[1]),
                     (center[0] + radius - 7, center[1]), 1)
        pg.draw.line(self.screen, self.LINE,
                     (center[0], center[1] - radius + 7),
                     (center[0], center[1] + radius - 7), 1)
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            tip = (center[0] + dx * (radius + 3), center[1] + dy * (radius + 3))
            pg.draw.circle(self.screen, self.MUTED, tip, 2)

        target_x = max(-4096, min(4096, x_value)) / 4096
        target_y = max(-4096, min(4096, y_value)) / 4096
        previous_x, previous_y = self.joystick_display
        self.joystick_display[0] += (target_x - previous_x) * 0.22
        self.joystick_display[1] += (target_y - previous_y) * 0.22
        motion = math.hypot(target_x - previous_x, target_y - previous_y)
        travel = radius - 13
        knob = (
            center[0] + round(self.joystick_display[0] * travel),
            center[1] + round(self.joystick_display[1] * travel),
        )
        if motion > 0.01:
            halo_radius = 15 + min(9, round(motion * 24))
            halo_color = self._mix_color(self.LINE, self.CYAN, min(1.0, motion * 2.5))
            pg.draw.circle(self.screen, halo_color, knob, halo_radius, 2)
        pg.draw.line(self.screen, self.CYAN, center, knob, 4)
        pg.draw.circle(self.screen, self.CYAN, knob, 13)
        pg.draw.circle(self.screen, (205, 250, 255), knob, 5)

        info_x = center[0] + radius + 25
        info_w = rect.right - info_x - 14
        self._text("POSITION", info_x, rect.y + 70, self.small_font, self.MUTED)
        self._text(f"X {x_value:+5d}", info_x, rect.y + 91,
                   self.value_font, self.TEXT, info_w)
        self._text(f"Y {y_value:+5d}", info_x, rect.y + 116,
                   self.value_font, self.TEXT, info_w)
        indicator = pg.Rect(info_x, rect.y + 148, max(84, info_w), 25)
        self._button_indicator("joystick2", indicator, pressed)

    def _draw_scroll_panel(self, panel: Panel, rect: Any) -> None:
        pg = self.pg
        values = panel.values
        value = int(values.get("value", 0) or 0)
        increment = int(values.get("increment", 0) or 0)
        pressed = bool(values.get("pressed", False))
        radius = 43 if rect.width >= 390 else 37
        center = (rect.x + radius + 24, rect.y + 125)

        pg.draw.circle(self.screen, (13, 19, 27), center, radius + 7)
        pg.draw.circle(self.screen, self.LINE, center, radius + 7, 2)
        pg.draw.circle(self.screen, self.PANEL_ALT, center, radius)
        for tick in range(12):
            angle = math.radians(tick * 30 - 90)
            inner = radius - (9 if tick % 3 == 0 else 6)
            start = (center[0] + math.cos(angle) * inner,
                     center[1] + math.sin(angle) * inner)
            end = (center[0] + math.cos(angle) * (radius - 2),
                   center[1] + math.sin(angle) * (radius - 2))
            pg.draw.line(self.screen, self.MUTED, start, end, 2 if tick % 3 == 0 else 1)
        target_angle = float(value * 15)
        if self.scroll_display_angle is None:
            self.scroll_display_angle = target_angle
        angle_error = target_angle - self.scroll_display_angle
        self.scroll_display_angle += angle_error * 0.20
        angle = math.radians(self.scroll_display_angle - 90)
        if abs(angle_error) > 0.4:
            arc_color = self.GREEN if angle_error > 0 else self.YELLOW
            sweep = min(110.0, max(18.0, abs(angle_error)))
            direction = 1.0 if angle_error > 0 else -1.0
            sweep_radians = math.radians(sweep)
            trail_radius = radius + 4
            segments = 10
            points = []
            for segment in range(segments + 1):
                progress = segment / segments
                trail_angle = angle - direction * sweep_radians * (1.0 - progress)
                points.append((
                    center[0] + math.cos(trail_angle) * trail_radius,
                    center[1] + math.sin(trail_angle) * trail_radius,
                ))
            for segment in range(segments):
                brightness = (segment + 1) / segments
                color = self._mix_color(self.LINE, arc_color, brightness)
                pg.draw.line(self.screen, color, points[segment],
                             points[segment + 1], 2 if segment < 6 else 3)
        pointer = (center[0] + math.cos(angle) * (radius - 13),
                   center[1] + math.sin(angle) * (radius - 13))
        pg.draw.line(self.screen, self.CYAN, center, pointer, 4)
        pg.draw.circle(self.screen, self.CYAN, center, 7)

        info_x = center[0] + radius + 25
        info_w = rect.right - info_x - 14
        self._text("ROTATION", info_x, rect.y + 70, self.small_font, self.MUTED)
        direction = "CW" if increment > 0 else "CCW" if increment < 0 else "IDLE"
        self._text(str(value), info_x, rect.y + 88,
                   self.title_font, self.TEXT, info_w)
        delta_color = self.GREEN if increment else self.MUTED
        self._text(f"{direction}  {increment:+d}", info_x, rect.y + 120,
                   self.body_font, delta_color, info_w)
        indicator = pg.Rect(info_x, rect.y + 148, max(84, info_w), 25)
        self._button_indicator("scroll", indicator, pressed)

    def _draw(self, state: DashboardState) -> None:
        pg = self.pg
        self.screen.fill(self.BG)
        width, height = self.screen.get_size()
        self._text("Grove Sensor Hub", 20, 16, self.title_font, self.TEXT)
        self._text(state.status, 21, 49, self.small_font, self.MUTED, width - 42)

        y = 75
        compact = width < 600
        gap = 6 if compact else 8
        tab_w = 72 if compact else 92
        i2c = pg.Rect(20, y, tab_w, 38)
        uart = pg.Rect(20 + tab_w + gap, y, tab_w, 38)
        scan = pg.Rect(width - (194 if compact else 196), y, 80 if compact else 86, 38)
        quit_rect = pg.Rect(width - (106 if compact else 102), y, 86 if compact else 82, 38)
        self._button("I2C", i2c, state.mode == "i2c")
        self._button("UART", uart, state.mode == "uart")
        self._button("RESCAN", scan)
        self._button("QUIT", quit_rect)
        self.buttons = [("i2c", i2c), ("uart", uart), ("scan", scan), ("quit", quit_rect)]
        if state.mode == "uart":
            baud_x = uart.right + gap
            baud_w = scan.x - gap - baud_x
            baud = pg.Rect(baud_x, y, baud_w, 38)
            self._button(str(state.uart_baud), baud)
            self.buttons.append(("baud", baud))

        top = 126
        bottom = height - 28
        pg.draw.line(self.screen, self.LINE, (20, top - 5), (width - 20, top - 5))
        columns = 2 if width >= 650 else 1
        margin = 20
        card_gap = 12
        card_w = (width - margin * 2 - card_gap * (columns - 1)) // columns
        card_h = 190
        rows = (len(state.panels) + columns - 1) // columns
        content_h = max(0, rows * (card_h + card_gap) - card_gap)
        max_scroll = max(0, content_h - (bottom - top))
        self.scroll = max(0, min(self.scroll, max_scroll))

        if not state.panels:
            title = "No I2C Grove Units detected" if state.mode == "i2c" else "Waiting for UART data"
            hint = ("Connect a Unit, then tap RESCAN" if state.mode == "i2c" else
                    "Baud rates cycle automatically; tap BAUD to advance")
            surface = self.title_font.render(title, True, self.MUTED)
            self.screen.blit(surface, surface.get_rect(center=(width // 2, height // 2 - 22)))
            hint_surface = self.small_font.render(hint, True, self.MUTED)
            self.screen.blit(hint_surface, hint_surface.get_rect(center=(width // 2, height // 2 + 18)))

        old_clip = self.screen.get_clip()
        self.screen.set_clip(pg.Rect(0, top, width, bottom - top))
        for index, panel in enumerate(state.panels):
            row, col = divmod(index, columns)
            x = margin + col * (card_w + card_gap)
            card_y = top + row * (card_h + card_gap) - self.scroll
            rect = pg.Rect(x, card_y, card_w, card_h)
            if rect.bottom < top or rect.top > bottom:
                continue
            pg.draw.rect(self.screen, self.PANEL, rect, border_radius=12)
            pg.draw.rect(self.screen, self.LINE, rect, 1, border_radius=12)
            color = self.GREEN if panel.status == "online" else self.YELLOW
            pg.draw.circle(self.screen, color, (rect.x + 16, rect.y + 18), 5)
            self._text(panel.title, rect.x + 28, rect.y + 8,
                       self.body_font, self.TEXT, card_w - 42)
            self._text(panel.detail, rect.x + 14, rect.y + 36,
                       self.small_font, self.MUTED, card_w - 28)
            if panel.key == "joystick2" and not panel.error:
                self._draw_joystick_panel(panel, rect)
                continue
            if panel.key == "scroll" and not panel.error:
                self._draw_scroll_panel(panel, rect)
                continue
            value_y = rect.y + 65
            items = list(panel.values.items())[:4]
            if panel.error:
                items = [("error", panel.error)]
            for item_index, (key, value) in enumerate(items):
                cell_w = (card_w - 28) // 2
                cell_x = rect.x + 14 + (item_index % 2) * cell_w
                cell_y = value_y + (item_index // 2) * 45
                self._text(str(key).replace("_", " ").upper(), cell_x, cell_y,
                           self.small_font, self.MUTED, cell_w - 8)
                self._text(format_value(value), cell_x, cell_y + 17,
                           self.value_font, self.TEXT, cell_w - 8)
        self.screen.set_clip(old_clip)

        footer = f"Catalog: {len(PERIPHERALS)} Units"
        if state.mode == "i2c" and state.addresses:
            footer += "  ·  " + " ".join(f"0x{x:02X}" for x in state.addresses)
        self._text(footer, 20, height - 21, self.small_font, self.MUTED, width - 40)

    def run(self) -> int:
        pg = self.pg
        self.backend.start()
        try:
            while self.running:
                for event in pg.event.get():
                    if event.type == pg.QUIT:
                        self.running = False
                    elif event.type == pg.KEYDOWN:
                        if event.key in (pg.K_ESCAPE, pg.K_q):
                            self.running = False
                        elif event.key == pg.K_i:
                            self.backend.set_mode("i2c")
                        elif event.key == pg.K_u:
                            self.backend.set_mode("uart")
                        elif event.key == pg.K_r:
                            self.backend.request_scan()
                    elif event.type == pg.MOUSEWHEEL:
                        self.scroll -= event.y * 70
                    elif event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                        self.drag_y = event.pos[1]
                        for action, rect in self.buttons:
                            if rect.collidepoint(event.pos):
                                if action in ("i2c", "uart"):
                                    self.scroll = 0
                                    self.backend.set_mode(action)
                                elif action == "scan":
                                    self.backend.request_scan()
                                elif action == "baud":
                                    self.backend.next_baud()
                                elif action == "quit":
                                    self.running = False
                                self.drag_y = None
                                break
                    elif event.type == pg.MOUSEMOTION and self.drag_y is not None:
                        self.scroll += self.drag_y - event.pos[1]
                        self.drag_y = event.pos[1]
                    elif event.type == pg.MOUSEBUTTONUP and event.button == 1:
                        self.drag_y = None

                self._draw(self.backend.snapshot())
                pg.display.flip()
                self.clock.tick(30)
        finally:
            self.backend.stop()
            pg.quit()
        return 0

    @property
    def backend(self) -> DashboardBackend:
        return self._backend

    @backend.setter
    def backend(self, value: DashboardBackend) -> None:
        self._backend = value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="whisplay-grove-dashboard")
    parser.add_argument("--mode", choices=("i2c", "uart"), default="i2c")
    parser.add_argument("--bus", type=int, default=1)
    parser.add_argument("--port", default="/dev/serial0")
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--mute", action="store_true")
    args = parser.parse_args(argv)
    backend = DashboardBackend(args.mode, args.bus, args.port, sound=not args.mute)
    return DashboardApp(backend, args.windowed, args.width, args.height).run()


if __name__ == "__main__":
    raise SystemExit(main())
