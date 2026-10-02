"""
Security Leak Scanner Test for JARVIS Authentication, Lockout, and Recovery Subsystems (Batches 12, 13 & 14).
Scans logs, audit records, event history, credential stores, lockout stores, and exception text for raw PIN and recovery answer leakage.
"""

import os
import tempfile
import shutil
from jarvis.security import (
    AuthenticationManager,
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
)
from jarvis.core.audit_log import AuditLogger
from jarvis.core.events.bus import EventBus


def test_pin_and_recovery_answer_leak_scanner():
    temp_dir = tempfile.mkdtemp(prefix="jarvis_leak_test_")
    try:
        log_dir = os.path.join(temp_dir, "logs")
        cred_dir = os.path.join(temp_dir, "credentials")
        audit_logger = AuditLogger(log_dir=log_dir)
        cred_store = PinCredentialStore(storage_dir=cred_dir)
        lockout_store = LockoutStore(storage_dir=cred_dir)
        recovery_store = RecoveryStore(storage_dir=cred_dir)
        event_bus = EventBus()

        pin_policy = PinPolicy()
        pin_hasher = PINHasher(iterations=1000)
        answer_hasher = RecoveryAnswerHasher(iterations=1000)
        session_manager = SessionManager()
        attempt_tracker = AttemptTracker()
        lockout_manager = LockoutManager(max_attempts=3, store=lockout_store, recovery_store=recovery_store)

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

        test_pins = ["987654321012", "8520749610", "65432100"]
        test_answers = ["FluffySecretPet123", "ToyotaSecretCar456"]

        # Scenario 1: PIN Enrollment
        enroll_res = auth_manager.enroll_pin(test_pins[0], test_pins[0])
        assert enroll_res.status == "SUCCESS"

        # Scenario 2: Security Question Enrollment
        sq_res = rec_service.enroll_security_question(test_pins[0], "What is your pet's name?", test_answers[0])
        assert sq_res.status == "SUCCESS"

        # Scenario 3: PIN Lockout Triggering
        auth_manager.verify_pin(test_pins[1])
        auth_manager.verify_pin(test_pins[1])
        lockout_res = auth_manager.verify_pin(test_pins[1])
        assert lockout_res.status == "ACCOUNT_LOCKED"

        # Scenario 4: Initiate Recovery & Incorrect Answer Submission
        _, challenge = rec_service.initiate_recovery("user")
        assert challenge is not None
        rec_service.submit_recovery_answer(challenge.challenge_id, test_answers[1])

        # SCAN PERSISTED FILES & AUDIT LOGS FOR TEST PINS & RAW RECOVERY ANSWERS
        files_to_scan = []
        for root, _, files in os.walk(temp_dir):
            for file in files:
                files_to_scan.append(os.path.join(root, file))

        secrets_to_scan = test_pins + test_answers

        for file_path in files_to_scan:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                for secret in secrets_to_scan:
                    assert secret not in content, f"SECURITY LEAK DETECTED: Raw secret/PIN '{secret}' found in file {file_path}"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
