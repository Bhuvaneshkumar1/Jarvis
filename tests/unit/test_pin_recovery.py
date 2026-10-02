"""
Comprehensive Unit, Integration, and Time-Based Test Suite for Security Question Recovery & 1-Hour Lockout (Batch 14).
"""

import os
import shutil
import tempfile
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
    RecoveryService,
    RecoveryStore,
    RecoveryAnswerHasher,
    normalize_answer,
)
from jarvis.core.audit_log import AuditLogger
from jarvis.core.events.bus import EventBus


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="jarvis_recovery_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def recovery_env(temp_dir):
    fake_time = 1000.0

    def clock():
        return fake_time

    cred_dir = os.path.join(temp_dir, "credentials")
    log_dir = os.path.join(temp_dir, "logs")

    cred_store = PinCredentialStore(storage_dir=cred_dir)
    lockout_store = LockoutStore(storage_dir=cred_dir)
    recovery_store = RecoveryStore(storage_dir=cred_dir)
    audit_logger = AuditLogger(log_dir=log_dir)
    event_bus = EventBus()

    pin_policy = PinPolicy(min_length=6, max_length=12)
    pin_hasher = PINHasher(iterations=1000)
    answer_hasher = RecoveryAnswerHasher(iterations=1000)
    session_manager = SessionManager(clock_fn=clock)
    attempt_tracker = AttemptTracker(clock_fn=clock)

    lockout_manager = LockoutManager(max_attempts=3, store=lockout_store, recovery_store=recovery_store, clock_fn=clock)

    rec_service = RecoveryService(
        recovery_store=recovery_store,
        answer_hasher=answer_hasher,
        pin_hasher=pin_hasher,
        pin_policy=pin_policy,
        credential_store=cred_store,
        session_manager=session_manager,
        lockout_manager=lockout_manager,
        audit_logger=audit_logger,
        event_bus=event_bus,
        clock_fn=clock,
    )

    auth_manager = AuthenticationManager(
        policy=pin_policy,
        hasher=pin_hasher,
        credential_store=cred_store,
        session_manager=session_manager,
        attempt_tracker=attempt_tracker,
        lockout_manager=lockout_manager,
        recovery_service=rec_service,
        audit_logger=audit_logger,
        event_bus=event_bus,
    )

    auth_manager.enroll_pin("123456", "123456")

    class Env:
        def advance_time(self, seconds: float):
            nonlocal fake_time
            fake_time += seconds

    env = Env()
    env.time = lambda: fake_time
    env.rec_service = rec_service
    env.auth_manager = auth_manager
    env.recovery_store = recovery_store
    env.temp_dir = temp_dir
    return env


# ============================================================================
# 1. NORMALIZATION & CRYPTO PRIMITIVE TESTS
# ============================================================================


def test_answer_normalization():
    # Whitespace stripping, internal whitespace collapsing, casefolding, NFKC
    raw1 = "   My   First  Dog  "
    raw2 = "my first dog"
    assert normalize_answer(raw1) == normalize_answer(raw2)
    assert normalize_answer(raw1) == "my first dog"

    with pytest.raises(ValueError, match="non-null string"):
        normalize_answer(None)  # type: ignore

    with pytest.raises(ValueError, match="empty or whitespace-only"):
        normalize_answer("   ")


def test_answer_hasher():
    hasher = RecoveryAnswerHasher(iterations=1000)
    salt1, v1, p1 = hasher.derive_answer_verifier("Fluffy")
    salt2, v2, p2 = hasher.derive_answer_verifier("Fluffy")

    assert salt1 != salt2
    assert v1 != v2
    assert hasher.verify_answer("fluffy ", salt1, v1, p1) is True
    assert hasher.verify_answer("wrong", salt1, v1, p1) is False


# ============================================================================
# 2. ENROLLMENT & UPDATE TESTS
# ============================================================================


def test_security_question_enrollment(recovery_env):
    rec_svc = recovery_env.rec_service

    # Fail with wrong PIN
    res_bad = rec_svc.enroll_security_question("999999", "What is your pet's name?", "Fluffy")
    assert res_bad.status == AuthenticationStatus.INVALID_PIN

    # Succeed with correct PIN
    res_good = rec_svc.enroll_security_question("123456", "What is your pet's name?", "Fluffy")
    assert res_good.status == AuthenticationStatus.SUCCESS
    assert recovery_env.recovery_store.has_question_credential("user") is True

    # Duplicate enrollment rejected
    res_dup = rec_svc.enroll_security_question("123456", "What is your pet's name?", "Fluffy")
    assert res_dup.safe_error_code == "ALREADY_ENROLLED"


