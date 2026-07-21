from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from .schemas import (
    Acceleration,
    DataQuality,
    Orientation,
    Position,
    RawSensorMessage,
    TelemetryFrame,
    VehicleState,
    Velocity,
)


@dataclass
class _VehicleFusionState:
    acceleration: dict[str, float] = field(
        default_factory=lambda: {"ax_mps2": 0.0, "ay_mps2": 0.0, "az_mps2": 0.0}
    )
    orientation: dict[str, float] = field(
        default_factory=lambda: {"heading_deg": 0.0, "pitch_deg": 0.0, "roll_deg": 0.0}
    )
    battery_percent: float = 100.0
    operating_mode: str = "UNKNOWN"
    autonomy_enabled: bool = True
    emergency_stop: bool = False


class RawMessageNormalizer:
    """Combines the latest sensor state and emits telemetry on GNSS/odometry updates.

    This is deliberately a transparent baseline normalizer rather than a Kalman filter.
    It demonstrates the acquisition boundary while keeping sensor fusion replaceable.
    """

    def __init__(self) -> None:
        self._states: dict[tuple[str, str], _VehicleFusionState] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _number(payload: dict[str, Any], key: str, default: float = 0.0) -> float:
        try:
            return float(payload.get(key, default))
        except (TypeError, ValueError):
            return default

    def process(self, message: RawSensorMessage) -> TelemetryFrame | None:
        key = (message.vehicle_id, message.mission_id)
        with self._lock:
            state = self._states.setdefault(key, _VehicleFusionState())
            payload = message.payload

            if message.message_type == "IMU":
                state.acceleration = {
                    "ax_mps2": self._number(payload, "ax_mps2"),
                    "ay_mps2": self._number(payload, "ay_mps2"),
                    "az_mps2": self._number(payload, "az_mps2"),
                }
                state.orientation = {
                    "heading_deg": self._number(
                        payload, "heading_deg", state.orientation["heading_deg"]
                    )
                    % 360.0,
                    "pitch_deg": max(
                        -90.0,
                        min(90.0, self._number(payload, "pitch_deg", state.orientation["pitch_deg"])),
                    ),
                    "roll_deg": max(
                        -180.0,
                        min(180.0, self._number(payload, "roll_deg", state.orientation["roll_deg"])),
                    ),
                }
                return None

            if message.message_type == "BATTERY":
                state.battery_percent = max(
                    0.0, min(100.0, self._number(payload, "battery_percent", state.battery_percent))
                )
                return None

            if message.message_type == "VEHICLE_STATUS":
                state.operating_mode = str(payload.get("operating_mode", state.operating_mode))
                state.autonomy_enabled = bool(
                    payload.get("autonomy_enabled", state.autonomy_enabled)
                )
                state.emergency_stop = bool(payload.get("emergency_stop", state.emergency_stop))
                return None

            if message.message_type not in {"GNSS", "ODOMETRY"}:
                return None

            vx = self._number(payload, "vx_mps")
            vy = self._number(payload, "vy_mps")
            vz = self._number(payload, "vz_mps")
            speed = self._number(payload, "speed_mps", math.sqrt(vx * vx + vy * vy + vz * vz))
            if "heading_deg" in payload:
                heading = self._number(payload, "heading_deg") % 360.0
            elif abs(vx) + abs(vy) > 1e-12:
                heading = math.degrees(math.atan2(vy, vx)) % 360.0
            else:
                heading = state.orientation["heading_deg"]
            state.orientation["heading_deg"] = heading

            coordinate_frame = str(payload.get("coordinate_frame", "LOCAL_ENU"))
            if coordinate_frame not in {"LOCAL_ENU", "WGS84"}:
                coordinate_frame = "LOCAL_ENU"

            return TelemetryFrame(
                schema_version="0.3.1",
                message_id=uuid4(),
                vehicle_id=message.vehicle_id,
                mission_id=message.mission_id,
                sequence_no=message.sequence_no,
                timestamp_utc=message.timestamp_utc,
                source=f"normalizer:{message.sensor_id}",
                coordinate_frame=coordinate_frame,
                position=Position(
                    x_m=self._number(payload, "x_m"),
                    y_m=self._number(payload, "y_m"),
                    z_m=self._number(payload, "z_m"),
                    latitude_deg=(
                        self._number(payload, "latitude_deg")
                        if payload.get("latitude_deg") is not None
                        else None
                    ),
                    longitude_deg=(
                        self._number(payload, "longitude_deg")
                        if payload.get("longitude_deg") is not None
                        else None
                    ),
                ),
                velocity=Velocity(
                    vx_mps=vx,
                    vy_mps=vy,
                    vz_mps=vz,
                    speed_mps=max(0.0, speed),
                ),
                acceleration=Acceleration(**state.acceleration),
                orientation=Orientation(**state.orientation),
                state=VehicleState(
                    battery_percent=state.battery_percent,
                    operating_mode=state.operating_mode,
                    autonomy_enabled=state.autonomy_enabled,
                    emergency_stop=state.emergency_stop,
                ),
                quality=DataQuality(
                    valid=message.quality.valid,
                    position_source=message.message_type,
                    confidence=message.quality.confidence,
                ),
            )
