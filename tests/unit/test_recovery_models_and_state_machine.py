"""
Unit Tests for Recovery Data Models, Classification, and Exceptions (Batch 19).
"""

import time
from jarvis.core.recovery.models import (
    RecoveryStatus,
    OperationClassification,
    RecoveryRecord,
    OutboxEventRecord,
)
from jarvis.core.exceptions import (
    RecoveryError,
    RecoveryLockError,
    RecoveryIntegrityError,
    RecoveryAuthorizationError,
)


def test_recovery_status_enums():
    assert RecoveryStatus.NOT_STARTED == "NOT_STARTED"
    assert RecoveryStatus.INSPECTING == "INSPECTING"
    assert RecoveryStatus.RECOVERING == "RECOVERING"
    assert RecoveryStatus.RECONCILING == "RECONCILING"
    assert RecoveryStatus.VERIFYING == "VERIFYING"
    assert RecoveryStatus.COMPLETED == "COMPLETED"
    assert RecoveryStatus.COMPLETED_WITH_WARNINGS == "COMPLETED_WITH_WARNINGS"
    assert RecoveryStatus.FAILED == "FAILED"
    assert RecoveryStatus.BLOCKED == "BLOCKED"


def test_operation_classification_enums():
    assert OperationClassification.CONFIRMED_NOT_EXECUTED == "CONFIRMED_NOT_EXECUTED"
    assert OperationClassification.CONFIRMED_EXECUTED == "CONFIRMED_EXECUTED"
    assert OperationClassification.SAFE_TO_RETRY == "SAFE_TO_RETRY"
    assert OperationClassification.REQUIRES_RECONCILIATION == "REQUIRES_RECONCILIATION"
    assert OperationClassification.REQUIRES_MANUAL_INTERVENTION == "REQUIRES_MANUAL_INTERVENTION"
    assert OperationClassification.INVALID_OR_INCONSISTENT == "INVALID_OR_INCONSISTENT"


def test_recovery_record_defaults():
    now = time.time()
    record = RecoveryRecord()

    assert record.recovery_id.startswith("rec-")
    assert record.correlation_id.startswith("corr-")
    assert record.status == RecoveryStatus.NOT_STARTED
    assert record.started_at >= now
    assert record.completed_at is None
    assert record.inspected_count == 0
    assert record.recovered_count == 0
    assert record.details == {}


def test_outbox_event_record_defaults():
    evt = OutboxEventRecord(event_type="TestEvent", payload={"key": "value"})

    assert evt.event_id.startswith("evt-")
    assert evt.event_type == "TestEvent"
    assert evt.payload == {"key": "value"}
    assert evt.status == "PENDING"
    assert evt.attempt_count == 0
    assert evt.max_attempts == 5


def test_recovery_exceptions_hierarchy():
    err = RecoveryLockError("Lock acquisition failed")
    assert isinstance(err, RecoveryError)

    integrity_err = RecoveryIntegrityError("Integrity check failed")
    assert isinstance(integrity_err, RecoveryError)

    auth_err = RecoveryAuthorizationError("Unauthorized recovery")
    assert isinstance(auth_err, RecoveryError)
