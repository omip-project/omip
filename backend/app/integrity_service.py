from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import floor
from typing import Any

from .config import (INTEGRITY_CLOCK_DRIFT_MS, INTEGRITY_CRITICAL_LATENCY_MS,
                     INTEGRITY_CRITICAL_LOW_RATE_RATIO,
                     INTEGRITY_FUTURE_CRITICAL_MS, INTEGRITY_FUTURE_WARNING_MS,
                     INTEGRITY_HIGH_RATE_RATIO, INTEGRITY_LOW_RATE_RATIO,
                     INTEGRITY_RATE_MIN_SPAN_S, INTEGRITY_RATE_WINDOW_S,
                     INTEGRITY_REALTIME_MAX_SKEW_S,
                     INTEGRITY_WARNING_LATENCY_MS)
from .database import OmipRepository
from .schemas import IntegrityFinding, RawSensorMessage, TelemetryFrame

RECOVERABLE_CHECK_TYPES = {
    "LOW_SAMPLING_RATE",
    "HIGH_SAMPLING_RATE",
    "HIGH_LATENCY",
    "FUTURE_TIMESTAMP",
    "CLOCK_DRIFT",
}


@dataclass(slots=True)
class IntegrityAnalysis:
    findings: list[IntegrityFinding] = field(default_factory=list)
    evaluated_recoverable_types: set[str] = field(default_factory=set)
    active_recoverable_types: set[str] = field(default_factory=set)


