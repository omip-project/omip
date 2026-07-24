from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

MissionStatus = Literal["PLANNED", "RUNNING", "COMPLETED", "ABORTED"]
VehicleType = Literal["GROUND_VEHICLE", "AUV", "USV", "UAV", "SIMULATED", "OTHER"]
SimulationRunStatus = Literal[
    "QUEUED", "STARTING", "RUNNING", "STOPPING", "COMPLETED", "FAILED", "ABORTED"
]
ConnectionStatus = Literal[
    "ONLINE", "DEGRADED", "OFFLINE", "INACTIVE", "DISABLED", "UNKNOWN"
]
RawMessageType = Literal[
    "GNSS", "IMU", "ODOMETRY", "BATTERY", "VEHICLE_STATUS", "GENERIC"
]
EventSeverity = Literal["INFO", "WARNING", "CRITICAL"]
EventSource = Literal["MANUAL", "SIMULATOR", "SYSTEM", "IMPORTED"]
TransportType = Literal["HTTP", "MQTT", "FILE_UPLOAD", "SIMULATOR"]
HeartbeatState = Literal["RUNNING", "IDLE", "STOPPING"]
IntegrityCheckType = Literal[
    "SEQUENCE_GAP",
    "DUPLICATE_MESSAGE",
    "OUT_OF_ORDER",
    "LOW_SAMPLING_RATE",
    "HIGH_SAMPLING_RATE",
    "HIGH_LATENCY",
    "TIMESTAMP_REGRESSION",
    "FUTURE_TIMESTAMP",
    "CLOCK_DRIFT",
]
IntegrityStreamKind = Literal["RAW_SENSOR", "TELEMETRY"]
AlertType = Literal[
    "SEQUENCE_GAP",
    "DUPLICATE_MESSAGE",
    "OUT_OF_ORDER",
    "LOW_SAMPLING_RATE",
    "HIGH_SAMPLING_RATE",
    "HIGH_LATENCY",
    "TIMESTAMP_REGRESSION",
    "FUTURE_TIMESTAMP",
    "CLOCK_DRIFT",
]
AlertStatus = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]
AlertResolutionSource = Literal["MANUAL", "AUTOMATIC"]


class Position(BaseModel):
    x_m: float
    y_m: float
    z_m: float = 0.0
    latitude_deg: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude_deg: float | None = Field(default=None, ge=-180.0, le=180.0)


class Velocity(BaseModel):
    vx_mps: float
    vy_mps: float
    vz_mps: float = 0.0
    speed_mps: float = Field(ge=0.0)


class Acceleration(BaseModel):
    ax_mps2: float = 0.0
    ay_mps2: float = 0.0
    az_mps2: float = 0.0


class Orientation(BaseModel):
    heading_deg: float = Field(ge=0.0, lt=360.0)
    pitch_deg: float = Field(default=0.0, ge=-90.0, le=90.0)
    roll_deg: float = Field(default=0.0, ge=-180.0, le=180.0)


class VehicleState(BaseModel):
    battery_percent: float = Field(ge=0.0, le=100.0)
    operating_mode: str = Field(min_length=1, max_length=64)
    autonomy_enabled: bool = True
    emergency_stop: bool = False


class DataQuality(BaseModel):
    valid: bool = True
    position_source: str = Field(default="SIMULATED", min_length=1, max_length=32)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class TelemetryFrame(BaseModel):
    # v0.2 remains accepted so existing clients do not break.
    schema_version: Literal["0.2", "0.3", "0.3.1"] = "0.3.1"
    message_id: UUID
    vehicle_id: str = Field(min_length=1, max_length=128)
    mission_id: str = Field(min_length=1, max_length=128)
    sequence_no: int = Field(ge=0)
    timestamp_utc: datetime
    source: str = Field(default="simulator", min_length=1, max_length=128)
    coordinate_frame: Literal["LOCAL_ENU", "WGS84"] = "LOCAL_ENU"
    position: Position
    velocity: Velocity
    acceleration: Acceleration = Field(default_factory=Acceleration)
    orientation: Orientation
    state: VehicleState
    quality: DataQuality = Field(default_factory=DataQuality)

    @field_validator("timestamp_utc")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp_utc must include a timezone")
        return value.astimezone(timezone.utc)


