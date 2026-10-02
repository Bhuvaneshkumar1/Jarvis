"""
Comprehensive Unit & Security Test Suite for JARVIS 3-Attempt PIN Lockout (Batch 13).
"""

import os
import shutil
import tempfile
import threading
import pytest
from jarvis.security import (
    AuthenticationManager,
    AuthenticationStatus,
    PinPolicy,
    PINHasher,
    PinCredentialStore,
    SessionManager,
    AttemptTracker,
    LockoutManager,
    LockoutStore,
    LockoutRecoveryService,
)
from jarvis.core.audit_log import AuditLogger
from jarvis.core.events.bus import EventBus
from jarvis.core.exceptions import SessionRevokedError


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="jarvis_lockout_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def auth_manager(temp_dir):
    cred_store = PinCredentialStore(storage_dir=os.path.join(temp_dir, "credentials"))
    lockout_store = LockoutStore(storage_dir=os.path.join(temp_dir, "credentials"))
    audit_logger = AuditLogger(log_dir=os.path.join(temp_dir, "logs"))
    event_bus = EventBus()
    policy = PinPolicy(min_length=6, max_length=12)
    hasher = PINHasher(iterations=1000)
    session_manager = SessionManager()
    attempt_tracker = AttemptTracker()
    lockout_manager = LockoutManager(max_attempts=3, store=lockout_store)

    manager = AuthenticationManager(
        policy=policy,
        hasher=hasher,
        credential_store=cred_store,
        session_manager=session_manager,
        attempt_tracker=attempt_tracker,
        lockout_manager=lockout_manager,
        audit_logger=audit_logger,
        event_bus=event_bus,
    )
    # Enroll standard test PIN
    manager.enroll_pin("123456", "123456")
    return manager


# ============================================================================
# 1. ATTEMPT COUNTING & LOCKOUT ENFORCEMENT
# ============================================================================


def test_three_attempt_lockout_sequence(auth_manager):
    # Attempt 1: Failed
    res1 = auth_manager.verify_pin("000000")
    assert res1.status == AuthenticationStatus.INVALID_PIN
    assert res1.metadata.get("consecutive_failures") == 1

    # Attempt 2: Failed
    res2 = auth_manager.verify_pin("000000")
    assert res2.status == AuthenticationStatus.INVALID_PIN
    assert res2.metadata.get("consecutive_failures") == 2

    # Attempt 3: Failed -> Lockout Triggered!
    res3 = auth_manager.verify_pin("000000")
    assert res3.status == AuthenticationStatus.ACCOUNT_LOCKED
    assert res3.metadata.get("consecutive_failures") == 3
    assert res3.metadata.get("locked") is True

    # Attempt 4: Rejected even with correct PIN!
    res4 = auth_manager.verify_pin("123456")
    assert res4.status == AuthenticationStatus.ACCOUNT_LOCKED
    assert res4.authenticated is False


def test_successful_authentication_resets_counter(auth_manager):
    # 2 Failed attempts
    auth_manager.verify_pin("000000")
    auth_manager.verify_pin("000000")
    assert auth_manager.lockout_manager.check_lockout("user").consecutive_failures == 2

    # 1 Successful attempt -> Counter reset to 0
    res_success = auth_manager.verify_pin("123456")
    assert res_success.status == AuthenticationStatus.SUCCESS
    assert auth_manager.lockout_manager.check_lockout("user").consecutive_failures == 0

    # Next failure is 1st failure again
    res_fail = auth_manager.verify_pin("000000")
    assert res_fail.status == AuthenticationStatus.INVALID_PIN
    assert res_fail.metadata.get("consecutive_failures") == 1


def test_lockout_persists_across_restarts(auth_manager, temp_dir):
    # Trigger lockout (3 failures)
    for _ in range(3):
        auth_manager.verify_pin("000000")

    assert auth_manager.lockout_manager.check_lockout("user").locked is True

    # Simulate application restart: recreate new AuthenticationManager over same storage directory
    cred_store = PinCredentialStore(storage_dir=os.path.join(temp_dir, "credentials"))
    lockout_store = LockoutStore(storage_dir=os.path.join(temp_dir, "credentials"))
    new_manager = AuthenticationManager(
        policy=PinPolicy(),
        hasher=PINHasher(iterations=1000),
        credential_store=cred_store,
        lockout_manager=LockoutManager(max_attempts=3, store=lockout_store),
    )

    # Verification must be blocked immediately on restarted system
    res = new_manager.verify_pin("123456")
    assert res.status == AuthenticationStatus.ACCOUNT_LOCKED


# ============================================================================
# 2. SESSION REVOCATION ON LOCKOUT
# ============================================================================


def test_session_revocation_on_lockout(auth_manager):
    # Authenticate and obtain active session
    login_res = auth_manager.verify_pin("123456")
    session_id = login_res.session_id
    assert auth_manager.validate_session(session_id) is not None

    # Trigger 3 failures
    for _ in range(3):
        auth_manager.verify_pin("000000")

    # Session must be revoked
    with pytest.raises(SessionRevokedError):
        auth_manager.validate_session(session_id)


# ============================================================================
# 3. CORRUPTED LOCKOUT STATE HANDLING
# ============================================================================


def test_corrupted_lockout_file_fails_closed(auth_manager):
    lockout_path = auth_manager.lockout_manager.store._get_lockout_path("user")

    # Overwrite file with invalid json
    with open(lockout_path, "w", encoding="utf-8") as f:
        f.write("{corrupted_lockout: true")

    res = auth_manager.verify_pin("123456")
    assert res.status == AuthenticationStatus.CREDENTIAL_CORRUPTED


# ============================================================================
# 4. CONCURRENCY TESTS
# ============================================================================


def test_concurrent_failed_attempts(auth_manager):
    errors = []

    def worker():
        try:
            auth_manager.verify_pin("000000")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    # Final state must be locked
    lockout = auth_manager.lockout_manager.check_lockout("user")
    assert lockout.locked is True
    assert lockout.consecutive_failures >= 3


# ============================================================================
# 5. LOCKOUT RECOVERY SERVICE INTERFACE STUB
# ============================================================================


def test_lockout_recovery_service_interface():
    svc = LockoutRecoveryService()
    req = svc.request_recovery("user")
    assert req["supported"] is False

    assert svc.validate_recovery_context("user") is False

    with pytest.raises(NotImplementedError):
        svc.complete_recovery("user")