def test_security_question_update(recovery_env):
    rec_svc = recovery_env.rec_service
    rec_svc.enroll_security_question("123456", "Original Question?", "Answer1")

    res_update = rec_svc.update_security_question("123456", "New Question?", "Answer2")
    assert res_update.status == AuthenticationStatus.SUCCESS

    cred = recovery_env.recovery_store.load_question_credential("user")
    assert cred.question_text == "New Question?"
    assert rec_svc.answer_hasher.verify_answer("answer2", cred.salt, cred.answer_verifier, cred.parameters) is True


# ============================================================================
# 3. RECOVERY FLOW & 1-HOUR LOCKOUT TESTS
# ============================================================================


def test_recovery_flow_success_path(recovery_env):
    auth_mgr = recovery_env.auth_manager
    rec_svc = recovery_env.rec_service

    # 1. Enroll Security Question
    rec_svc.enroll_security_question("123456", "What is your childhood street?", "Elm Street")

    # 2. Trigger 3-attempt PIN lockout
    for _ in range(3):
        auth_mgr.verify_pin("000000")
    assert auth_mgr.lockout_manager.check_lockout("user").locked is True

    # 3. Initiate Recovery Challenge
    res_init, challenge = rec_svc.initiate_recovery("user")
    assert res_init.status == AuthenticationStatus.SUCCESS
    assert challenge is not None
    assert challenge.question_text == "What is your childhood street?"

    # 4. Submit Correct Answer
    res_ans = rec_svc.submit_recovery_answer(challenge.challenge_id, " elm street ")
    assert res_ans.status == AuthenticationStatus.SUCCESS
    assert res_ans.metadata.get("state") == "PIN_RESET_REQUIRED"

    # 5. Complete PIN Reset
    res_reset = rec_svc.complete_pin_reset(challenge.challenge_id, "654321", "654321")
    assert res_reset.status == AuthenticationStatus.SUCCESS

    # 6. Verify authentication works with NEW PIN
    res_login = auth_mgr.verify_pin("654321")
    assert res_login.status == AuthenticationStatus.SUCCESS
    assert res_login.authenticated is True


def test_incorrect_recovery_answer_triggers_one_hour_lockout(recovery_env):
    auth_mgr = recovery_env.auth_manager
    rec_svc = recovery_env.rec_service

    rec_svc.enroll_security_question("123456", "First car?", "Toyota")

    # Lock PIN (3 failures)
    for _ in range(3):
        auth_mgr.verify_pin("000000")

    # Initiate Recovery
    _, challenge = rec_svc.initiate_recovery("user")

    # Submit INCORRECT answer -> Triggers 1-Hour Lockout
    res_bad = rec_svc.submit_recovery_answer(challenge.challenge_id, "Honda")
    assert res_bad.status == AuthenticationStatus.ACCOUNT_LOCKED
    assert res_bad.safe_error_code == "RECOVERY_LOCKED"
    assert res_bad.metadata.get("locked") is True

    # Verify 1-Hour Lockout Persistence across authentication attempts
    res_blocked = auth_mgr.verify_pin("123456")
    assert res_blocked.status == AuthenticationStatus.ACCOUNT_LOCKED

    # Advance time by 3599 seconds (59 min 59 sec) -> STAYS LOCKED
    recovery_env.advance_time(3599.0)
    assert auth_mgr.verify_pin("123456").status == AuthenticationStatus.ACCOUNT_LOCKED

    # Advance 2 more seconds (60 min 01 sec) -> Lockout Expiration!
    recovery_env.advance_time(2.0)
    is_rec_locked, _ = rec_svc.check_recovery_lockout("user")
    assert is_rec_locked is False


def test_challenge_single_use_replay_prevention(recovery_env):
    rec_svc = recovery_env.rec_service
    rec_svc.enroll_security_question("123456", "City?", "Paris")

    recovery_env.auth_manager.verify_pin("000000")
    recovery_env.auth_manager.verify_pin("000000")
    recovery_env.auth_manager.verify_pin("000000")

    _, challenge = rec_svc.initiate_recovery("user")

    # Consume challenge once
    rec_svc.submit_recovery_answer(challenge.challenge_id, "Paris")

    # Attempt replay of same challenge -> REJECTED
    res_replay = rec_svc.submit_recovery_answer(challenge.challenge_id, "Paris")
    assert res_replay.status == AuthenticationStatus.INVALID_INPUT
    assert res_replay.safe_error_code == "INVALID_CHALLENGE"


def test_unenrolled_question_fails_closed(recovery_env):
    auth_mgr = recovery_env.auth_manager
    rec_svc = recovery_env.rec_service

    # Lock PIN
    for _ in range(3):
        auth_mgr.verify_pin("000000")

    # Initiate recovery without enrolled question -> FAILS CLOSED
    res_init, challenge = rec_svc.initiate_recovery("user")
    assert res_init.status == AuthenticationStatus.NOT_ENROLLED
    assert challenge is None