class MissionCreate(BaseModel):
    mission_id: str | None = Field(default=None, min_length=1, max_length=128)
    vehicle_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=160)
    scenario_name: str | None = Field(default=None, max_length=128)
    description: str = Field(default="", max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VehicleCreate(BaseModel):
    vehicle_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    vehicle_name: str = Field(min_length=1, max_length=160)
    vehicle_type: VehicleType = "SIMULATED"
    manufacturer: str = Field(default="", max_length=160)
    model: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=2000)
    enabled: bool = True
    vehicle_profile_id: str | None = Field(default=None, min_length=1, max_length=128)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VehicleUpdate(BaseModel):
    vehicle_name: str | None = Field(default=None, min_length=1, max_length=160)
    vehicle_type: VehicleType | None = None
    manufacturer: str | None = Field(default=None, max_length=160)
    model: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    vehicle_profile_id: str | None = Field(default=None, min_length=1, max_length=128)
    capabilities: dict[str, bool] | None = None
    parameters: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class SensorCreate(BaseModel):
    sensor_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    sensor_name: str = Field(min_length=1, max_length=160)
    sensor_type: RawMessageType
    manufacturer: str = Field(default="", max_length=160)
    model: str = Field(default="", max_length=160)
    unit: str = Field(default="", max_length=64)
    sampling_rate_hz: float | None = Field(default=None, gt=0.0, le=10_000.0)
    coordinate_frame: str = Field(default="LOCAL_ENU", min_length=1, max_length=64)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class SensorUpdate(BaseModel):
    sensor_name: str | None = Field(default=None, min_length=1, max_length=160)
    sensor_type: RawMessageType | None = None
    manufacturer: str | None = Field(default=None, max_length=160)
    model: str | None = Field(default=None, max_length=160)
    unit: str | None = Field(default=None, max_length=64)
    sampling_rate_hz: float | None = Field(default=None, gt=0.0, le=10_000.0)
    coordinate_frame: str | None = Field(default=None, min_length=1, max_length=64)
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class RawSensorMessage(BaseModel):
    schema_version: Literal["0.3", "0.3.1"] = "0.3.1"
    message_id: UUID
    vehicle_id: str = Field(min_length=1, max_length=128)
    sensor_id: str = Field(min_length=1, max_length=128)
    mission_id: str = Field(min_length=1, max_length=128)
    sequence_no: int = Field(ge=0)
    timestamp_utc: datetime
    message_type: RawMessageType
    payload: dict[str, Any]
    quality: DataQuality = Field(default_factory=DataQuality)

    @field_validator("timestamp_utc")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp_utc must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def basic_payload_validation(self) -> "RawSensorMessage":
        required: dict[str, set[str]] = {
            "GNSS": {"x_m", "y_m"},
            "ODOMETRY": {"x_m", "y_m"},
            "IMU": {"ax_mps2", "ay_mps2", "az_mps2"},
            "BATTERY": {"battery_percent"},
            "VEHICLE_STATUS": {"operating_mode"},
            "GENERIC": set(),
        }
        missing = required[self.message_type] - set(self.payload)
        if missing:
            raise ValueError(
                f"payload for {self.message_type} is missing fields: {', '.join(sorted(missing))}"
            )
        if "battery_percent" in self.payload:
            value = float(self.payload["battery_percent"])
            if not 0.0 <= value <= 100.0:
                raise ValueError("battery_percent must be between 0 and 100")
        return self


class VehicleHeartbeat(BaseModel):
    schema_version: Literal["0.3.1"] = "0.3.1"
    message_id: UUID
    vehicle_id: str = Field(min_length=1, max_length=128)
    mission_id: str | None = Field(default=None, min_length=1, max_length=128)
    timestamp_utc: datetime
    state: HeartbeatState = "RUNNING"
    source: str = Field(default="simulator", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp_utc")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp_utc must include a timezone")
        return value.astimezone(timezone.utc)