class DataIntegrityService:
    """Persistent sequence, timing, sampling-rate and latency checks.

    Sequence state and recent timing samples are read from SQLite before the
    incoming message is inserted. This preserves behaviour across backend
    restarts and keeps the service stateless enough for local multi-worker
    development.
    """

    def __init__(self, repository: OmipRepository) -> None:
        self._repository = repository

    def analyse_raw(self, message: RawSensorMessage) -> list[IntegrityFinding]:
        return self.analyse_raw_detailed(message).findings

    def analyse_raw_detailed(self, message: RawSensorMessage) -> IntegrityAnalysis:
        now = datetime.now(timezone.utc)
        state = self._repository.raw_integrity_state(
            message.mission_id,
            message.sensor_id,
            str(message.message_id),
            message.sequence_no,
            rate_window_s=INTEGRITY_RATE_WINDOW_S,
        )
        findings = self._analyse_sequence(
            stream_kind="RAW_SENSOR",
            vehicle_id=message.vehicle_id,
            sensor_id=message.sensor_id,
            mission_id=message.mission_id,
            message_id=str(message.message_id),
            sequence_no=message.sequence_no,
            state=state,
        )
        duplicate_id = any(
            finding.details.get("duplicate_kind") == "MESSAGE_ID"
            for finding in findings
        )
        result = IntegrityAnalysis(findings=findings)
        if duplicate_id:
            return result

        temporal, evaluated = self._analyse_timing(
            stream_kind="RAW_SENSOR",
            vehicle_id=message.vehicle_id,
            sensor_id=message.sensor_id,
            mission_id=message.mission_id,
            message_id=str(message.message_id),
            sequence_no=message.sequence_no,
            timestamp_utc=message.timestamp_utc,
            now=now,
            state=state,
        )
        result.findings.extend(temporal)
        result.evaluated_recoverable_types.update(evaluated)

        rate_findings, rate_evaluated = self._analyse_sampling_rate(
            vehicle_id=message.vehicle_id,
            sensor_id=message.sensor_id,
            mission_id=message.mission_id,
            message_id=str(message.message_id),
            sequence_no=message.sequence_no,
            now=now,
            state=state,
        )
        result.findings.extend(rate_findings)
        result.evaluated_recoverable_types.update(rate_evaluated)
        result.active_recoverable_types = {
            finding.check_type
            for finding in result.findings
            if finding.check_type in RECOVERABLE_CHECK_TYPES
        }
        return result

    def analyse_telemetry(self, frame: TelemetryFrame) -> list[IntegrityFinding]:
        return self.analyse_telemetry_detailed(frame).findings

    def analyse_telemetry_detailed(self, frame: TelemetryFrame) -> IntegrityAnalysis:
        now = datetime.now(timezone.utc)
        state = self._repository.telemetry_integrity_state(
            frame.mission_id,
            frame.vehicle_id,
            str(frame.message_id),
            frame.sequence_no,
        )
        findings = self._analyse_sequence(
            stream_kind="TELEMETRY",
            vehicle_id=frame.vehicle_id,
            sensor_id=None,
            mission_id=frame.mission_id,
            message_id=str(frame.message_id),
            sequence_no=frame.sequence_no,
            state=state,
        )
        duplicate_id = any(
            finding.details.get("duplicate_kind") == "MESSAGE_ID"
            for finding in findings
        )
        result = IntegrityAnalysis(findings=findings)
        if duplicate_id:
            return result
        temporal, evaluated = self._analyse_timing(
            stream_kind="TELEMETRY",
            vehicle_id=frame.vehicle_id,
            sensor_id=None,
            mission_id=frame.mission_id,
            message_id=str(frame.message_id),
            sequence_no=frame.sequence_no,
            timestamp_utc=frame.timestamp_utc,
            now=now,
            state=state,
        )
        result.findings.extend(temporal)
        result.evaluated_recoverable_types.update(evaluated)
        result.active_recoverable_types = {
            finding.check_type
            for finding in result.findings
            if finding.check_type in RECOVERABLE_CHECK_TYPES
        }
        return result

    @staticmethod
    def _stream_parts(
        stream_kind: str,
        vehicle_id: str,
        sensor_id: str | None,
        mission_id: str,
    ) -> tuple[str, str, str]:
        stream_id = sensor_id or f"{vehicle_id}-TELEMETRY"
        key_prefix = f"{stream_kind}:{mission_id}:{stream_id}"
        alert_suffix = f"{mission_id}:{stream_id}"
        return stream_id, key_prefix, alert_suffix

    @classmethod
    def _analyse_sequence(
        cls,
        *,
        stream_kind: str,
        vehicle_id: str,
        sensor_id: str | None,
        mission_id: str,
        message_id: str,
        sequence_no: int,
        state: dict[str, Any],
    ) -> list[IntegrityFinding]:
        stream_id, key_prefix, alert_suffix = cls._stream_parts(
            stream_kind, vehicle_id, sensor_id, mission_id
        )

        if bool(state.get("message_id_exists")):
            return [
                IntegrityFinding(
                    dedup_key=f"DUPLICATE_MESSAGE_ID:{key_prefix}:{message_id}",
                    stream_kind=stream_kind,
                    check_type="DUPLICATE_MESSAGE",
                    vehicle_id=vehicle_id,
                    sensor_id=sensor_id,
                    mission_id=mission_id,
                    message_id=message_id,
                    sequence_no=sequence_no,
                    description=f"Message ID {message_id} was received more than once on {stream_id}.",
                    details={
                        "duplicate_kind": "MESSAGE_ID",
                        "duplicate_message_id": message_id,
                        "sequence_no": sequence_no,
                    },
                    alert_type="DUPLICATE_MESSAGE",
                    alert_title=f"Duplicate message on {stream_id}",
                    alert_active_key=f"DUPLICATE_MESSAGE:{alert_suffix}",
                )
            ]

        max_sequence = state.get("max_sequence")
        max_sequence = int(max_sequence) if max_sequence is not None else None

        if bool(state.get("sequence_exists")):
            findings = [
                IntegrityFinding(
                    dedup_key=f"DUPLICATE_SEQUENCE:{key_prefix}:{message_id}",
                    stream_kind=stream_kind,
                    check_type="DUPLICATE_MESSAGE",
                    vehicle_id=vehicle_id,
                    sensor_id=sensor_id,
                    mission_id=mission_id,
                    message_id=message_id,
                    sequence_no=sequence_no,
                    description=(
                        f"Sequence number {sequence_no} was reused on {stream_id} with a new message ID."
                    ),
                    details={
                        "duplicate_kind": "SEQUENCE_NUMBER",
                        "sequence_no": sequence_no,
                        "message_id": message_id,
                    },
                    alert_type="DUPLICATE_MESSAGE",
                    alert_title=f"Duplicate sequence on {stream_id}",
                    alert_active_key=f"DUPLICATE_MESSAGE:{alert_suffix}",
                )
            ]
            if max_sequence is not None and sequence_no < max_sequence:
                findings.append(
                    IntegrityFinding(
                        dedup_key=f"OUT_OF_ORDER:{key_prefix}:{message_id}",
                        stream_kind=stream_kind,
                        check_type="OUT_OF_ORDER",
                        vehicle_id=vehicle_id,
                        sensor_id=sensor_id,
                        mission_id=mission_id,
                        message_id=message_id,
                        sequence_no=sequence_no,
                        description=f"Sequence {sequence_no} arrived after sequence {max_sequence} on {stream_id}.",
                        details={
                            "actual_sequence": sequence_no,
                            "previous_max_sequence": max_sequence,
                            "sequence_distance": max_sequence - sequence_no,
                            "sequence_was_already_present": True,
                        },
                        alert_type="OUT_OF_ORDER",
                        alert_title=f"Out-of-order data on {stream_id}",
                        alert_active_key=f"OUT_OF_ORDER:{alert_suffix}",
                    )
                )
            return findings

        if max_sequence is None:
            return []

        if sequence_no < max_sequence:
            return [
                IntegrityFinding(
                    dedup_key=f"OUT_OF_ORDER:{key_prefix}:{message_id}",
                    stream_kind=stream_kind,
                    check_type="OUT_OF_ORDER",
                    vehicle_id=vehicle_id,
                    sensor_id=sensor_id,
                    mission_id=mission_id,
                    message_id=message_id,
                    sequence_no=sequence_no,
                    description=f"Sequence {sequence_no} arrived after sequence {max_sequence} on {stream_id}.",
                    details={
                        "actual_sequence": sequence_no,
                        "previous_max_sequence": max_sequence,
                        "sequence_distance": max_sequence - sequence_no,
                    },
                    alert_type="OUT_OF_ORDER",
                    alert_title=f"Out-of-order data on {stream_id}",
                    alert_active_key=f"OUT_OF_ORDER:{alert_suffix}",
                )
            ]

        if sequence_no > max_sequence + 1:
            expected = max_sequence + 1
            missing_count = sequence_no - expected
            return [
                IntegrityFinding(
                    dedup_key=f"SEQUENCE_GAP:{key_prefix}:{sequence_no}",
                    stream_kind=stream_kind,
                    check_type="SEQUENCE_GAP",
                    vehicle_id=vehicle_id,
                    sensor_id=sensor_id,
                    mission_id=mission_id,
                    message_id=message_id,
                    sequence_no=sequence_no,
                    description=(
                        f"Expected sequence {expected} but received {sequence_no} on {stream_id}; "
                        f"{missing_count} message(s) are missing."
                    ),
                    details={
                        "expected_sequence": expected,
                        "actual_sequence": sequence_no,
                        "previous_max_sequence": max_sequence,
                        "missing_count": missing_count,
                        "missing_from": expected,
                        "missing_to": sequence_no - 1,
                    },
                    alert_type="SEQUENCE_GAP",
                    alert_title=f"Sequence gap on {stream_id}",
                    alert_active_key=f"SEQUENCE_GAP:{alert_suffix}",
                )
            ]
        return []

    @classmethod
    def _analyse_timing(
        cls,
        *,
        stream_kind: str,
        vehicle_id: str,
        sensor_id: str | None,
        mission_id: str,
        message_id: str,
        sequence_no: int,
        timestamp_utc: datetime,
        now: datetime,
        state: dict[str, Any],
    ) -> tuple[list[IntegrityFinding], set[str]]:
        stream_id, key_prefix, alert_suffix = cls._stream_parts(
            stream_kind, vehicle_id, sensor_id, mission_id
        )
        findings: list[IntegrityFinding] = []
        evaluated: set[str] = set()

        latest_timestamp_value = state.get("latest_timestamp_utc")
        if latest_timestamp_value:
            latest_timestamp = datetime.fromisoformat(str(latest_timestamp_value))
            if latest_timestamp.tzinfo is None:
                latest_timestamp = latest_timestamp.replace(tzinfo=timezone.utc)
            if timestamp_utc < latest_timestamp:
                regression_ms = (
                    latest_timestamp - timestamp_utc
                ).total_seconds() * 1000.0
                findings.append(
                    IntegrityFinding(
                        dedup_key=f"TIMESTAMP_REGRESSION:{key_prefix}:{message_id}",
                        stream_kind=stream_kind,
                        check_type="TIMESTAMP_REGRESSION",
                        severity="WARNING",
                        vehicle_id=vehicle_id,
                        sensor_id=sensor_id,
                        mission_id=mission_id,
                        message_id=message_id,
                        sequence_no=sequence_no,
                        description=(
                            f"Timestamp moved backwards by {regression_ms:.1f} ms on {stream_id}."
                        ),
                        details={
                            "previous_timestamp_utc": latest_timestamp.isoformat(),
                            "actual_timestamp_utc": timestamp_utc.isoformat(),
                            "regression_ms": round(regression_ms, 3),
                        },
                        alert_type="TIMESTAMP_REGRESSION",
                        alert_title=f"Timestamp regression on {stream_id}",
                        alert_active_key=f"TIMESTAMP_REGRESSION:{alert_suffix}",
                    )
                )

        signed_latency_ms = (now - timestamp_utc).total_seconds() * 1000.0
        # Historical imports/backfills are not treated as live communication
        # latency. This avoids meaningless multi-hour latency alerts when old
        # datasets are uploaded through HTTP.
        realtime_eligible = (
            abs(signed_latency_ms) <= INTEGRITY_REALTIME_MAX_SKEW_S * 1000.0
        )
        if not realtime_eligible:
            return findings, evaluated

        evaluated.add("FUTURE_TIMESTAMP")
        if signed_latency_ms <= -INTEGRITY_FUTURE_WARNING_MS:
            future_ms = abs(signed_latency_ms)
            severity = (
                "CRITICAL" if future_ms >= INTEGRITY_FUTURE_CRITICAL_MS else "WARNING"
            )
            findings.append(
                IntegrityFinding(
                    dedup_key=f"FUTURE_TIMESTAMP:{key_prefix}:{message_id}",
                    stream_kind=stream_kind,
                    check_type="FUTURE_TIMESTAMP",
                    severity=severity,
                    vehicle_id=vehicle_id,
                    sensor_id=sensor_id,
                    mission_id=mission_id,
                    message_id=message_id,
                    sequence_no=sequence_no,
                    description=f"Timestamp is {future_ms:.1f} ms ahead of the server clock on {stream_id}.",
                    details={
                        "future_offset_ms": round(future_ms, 3),
                        "server_time_utc": now.isoformat(),
                        "message_timestamp_utc": timestamp_utc.isoformat(),
                    },
                    alert_type="FUTURE_TIMESTAMP",
                    alert_title=f"Future timestamp on {stream_id}",
                    alert_active_key=f"FUTURE_TIMESTAMP:{alert_suffix}",
                )
            )
        elif signed_latency_ms >= 0:
            evaluated.add("HIGH_LATENCY")
            if signed_latency_ms >= INTEGRITY_WARNING_LATENCY_MS:
                severity = (
                    "CRITICAL"
                    if signed_latency_ms >= INTEGRITY_CRITICAL_LATENCY_MS
                    else "WARNING"
                )
                findings.append(
                    IntegrityFinding(
                        dedup_key=f"HIGH_LATENCY:{key_prefix}:{message_id}",
                        stream_kind=stream_kind,
                        check_type="HIGH_LATENCY",
                        severity=severity,
                        vehicle_id=vehicle_id,
                        sensor_id=sensor_id,
                        mission_id=mission_id,
                        message_id=message_id,
                        sequence_no=sequence_no,
                        description=f"Communication latency is {signed_latency_ms:.1f} ms on {stream_id}.",
                        details={
                            "latency_ms": round(signed_latency_ms, 3),
                            "warning_threshold_ms": INTEGRITY_WARNING_LATENCY_MS,
                            "critical_threshold_ms": INTEGRITY_CRITICAL_LATENCY_MS,
                        },
                        alert_type="HIGH_LATENCY",
                        alert_title=f"High communication latency on {stream_id}",
                        alert_active_key=f"HIGH_LATENCY:{alert_suffix}",
                    )
                )

            previous_latency = state.get("previous_latency_ms")
            if previous_latency is not None:
                evaluated.add("CLOCK_DRIFT")
                drift_ms = signed_latency_ms - float(previous_latency)
                if abs(drift_ms) >= INTEGRITY_CLOCK_DRIFT_MS:
                    findings.append(
                        IntegrityFinding(
                            dedup_key=f"CLOCK_DRIFT:{key_prefix}:{message_id}",
                            stream_kind=stream_kind,
                            check_type="CLOCK_DRIFT",
                            severity="WARNING",
                            vehicle_id=vehicle_id,
                            sensor_id=sensor_id,
                            mission_id=mission_id,
                            message_id=message_id,
                            sequence_no=sequence_no,
                            description=(
                                f"Observed clock/latency offset changed by {drift_ms:.1f} ms on {stream_id}."
                            ),
                            details={
                                "previous_latency_ms": round(
                                    float(previous_latency), 3
                                ),
                                "current_latency_ms": round(signed_latency_ms, 3),
                                "drift_ms": round(drift_ms, 3),
                                "threshold_ms": INTEGRITY_CLOCK_DRIFT_MS,
                            },
                            alert_type="CLOCK_DRIFT",
                            alert_title=f"Clock drift on {stream_id}",
                            alert_active_key=f"CLOCK_DRIFT:{alert_suffix}",
                        )
                    )
        return findings, evaluated

    @classmethod
    def _analyse_sampling_rate(
        cls,
        *,
        vehicle_id: str,
        sensor_id: str,
        mission_id: str,
        message_id: str,
        sequence_no: int,
        now: datetime,
        state: dict[str, Any],
    ) -> tuple[list[IntegrityFinding], set[str]]:
        expected = state.get("expected_rate_hz")
        if expected is None or float(expected) <= 0:
            return [], set()

        timestamps: list[datetime] = []
        for value in state.get("recent_received_at_utc", []):
            try:
                parsed = datetime.fromisoformat(str(value))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                timestamps.append(parsed.astimezone(timezone.utc))
            except (TypeError, ValueError):
                continue
        timestamps.append(now)
        cutoff = now.timestamp() - INTEGRITY_RATE_WINDOW_S
        timestamps = sorted(item for item in timestamps if item.timestamp() >= cutoff)
        if len(timestamps) < 5:
            return [], set()
        span_s = (timestamps[-1] - timestamps[0]).total_seconds()
        if span_s < INTEGRITY_RATE_MIN_SPAN_S:
            return [], set()

        expected_rate = float(expected)
        actual_rate = (len(timestamps) - 1) / span_s if span_s > 0 else 0.0
        ratio = actual_rate / expected_rate
        evaluated = {"LOW_SAMPLING_RATE", "HIGH_SAMPLING_RATE"}
        stream_id, key_prefix, alert_suffix = cls._stream_parts(
            "RAW_SENSOR", vehicle_id, sensor_id, mission_id
        )
        bucket = floor(now.timestamp() / max(INTEGRITY_RATE_WINDOW_S, 1.0))

        if ratio < INTEGRITY_LOW_RATE_RATIO:
            severity = (
                "CRITICAL" if ratio < INTEGRITY_CRITICAL_LOW_RATE_RATIO else "WARNING"
            )
            return [
                IntegrityFinding(
                    dedup_key=f"LOW_SAMPLING_RATE:{key_prefix}:{bucket}",
                    stream_kind="RAW_SENSOR",
                    check_type="LOW_SAMPLING_RATE",
                    severity=severity,
                    vehicle_id=vehicle_id,
                    sensor_id=sensor_id,
                    mission_id=mission_id,
                    message_id=message_id,
                    sequence_no=sequence_no,
                    description=(
                        f"{stream_id} is producing {actual_rate:.2f} Hz; expected {expected_rate:.2f} Hz."
                    ),
                    details={
                        "expected_rate_hz": round(expected_rate, 4),
                        "actual_rate_hz": round(actual_rate, 4),
                        "rate_ratio": round(ratio, 4),
                        "window_s": round(span_s, 3),
                        "sample_count": len(timestamps),
                    },
                    alert_type="LOW_SAMPLING_RATE",
                    alert_title=f"Low sampling rate on {stream_id}",
                    alert_active_key=f"LOW_SAMPLING_RATE:{alert_suffix}",
                )
            ], evaluated

        if ratio > INTEGRITY_HIGH_RATE_RATIO:
            return [
                IntegrityFinding(
                    dedup_key=f"HIGH_SAMPLING_RATE:{key_prefix}:{bucket}",
                    stream_kind="RAW_SENSOR",
                    check_type="HIGH_SAMPLING_RATE",
                    severity="WARNING",
                    vehicle_id=vehicle_id,
                    sensor_id=sensor_id,
                    mission_id=mission_id,
                    message_id=message_id,
                    sequence_no=sequence_no,
                    description=(
                        f"{stream_id} is producing {actual_rate:.2f} Hz; expected {expected_rate:.2f} Hz."
                    ),
                    details={
                        "expected_rate_hz": round(expected_rate, 4),
                        "actual_rate_hz": round(actual_rate, 4),
                        "rate_ratio": round(ratio, 4),
                        "window_s": round(span_s, 3),
                        "sample_count": len(timestamps),
                    },
                    alert_type="HIGH_SAMPLING_RATE",
                    alert_title=f"High sampling rate on {stream_id}",
                    alert_active_key=f"HIGH_SAMPLING_RATE:{alert_suffix}",
                )
            ], evaluated
        return [], evaluated
