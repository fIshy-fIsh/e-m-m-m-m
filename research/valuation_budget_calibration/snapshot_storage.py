"""Immutable snapshot files and append-only manifest storage."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from research.valuation_budget_calibration.snapshot_schema import (
    PROTOCOL_ID,
    SAFE_REASONS,
    SCHEMA_VERSION,
    ObservationStatus,
    RepresentativeSnapshot,
    canonical_snapshot_bytes,
    scan_for_secret_material,
)

_FIXED_ERROR = "representative snapshot storage failed"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "protocol_id",
        "campaign_id",
        "snapshot_id",
        "nominal_slot_utc",
        "scheduled_for_utc",
        "observed_at_utc",
        "capture_completed_at_utc",
        "stratum",
        "outcome",
        "reason",
        "snapshot_path",
        "snapshot_sha256",
        "request_count",
        "pages_completed",
        "pages_failed",
        "listings_received",
        "supersedes_snapshot_id",
    }
)
_MANIFEST_OUTCOMES = frozenset(
    {
        ObservationStatus.COMPLETE.value,
        ObservationStatus.PARTIAL.value,
        ObservationStatus.INVALID.value,
        "MISSED_OBSERVATION",
    }
)


class SnapshotStorageError(RuntimeError):
    """Storage failed with a safe fixed public message."""

    def __init__(self, *, reason: str) -> None:
        super().__init__(_FIXED_ERROR)
        self.reason = reason


@dataclass(frozen=True, kw_only=True)
class SnapshotWriteReceipt:
    snapshot_path: Path
    relative_snapshot_path: str
    snapshot_sha256: str
    bytes_written: int


@dataclass(frozen=True, kw_only=True)
class ManifestEntry:
    campaign_id: str
    snapshot_id: str | None
    nominal_slot_utc: str
    scheduled_for_utc: str
    observed_at_utc: str | None
    capture_completed_at_utc: str | None
    input_rarity: str
    stattrak_mode: str
    outcome: str
    reason: str | None
    snapshot_path: str | None
    snapshot_sha256: str | None
    request_count: int
    pages_completed: int
    pages_failed: int
    listings_received: int
    supersedes_snapshot_id: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "protocol_id": PROTOCOL_ID,
            "campaign_id": self.campaign_id,
            "snapshot_id": self.snapshot_id,
            "nominal_slot_utc": self.nominal_slot_utc,
            "scheduled_for_utc": self.scheduled_for_utc,
            "observed_at_utc": self.observed_at_utc,
            "capture_completed_at_utc": self.capture_completed_at_utc,
            "stratum": {
                "input_rarity": self.input_rarity,
                "stattrak_mode": self.stattrak_mode,
            },
            "outcome": self.outcome,
            "reason": self.reason,
            "snapshot_path": self.snapshot_path,
            "snapshot_sha256": self.snapshot_sha256,
            "request_count": self.request_count,
            "pages_completed": self.pages_completed,
            "pages_failed": self.pages_failed,
            "listings_received": self.listings_received,
            "supersedes_snapshot_id": self.supersedes_snapshot_id,
        }


class SnapshotArtifactStore:
    """Write immutable snapshots and append-only manifest lines under one root."""

    def __init__(self, *, artifact_root: Path, campaign_id: str) -> None:
        self._artifact_root = artifact_root.resolve()
        self._campaign_id = campaign_id
        self._campaign_root = (
            self._artifact_root
            / "valuation_budget_calibration"
            / campaign_id
        )
        self._snapshot_root = self._campaign_root / "snapshots"
        self._manifest_path = self._campaign_root / "manifest.v1.jsonl"

    @property
    def campaign_root(self) -> Path:
        return self._campaign_root

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    def write_snapshot(
        self,
        snapshot: RepresentativeSnapshot,
    ) -> SnapshotWriteReceipt:
        if snapshot.campaign_id != self._campaign_id:
            raise SnapshotStorageError(reason="campaign_mismatch")
        content = canonical_snapshot_bytes(snapshot)
        digest = hashlib.sha256(content).hexdigest()
        filename = _snapshot_filename(snapshot)
        target = self._snapshot_root / filename
        self._snapshot_root.mkdir(parents=True, exist_ok=True)
        _atomic_create(target, content)
        relative = target.relative_to(self._campaign_root).as_posix()
        return SnapshotWriteReceipt(
            snapshot_path=target,
            relative_snapshot_path=relative,
            snapshot_sha256=digest,
            bytes_written=len(content),
        )

    def append_manifest(self, entry: ManifestEntry) -> None:
        if entry.campaign_id != self._campaign_id:
            raise SnapshotStorageError(reason="campaign_mismatch")
        payload = entry.to_payload()
        _validate_manifest_payload(payload)
        scan_for_secret_material(payload)
        line = (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        self._campaign_root.mkdir(parents=True, exist_ok=True)
        descriptor: int | None = None
        try:
            descriptor = os.open(
                self._manifest_path,
                os.O_APPEND
                | os.O_CREAT
                | os.O_WRONLY
                | getattr(os, "O_BINARY", 0),
                0o600,
            )
            offset = 0
            while offset < len(line):
                written = os.write(descriptor, line[offset:])
                if written <= 0:
                    raise SnapshotStorageError(reason="manifest_short_write")
                offset += written
            os.fsync(descriptor)
        except SnapshotStorageError:
            raise
        except OSError:
            raise SnapshotStorageError(reason="manifest_append_failed") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)


def manifest_entry_for_snapshot(
    *,
    snapshot: RepresentativeSnapshot,
    receipt: SnapshotWriteReceipt,
    request_count: int,
) -> ManifestEntry:
    summary = snapshot.acquisition_summary
    return ManifestEntry(
        campaign_id=snapshot.campaign_id,
        snapshot_id=snapshot.snapshot_id,
        nominal_slot_utc=snapshot.nominal_slot_utc,
        scheduled_for_utc=snapshot.scheduled_for_utc,
        observed_at_utc=snapshot.observed_at_utc,
        capture_completed_at_utc=snapshot.capture_completed_at_utc,
        input_rarity=snapshot.stratum.input_rarity,
        stattrak_mode=snapshot.stratum.stattrak_mode,
        outcome=snapshot.observation_status.value,
        reason=_snapshot_outcome_reason(snapshot),
        snapshot_path=receipt.relative_snapshot_path,
        snapshot_sha256=receipt.snapshot_sha256,
        request_count=request_count,
        pages_completed=summary.pages_completed,
        pages_failed=summary.pages_failed,
        listings_received=summary.listings_received,
    )


def verify_snapshot_hash(path: Path, expected_sha256: str) -> None:
    if type(expected_sha256) is not str or _SHA256_PATTERN.fullmatch(
        expected_sha256
    ) is None:
        raise SnapshotStorageError(reason="snapshot_hash_invalid")
    try:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise SnapshotStorageError(reason="snapshot_read_failed") from None
    if actual != expected_sha256:
        raise SnapshotStorageError(reason="snapshot_hash_mismatch")


def _snapshot_filename(snapshot: RepresentativeSnapshot) -> str:
    nominal = snapshot.nominal_slot_utc.replace("-", "").replace(":", "")
    rarity = snapshot.stratum.input_rarity.casefold().replace(" ", "-")
    mode = snapshot.stratum.stattrak_mode
    return f"snap-v1-{nominal}-{rarity}-{mode}-{snapshot.snapshot_id}.json"


def _atomic_create(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    linked = False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
            linked = True
        except FileExistsError:
            raise SnapshotStorageError(reason="snapshot_exists") from None
        except OSError:
            raise SnapshotStorageError(reason="snapshot_create_failed") from None
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            if not linked:
                raise SnapshotStorageError(reason="temporary_cleanup_failed") from None


def _validate_manifest_payload(value: object) -> None:
    if type(value) is not dict or frozenset(value) != _MANIFEST_KEYS:
        raise SnapshotStorageError(reason="manifest_schema_invalid")
    outcome = value.get("outcome")
    if outcome not in _MANIFEST_OUTCOMES:
        raise SnapshotStorageError(reason="manifest_schema_invalid")
    snapshot_path = value.get("snapshot_path")
    snapshot_hash = value.get("snapshot_sha256")
    snapshot_id = value.get("snapshot_id")
    if outcome == "MISSED_OBSERVATION":
        if any(item is not None for item in (snapshot_path, snapshot_hash, snapshot_id)):
            raise SnapshotStorageError(reason="manifest_schema_invalid")
    elif snapshot_path is None or snapshot_hash is None:
        if (
            outcome != ObservationStatus.INVALID.value
            or type(snapshot_id) is not str
            or value.get("reason")
            not in {"UNIVERSE_PLANNING_FAILED", "UNIVERSE_NOT_EXACTLY_TEN"}
        ):
            raise SnapshotStorageError(reason="manifest_schema_invalid")
    elif (
        type(snapshot_path) is not str
        or type(snapshot_hash) is not str
        or type(snapshot_id) is not str
        or _SHA256_PATTERN.fullmatch(snapshot_hash) is None
    ):
        raise SnapshotStorageError(reason="manifest_schema_invalid")
    reason = value.get("reason")
    if reason is not None and reason not in SAFE_REASONS:
        raise SnapshotStorageError(reason="manifest_schema_invalid")
    for key in (
        "request_count",
        "pages_completed",
        "pages_failed",
        "listings_received",
    ):
        item = value.get(key)
        if type(item) is not int or item < 0:
            raise SnapshotStorageError(reason="manifest_schema_invalid")
    if type(value.get("stratum")) is not dict:
        raise SnapshotStorageError(reason="manifest_schema_invalid")


def _snapshot_outcome_reason(snapshot: RepresentativeSnapshot) -> str | None:
    if snapshot.observation_status is ObservationStatus.COMPLETE:
        return None
    if snapshot.observation_status is ObservationStatus.PARTIAL:
        return "SNAPSHOT_PARTIAL"
    return "SNAPSHOT_ACQUISITION_FAILED"
