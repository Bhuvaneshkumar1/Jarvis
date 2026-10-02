"""
Comprehensive Unit & Security Test Suite for JARVIS PIN Authentication (Batch 12).
"""

import os
import shutil
import tempfile
import pytest
from jarvis.security.contracts import (
    AuthenticationStatus,
)
from jarvis.security.pin_policy import PinPolicy
from jarvis.security.pin_crypto import PINHasher
from jarvis.security.credential_store import PinCredentialStore
from jarvis.security.session_manager import SessionManager
from jarvis.security.rate_limit import AttemptTracker
from jarvis.security.auth_manager import AuthenticationManager
from jarvis.core.events.bus import EventBus
from jarvis.core.audit_log import AuditLogger
from jarvis.core.exceptions import (
    PinPolicyValidationError,
    SessionExpiredError,
    SessionRevokedError,
)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="jarvis_auth_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def auth_manager(temp_dir):
    cred_store = PinCredentialStore(storage_dir=os.path.join(temp_dir, "credentials"))
    audit_logger = AuditLogger(log_dir=os.path.join(temp_dir, "logs"))
    event_bus = EventBus()
    policy = PinPolicy(min_length=6, max_length=12)
    hasher = PINHasher(iterations=1000)  # Faster iterations for unit test fixture
    session_manager = SessionManager(default_ttl_seconds=3600.0, inactivity_timeout_seconds=300.0)
    attempt_tracker = AttemptTracker()

    return AuthenticationManager(
        policy=policy,
        hasher=hasher,
        credential_store=cred_store,
        session_manager=session_manager,
        attempt_tracker=attempt_tracker,
        audit_logger=audit_logger,
        event_bus=event_bus,
    )


# ============================================================================
# 1. ENROLLMENT TESTS
# ============================================================================


def test_enrollment_valid(auth_manager):
    res = auth_manager.enroll_pin("123456", "123456")
    assert res.status == AuthenticationStatus.SUCCESS
    assert res.authenticated is False
    assert auth_manager.is_enrolled("user") is True


def test_enrollment_leading_zeroes_preserved(auth_manager):
    res = auth_manager.enroll_pin("001234", "001234")
    assert res.status == AuthenticationStatus.SUCCESS
    # Verify candidate with leading zero succeeds, but without fails
    verify_res = auth_manager.verify_pin("001234")
    assert verify_res.status == AuthenticationStatus.SUCCESS
    assert verify_res.authenticated is True

    auth_manager.session_manager.clear()
    verify_fail = auth_manager.verify_pin("1234")
    assert verify_fail.status == AuthenticationStatus.INVALID_PIN


def test_enrollment_policy_boundary_lengths(auth_manager):
    # Minimum length (6)
    res_min = auth_manager.enroll_pin("123456", "123456")
    assert res_min.status == AuthenticationStatus.SUCCESS

    # Clean up for max length test
    auth_manager.credential_store.delete_credential("user")

    # Maximum length (12)
    res_max = auth_manager.enroll_pin("123456789012", "123456789012")
    assert res_max.status == AuthenticationStatus.SUCCESS


def test_enrollment_policy_violations(auth_manager):
    policy = PinPolicy(min_length=6, max_length=12)

    # Too short (<6)
    with pytest.raises(PinPolicyValidationError, match="less than minimum"):
        policy.validate_pin("12345")

    # Too long (>12)
    with pytest.raises(PinPolicyValidationError, match="exceeds maximum"):
        policy.validate_pin("1234567890123")

    # Alphabetic
    with pytest.raises(PinPolicyValidationError, match="numeric digits"):
        policy.validate_pin("12345a")

    # Whitespace inside
    with pytest.raises(PinPolicyValidationError, match="whitespace"):
        policy.validate_pin("123 56")

    # Non-ASCII digits (e.g. Arabic/Devanagari digits)
    with pytest.raises(PinPolicyValidationError, match="numeric digits"):
        policy.validate_pin("12345६")

    # Mismatched confirmation
    with pytest.raises(PinPolicyValidationError, match="confirmation does not match"):
        policy.validate_pin_confirmation("123456", "654321")


def test_enrollment_duplicate_rejection(auth_manager):
    res1 = auth_manager.enroll_pin("123456", "123456")
    assert res1.status == AuthenticationStatus.SUCCESS

    res2 = auth_manager.enroll_pin("654321", "654321")
    assert res2.status == AuthenticationStatus.INVALID_INPUT
    assert res2.safe_error_code == "ALREADY_ENROLLED"


# ============================================================================
# 2. VERIFICATION TESTS
# ============================================================================


def test_verification_correct_pin(auth_manager):
    auth_manager.enroll_pin("987654", "987654")
    res = auth_manager.verify_pin("987654")
    assert res.status == AuthenticationStatus.SUCCESS
    assert res.authenticated is True
    assert res.session_id is not None
    assert res.session_id.startswith("sess_")