class MissionEventCreate(BaseModel):
    event_id: str | None = Field(default=None, min_length=1, max_length=128)
    vehicle_id: str = Field(min_length=1, max_length=128)
    event_type: str = Field(min_length=1, max_length=128)
    start_timestamp_utc: datetime
    end_timestamp_utc: datetime | None = None
    severity: EventSeverity = "INFO"
    source: EventSource = "MANUAL"
    description: str = Field(default="", max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("start_timestamp_utc", "end_timestamp_utc")
    @classmethod
    def timestamps_must_be_timezone_aware(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event timestamps must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def end_must_not_precede_start(self) -> "MissionEventCreate":
        if self.end_timestamp_utc and self.end_timestamp_utc < self.start_timestamp_utc:
            raise ValueError(
                "end_timestamp_utc cannot be earlier than start_timestamp_utc"
            )
        return self


class MissionEventUpdate(BaseModel):
    event_type: str | None = Field(default=None, min_length=1, max_length=128)
    start_timestamp_utc: datetime | None = None
    end_timestamp_utc: datetime | None = None
    severity: EventSeverity | None = None
    source: EventSource | None = None
    description: str | None = Field(default=None, max_length=4000)
    metadata: dict[str, Any] | None = None

    @field_validator("start_timestamp_utc", "end_timestamp_utc")
    @classmethod
    def timestamps_must_be_timezone_aware(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event timestamps must include a timezone")
        return value.astimezone(timezone.utc)


class MqttControlRequest(BaseModel):
    """Runtime MQTT bridge settings exposed by the local operations console."""

    enabled: bool
    host: str | None = Field(default=None, min_length=1, max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)
    raw_topic: str | None = Field(default=None, min_length=1, max_length=256)
    telemetry_topic: str | None = Field(default=None, min_length=1, max_length=256)
    heartbeat_topic: str | None = Field(default=None, min_length=1, max_length=256)


class IntegrityFinding(BaseModel):
    """A transient integrity finding produced before it is persisted."""

    dedup_key: str = Field(min_length=1, max_length=512)
    stream_kind: IntegrityStreamKind
    check_type: IntegrityCheckType
    severity: EventSeverity = "WARNING"
    vehicle_id: str = Field(min_length=1, max_length=128)
    sensor_id: str | None = Field(default=None, min_length=1, max_length=128)
    mission_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=128)
    sequence_no: int = Field(ge=0)
    description: str = Field(min_length=1, max_length=4000)
    details: dict[str, Any] = Field(default_factory=dict)
    alert_type: AlertType
    alert_title: str = Field(min_length=1, max_length=240)
    alert_active_key: str = Field(min_length=1, max_length=512)


class AlertActionRequest(BaseModel):
    actor: str = Field(default="operator", min_length=1, max_length=160)
    note: str = Field(default="", max_length=2000)


class RetentionPolicyUpdate(BaseModel):
    raw_messages_days: int | None = Field(default=None, ge=1, le=3650)
    telemetry_days: int | None = Field(default=None, ge=1, le=3650)
    application_logs_days: int | None = Field(default=None, ge=1, le=3650)
    system_snapshots_days: int | None = Field(default=None, ge=1, le=3650)


class CleanupExecuteRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=128)


class ExportJobCreate(BaseModel):
    mission_id: str = Field(min_length=1, max_length=128)
    export_format: Literal[
        "package", "telemetry_csv", "telemetry_jsonl", "raw_csv", "raw_jsonl"
    ] = "package"


class BackupCreateRequest(BaseModel):
    label: str = Field(default="manual", min_length=1, max_length=80)


class VehicleProfileCreate(BaseModel):
    profile_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    profile_name: str = Field(min_length=1, max_length=160)
    vehicle_type: VehicleType
    schema_version: str = Field(default="1.0", min_length=1, max_length=32)
    description: str = Field(default="", max_length=2000)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class VehicleProfileUpdate(BaseModel):
    profile_name: str | None = Field(default=None, min_length=1, max_length=160)
    schema_version: str | None = Field(default=None, min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=2000)
    capabilities: dict[str, bool] | None = None
    parameters: dict[str, Any] | None = None
    enabled: bool | None = None


# ---------------------------------------------------------------------------
# Environment context and obstacle-interaction models (v0.5.2)
# ---------------------------------------------------------------------------
CoordinateFrame = Literal["LOCAL_ENU", "WGS84"]
GeometryType = Literal["POINT", "CIRCLE", "SPHERE", "BOX", "POLYGON"]
ObstacleType = Literal[
    "STATIC_OBSTACLE",
    "DYNAMIC_OBSTACLE",
    "UNKNOWN_OBJECT",
    "TERRAIN",
    "BUILDING",
    "VESSEL",
    "UNDERWATER_STRUCTURE",
]
ConstraintType = Literal[
    "SPEED_LIMIT",
    "NO_ENTRY_ZONE",
    "MAXIMUM_ALTITUDE",
    "MINIMUM_ALTITUDE",
    "MAXIMUM_DEPTH",
    "MINIMUM_DEPTH",
    "MISSION_BOUNDARY",
    "REQUIRED_CORRIDOR",
    "CHECKPOINT",
    "BATTERY_RETURN_THRESHOLD",
    "COMMUNICATION_REQUIRED_ZONE",
]
ExternalFieldType = Literal[
    "WIND",
    "OCEAN_CURRENT",
    "WATER_CURRENT",
    "ROAD_SLOPE",
    "SURFACE_FRICTION",
    "TERRAIN_ELEVATION",
    "COMMUNICATION_QUALITY",
    "GNSS_QUALITY",
]
ConstraintSeverity = Literal["ADVISORY", "RECOMMENDED", "MANDATORY"]
EnvironmentSource = Literal["SCENARIO", "MANUAL", "IMPORTED", "INFERRED", "SENSOR"]


class EnvironmentPoint(BaseModel):
    x_m: float
    y_m: float
    z_m: float = 0.0


class EnvironmentVector(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    unit: str = Field(default="m/s", max_length=32)


class EnvironmentGeometry(BaseModel):
    geometry_type: GeometryType
    position: EnvironmentPoint | None = None
    radius_m: float | None = Field(default=None, gt=0.0)
    width_m: float | None = Field(default=None, gt=0.0)
    length_m: float | None = Field(default=None, gt=0.0)
    height_m: float | None = Field(default=None, gt=0.0)
    points: list[EnvironmentPoint] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def validate_geometry(self) -> "EnvironmentGeometry":
        if (
            self.geometry_type in {"POINT", "CIRCLE", "SPHERE", "BOX"}
            and self.position is None
        ):
            raise ValueError(f"{self.geometry_type} geometry requires position")
        if self.geometry_type in {"CIRCLE", "SPHERE"} and self.radius_m is None:
            raise ValueError(f"{self.geometry_type} geometry requires radius_m")
        if self.geometry_type == "BOX" and (
            self.width_m is None or self.length_m is None
        ):
            raise ValueError("BOX geometry requires width_m and length_m")
        if self.geometry_type == "POLYGON" and len(self.points) < 3:
            raise ValueError("POLYGON geometry requires at least three points")
        return self


class Applicability(BaseModel):
    applies_to_vehicle_types: list[VehicleType] = Field(default_factory=list)
    applies_to_vehicle_ids: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)


class ObstacleCreate(Applicability):
    obstacle_id: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    name: str = Field(min_length=1, max_length=160)
    obstacle_type: ObstacleType = "STATIC_OBSTACLE"
    geometry: EnvironmentGeometry
    coordinate_frame: CoordinateFrame = "LOCAL_ENU"
    source: EnvironmentSource = "SCENARIO"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    velocity: EnvironmentVector | None = None
    heading_deg: float | None = Field(default=None, ge=0.0, lt=360.0)
    valid_from_utc: datetime | None = None
    valid_to_utc: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObstacleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    obstacle_type: ObstacleType | None = None
    geometry: EnvironmentGeometry | None = None
    coordinate_frame: CoordinateFrame | None = None
    source: EnvironmentSource | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    velocity: EnvironmentVector | None = None
    heading_deg: float | None = Field(default=None, ge=0.0, lt=360.0)
    valid_from_utc: datetime | None = None
    valid_to_utc: datetime | None = None
    applies_to_vehicle_types: list[VehicleType] | None = None
    applies_to_vehicle_ids: list[str] | None = None
    required_capabilities: list[str] | None = None
    metadata: dict[str, Any] | None = None


class EnvironmentConstraintCreate(Applicability):
    constraint_id: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    name: str = Field(min_length=1, max_length=160)
    constraint_type: ConstraintType
    geometry: EnvironmentGeometry | None = None
    value: float | str | bool | None = None
    unit: str = Field(default="", max_length=32)
    severity: ConstraintSeverity = "MANDATORY"
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnvironmentConstraintUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    constraint_type: ConstraintType | None = None
    geometry: EnvironmentGeometry | None = None
    value: float | str | bool | None = None
    unit: str | None = Field(default=None, max_length=32)
    severity: ConstraintSeverity | None = None
    enabled: bool | None = None
    applies_to_vehicle_types: list[VehicleType] | None = None
    applies_to_vehicle_ids: list[str] | None = None
    required_capabilities: list[str] | None = None
    metadata: dict[str, Any] | None = None


class ExternalFieldCreate(Applicability):
    field_id: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    name: str = Field(min_length=1, max_length=160)
    field_type: ExternalFieldType
    geometry: EnvironmentGeometry | None = None
    coordinate_frame: CoordinateFrame = "LOCAL_ENU"
    vector: EnvironmentVector | None = None
    scalar_value: float | None = None
    unit: str = Field(default="", max_length=32)
    valid_from_utc: datetime | None = None
    valid_to_utc: datetime | None = None
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalFieldUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    field_type: ExternalFieldType | None = None
    geometry: EnvironmentGeometry | None = None
    coordinate_frame: CoordinateFrame | None = None
    vector: EnvironmentVector | None = None
    scalar_value: float | None = None
    unit: str | None = Field(default=None, max_length=32)
    valid_from_utc: datetime | None = None
    valid_to_utc: datetime | None = None
    enabled: bool | None = None
    applies_to_vehicle_types: list[VehicleType] | None = None
    applies_to_vehicle_ids: list[str] | None = None
    required_capabilities: list[str] | None = None
    metadata: dict[str, Any] | None = None


class ScenarioCreate(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    coordinate_frame: CoordinateFrame = "LOCAL_ENU"
    origin: dict[str, Any] = Field(default_factory=dict)
    default_duration_s: float = Field(default=60.0, ge=0.0, le=604800.0)
    motion: dict[str, Any] = Field(default_factory=dict)
    obstacle_avoidance: dict[str, Any] = Field(default_factory=dict)
    sensor_rates_hz: dict[str, float] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    faults: dict[str, Any] = Field(default_factory=dict)
    obstacles: list[ObstacleCreate] = Field(default_factory=list)
    constraints: list[EnvironmentConstraintCreate] = Field(default_factory=list)
    external_fields: list[ExternalFieldCreate] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ScenarioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    coordinate_frame: CoordinateFrame | None = None
    origin: dict[str, Any] | None = None
    default_duration_s: float | None = Field(default=None, ge=0.0, le=604800.0)
    motion: dict[str, Any] | None = None
    obstacle_avoidance: dict[str, Any] | None = None
    sensor_rates_hz: dict[str, float] | None = None
    quality: dict[str, Any] | None = None
    faults: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    enabled: bool | None = None


class MissionEnvironmentCapture(BaseModel):
    scenario: dict[str, Any]
    vehicle_type: VehicleType
    vehicle_profile_id: str = Field(min_length=1, max_length=128)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    effective_parameters: dict[str, Any] = Field(default_factory=dict)
    random_seed: int = Field(default=42, ge=0, le=2_147_483_647)


class SimulationRunCreate(BaseModel):
    vehicle_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    vehicle_type: VehicleType
    vehicle_profile_id: str = Field(min_length=1, max_length=128)
    scenario_id: str = Field(
        default="multi_sensor_nominal",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    mission_id: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    duration_s: float = Field(default=60.0, ge=0.0, le=604800.0)
    transport: Literal["http", "mqtt"] = "http"
    random_seed: int = Field(default=42, ge=0, le=2_147_483_647)
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)
    launch_process: bool = True


class SimulationRunStopRequest(BaseModel):
    reason: str = Field(default="Stopped by operator", max_length=500)
