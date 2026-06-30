"""Minimal local TCP protocol client for SP108E/LED Shop controllers."""

from __future__ import annotations

import socket
from dataclasses import dataclass

START = 0x38
END = 0x83


class Sp108eError(Exception):
    """Base exception for SP108E errors."""


class Sp108eConnectionError(Sp108eError):
    """Raised when the controller cannot be reached."""


class Sp108eProtocolError(Sp108eError):
    """Raised when the controller returns an invalid frame."""


@dataclass(frozen=True)
class Sp108eSettings:
    """Decoded SP108E state frame."""

    power_raw: int
    effect_raw: int
    speed_raw: int
    brightness_raw: int
    ic_type_raw: int
    led_count: int
    segment_count: int
    color_rgb: tuple[int, int, int]
    color_order_raw: int
    recorded_patterns_raw: int
    white_brightness_raw: int

    @property
    def is_on(self) -> bool:
        return self.power_raw != 0

    @property
    def color_hex(self) -> str:
        return "%02x%02x%02x" % self.color_rgb


def clamp_byte(value: int) -> int:
    if value < 0 or value > 255:
        raise ValueError("value must be in range 0..255")
    return value


def build_frame(instruction: int, payload: bytes | None = None) -> bytes:
    instruction = clamp_byte(instruction)
    value = payload or b"\x00\x00\x00"
    if len(value) != 3:
        raise ValueError("SP108E payload must be exactly 3 bytes")
    return bytes([START]) + value + bytes([instruction, END])


def get_name_frame() -> bytes:
    return build_frame(0x77)


def get_settings_frame() -> bytes:
    return build_frame(0x10)


def toggle_power_frame() -> bytes:
    return build_frame(0xAA)


def brightness_frame(value: int) -> bytes:
    return build_frame(0x2A, bytes([clamp_byte(value), 0x00, 0x00]))


def speed_frame(value: int) -> bytes:
    return build_frame(0x03, bytes([clamp_byte(value), 0x00, 0x00]))


def color_frame(red: int, green: int, blue: int) -> bytes:
    return build_frame(
        0x22,
        bytes([clamp_byte(red), clamp_byte(green), clamp_byte(blue)]),
    )


def mode_frame(value: int) -> bytes:
    return build_frame(0x2C, bytes([clamp_byte(value), 0x00, 0x00]))


def parse_name_response(data: bytes) -> str:
    return data.strip(b"\x00").decode("ascii")


def parse_settings_response(data: bytes) -> Sp108eSettings:
    if len(data) != 17:
        raise Sp108eProtocolError("SP108E settings response must be exactly 17 bytes")
    if data[0] != START or data[-1] != END:
        raise Sp108eProtocolError("SP108E settings response has invalid frame markers")

    return Sp108eSettings(
        power_raw=data[1],
        effect_raw=data[2],
        speed_raw=data[3],
        brightness_raw=data[4],
        ic_type_raw=data[5],
        led_count=int.from_bytes(data[6:8], "big"),
        segment_count=int.from_bytes(data[8:10], "big"),
        color_rgb=(data[10], data[11], data[12]),
        color_order_raw=data[13],
        recorded_patterns_raw=data[14],
        white_brightness_raw=data[15],
    )


class Sp108eClient:
    """Blocking SP108E TCP client.

    Home Assistant calls this through the executor so the event loop is not
    blocked by socket operations.
    """

    def __init__(self, host: str, port: int = 8189, timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def _exchange(self, tx: bytes, read_response: bool = True) -> bytes:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.settimeout(self.timeout)
                sock.sendall(tx)
                if not read_response:
                    return b""
                try:
                    return sock.recv(4096)
                except TimeoutError:
                    return b""
        except OSError as err:
            raise Sp108eConnectionError(str(err)) from err

    def get_name(self) -> str:
        data = self._exchange(get_name_frame())
        if not data:
            raise Sp108eProtocolError("empty name response")
        return parse_name_response(data)

    def get_settings(self) -> Sp108eSettings:
        return parse_settings_response(self._exchange(get_settings_frame()))

    def toggle_power(self) -> Sp108eSettings | None:
        data = self._exchange(toggle_power_frame())
        if not data:
            return None
        return parse_settings_response(data)

    def set_brightness(self, value: int) -> None:
        self._exchange(brightness_frame(value), read_response=False)

    def set_speed(self, value: int) -> None:
        self._exchange(speed_frame(value), read_response=False)

    def set_mode(self, value: int) -> None:
        self._exchange(mode_frame(value), read_response=False)

    def set_color(self, red: int, green: int, blue: int) -> None:
        self._exchange(color_frame(red, green, blue), read_response=False)