def test_verification_incorrect_pin(auth_manager):
    auth_manager.enroll_pin("987654", "987654")
    res = auth_manager.verify_pin("111111")
    assert res.status == AuthenticationStatus.INVALID_PIN
    assert res.authenticated is False
    assert res.session_id is None
    assert auth_manager.attempt_tracker.get_failed_attempts("user") == 1


def test_verification_unenrolled(auth_manager):
    res = auth_manager.verify_pin("123456")
    assert res.status == AuthenticationStatus.NOT_ENROLLED
    assert res.authenticated is False


def test_verification_corrupted_credential(auth_manager):
    auth_manager.enroll_pin("987654", "987654")
    cred_path = auth_manager.credential_store._get_credential_path("user")

    # Overwrite file with invalid json
    with open(cred_path, "w", encoding="utf-8") as f:
        f.write("{corrupted_json: true")

    res = auth_manager.verify_pin("987654")
    assert res.status == AuthenticationStatus.CREDENTIAL_CORRUPTED
    assert res.authenticated is False


# ============================================================================
# 3. PIN CHANGE TESTS
# ============================================================================


def test_pin_change_valid(auth_manager):
    auth_manager.enroll_pin("123456", "123456")
    login_res = auth_manager.verify_pin("123456")
    session_id = login_res.session_id

    change_res = auth_manager.change_pin("123456", "654321", "654321", session_id=session_id)
    assert change_res.status == AuthenticationStatus.SUCCESS

    # Verify old PIN no longer works
    old_verify = auth_manager.verify_pin("123456")
    assert old_verify.status == AuthenticationStatus.INVALID_PIN

    # Verify new PIN works
    new_verify = auth_manager.verify_pin("654321")
    assert new_verify.status == AuthenticationStatus.SUCCESS


def test_pin_change_incorrect_current_pin(auth_manager):
    auth_manager.enroll_pin("123456", "123456")
    res = auth_manager.change_pin("999999", "654321", "654321")
    assert res.status == AuthenticationStatus.INVALID_PIN
    assert res.safe_error_code == "INVALID_CURRENT_PIN"


def test_pin_change_same_pin_prohibited(auth_manager):
    auth_manager.enroll_pin("123456", "123456")
    res = auth_manager.change_pin("123456", "123456", "123456")
    assert res.status == AuthenticationStatus.INVALID_INPUT
    assert res.safe_error_code == "SAME_PIN_PROHIBITED"


# ============================================================================
# 4. SESSION TESTS
# ============================================================================


def test_session_lifecycle_and_expiration():
    fake_time = 1000.0

    def clock():
        return fake_time

    sm = SessionManager(default_ttl_seconds=3600.0, inactivity_timeout_seconds=300.0, clock_fn=clock)

    session = sm.create_session("user")
    assert session.is_active(now=fake_time) is True

    # Advance 200s (below 300s inactivity)
    fake_time = 1200.0
    validated = sm.validate_session(session.session_id)
    assert validated is not None
    assert validated.last_activity_at == 1200.0

    # Advance 350s from last activity (1200 + 350 = 1550) -> Inactivity Expiration
    fake_time = 1550.0
    with pytest.raises(SessionExpiredError):
        sm.validate_session(session.session_id)


def test_session_absolute_ttl_expiration():
    fake_time = 1000.0

    def clock():
        return fake_time

    sm = SessionManager(default_ttl_seconds=3600.0, inactivity_timeout_seconds=3000.0, clock_fn=clock)
    session = sm.create_session("user")

    # Advance beyond 3600s
    fake_time = 4601.0
    with pytest.raises(SessionExpiredError):
        sm.validate_session(session.session_id)


def test_session_explicit_revocation(auth_manager):
    auth_manager.enroll_pin("123456", "123456")
    login_res = auth_manager.verify_pin("123456")
    session_id = login_res.session_id

    rev_res = auth_manager.revoke_session(session_id)
    assert rev_res is True

    with pytest.raises(SessionRevokedError):
        auth_manager.validate_session(session_id)


def test_session_restart_behavior(auth_manager):
    auth_manager.enroll_pin("123456", "123456")
    login_res = auth_manager.verify_pin("123456")
    session_id = login_res.session_id

    # Simulate application restart (in-memory clearing)
    auth_manager.session_manager.clear()

    # Session is invalidated
    val_res = auth_manager.validate_session(session_id)
    assert val_res is None


# ============================================================================
# 5. CRYPTOGRAPHIC PRIMITIVE TESTS
# ============================================================================


def test_crypto_hasher_salt_randomness():
    hasher = PINHasher(iterations=1000)
    salt1, v1, p1 = hasher.derive_verifier("123456")
    salt2, v2, p2 = hasher.derive_verifier("123456")

    assert salt1 != salt2
    assert v1 != v2
    assert hasher.verify_pin("123456", salt1, v1, p1) is True
    assert hasher.verify_pin("123456", salt2, v2, p2) is True
