from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import re
import threading
from typing import Any


@dataclass
class ToolState:
    id: str | None = None
    temperature_raw: str | None = None
    temperature_c: float | None = None
    power_raw: str | None = None
    power_w: float | None = None
    power_updated_at: str | None = None  # nur beim Power-Topic gesetzt
    standby_raw: str | None = None
    standby_updated_at: str | None = None
    counter_time: str | None = None
    counter_updated_at: str | None = None  # nur beim Counter/Time-Topic gesetzt – Heartbeat
    operating_hours_total: str | None = None
    serial_number: str | None = None
    firmware_version: str | None = None
    mode: str | None = None
    updated_at: str | None = None


@dataclass
class StationState:
    online: str | None = None
    firmware: str | None = None
    device_name: str | None = None
    utc: str | None = None
    updated_at: str | None = None


@dataclass
class TipState:
    id: str | None = None
    serial_number: str | None = None
    wattage_raw: str | None = None
    wattage_w: float | None = None
    temperature_raw: str | None = None
    temperature_c: float | None = None
    temperature_offset_raw: str | None = None
    temperature_offset_c: float | None = None
    energy_raw: str | None = None
    energy_consumption: float | None = None
    updated_at: str | None = None


@dataclass
class AppState:
    station: StationState = field(default_factory=StationState)
    tools: dict[str, ToolState] = field(
        default_factory=lambda: {"Tool1": ToolState(), "Tool2": ToolState()}
    )
    tips: dict[str, TipState] = field(
        default_factory=lambda: {"Tip1": TipState(), "Tip2": TipState()}
    )
    last_topic: str | None = None
    last_payload: str | None = None
    message_count: int = 0


class StateStore:
    def __init__(self) -> None:
        self._state = AppState()
        self._lock = threading.Lock()

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _parse_number(self, payload_value: str) -> float | None:
        cleaned = payload_value.strip().replace(",", ".")
        match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None

    def _parse_deci_value(self, payload_value: str) -> float | None:
        numeric = self._parse_number(payload_value)
        if numeric is None:
            return None
        return numeric / 10.0

    def update_from_topic(self, topic: str, payload_value: str) -> None:
        with self._lock:
            self._state.message_count += 1
            self._state.last_topic = topic
            self._state.last_payload = payload_value

            parts = topic.split("/")
            if len(parts) < 4 or parts[0].upper() != "WXSMART":
                return

            if "/STATUS/ONLINE" in topic:
                self._state.station.online = payload_value
                self._state.station.updated_at = self._now()
                return

            if "/Station1/Version/Firmware" in topic:
                self._state.station.firmware = payload_value
                self._state.station.updated_at = self._now()
                return

            if "/Config/System/DeviceName" in topic:
                self._state.station.device_name = payload_value
                self._state.station.updated_at = self._now()
                return

            if "/Station1/UTC" in topic:
                self._state.station.utc = payload_value
                self._state.station.updated_at = self._now()
                return

            tip_name = "Tip1" if "/STATUS/Tip1/" in topic else "Tip2" if "/STATUS/Tip2/" in topic else None
            if tip_name is not None:
                tip = self._state.tips[tip_name]
                if topic.endswith("/ID"):
                    tip.id = payload_value
                elif topic.endswith("/SerialNumber"):
                    tip.serial_number = payload_value
                elif topic.endswith("/Wattage"):
                    tip.wattage_raw = payload_value
                    tip.wattage_w = self._parse_number(payload_value)
                elif "/Temperature/Read" in topic:
                    tip.temperature_raw = payload_value
                    tip.temperature_c = self._parse_deci_value(payload_value)
                elif "/Temperature/Offset" in topic:
                    tip.temperature_offset_raw = payload_value
                    tip.temperature_offset_c = self._parse_deci_value(payload_value)
                elif "/Energy/Consumption" in topic:
                    tip.energy_raw = payload_value
                    tip.energy_consumption = self._parse_number(payload_value)
                tip.updated_at = self._now()
                return

            tool_name = "Tool1" if "/STATUS/Tool1/" in topic else "Tool2" if "/STATUS/Tool2/" in topic else None
            if tool_name is None:
                return

            tool = self._state.tools[tool_name]
            if topic.endswith("/ID"):
                tool.id = payload_value
            elif "/Temperature/Read" in topic:
                tool.temperature_raw = payload_value
                tool.temperature_c = self._parse_deci_value(payload_value)
            elif "/Power/Read" in topic:
                tool.power_raw = payload_value
                tool.power_w = self._parse_deci_value(payload_value)
                tool.power_updated_at = self._now()
            elif "/Power" in topic:
                tool.power_raw = payload_value
                tool.power_w = self._parse_number(payload_value)
                tool.power_updated_at = self._now()
            elif "/OperatingHours/Standby" in topic:
                tool.standby_raw = payload_value
                tool.standby_updated_at = self._now()
            elif "/Counter/Time" in topic:
                tool.counter_time = payload_value
                tool.counter_updated_at = self._now()
            elif "/OperatingHours/Total" in topic:
                tool.operating_hours_total = payload_value
            elif "/SerialNumber" in topic:
                tool.serial_number = payload_value
            elif "/Version/Firmware" in topic:
                tool.firmware_version = payload_value
            elif "/Status/Mode" in topic:
                tool.mode = payload_value
            elif topic.endswith("/State"):
                tool.mode = payload_value

            tool.updated_at = self._now()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._state)
