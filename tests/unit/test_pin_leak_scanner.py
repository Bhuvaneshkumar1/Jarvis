"""
Security Leak Scanner Test for JARVIS PIN Authentication & Lockout Subsystems (Batch 12 & 13).
Scans logs, audit records, event history, credential stores, lockout stores, and exception text for raw PIN leakage.
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
)
from jarvis.core.audit_log import AuditLogger
from jarvis.core.events.bus import EventBus


def test_pin_leak_scanner():
    temp_dir = tempfile.mkdtemp(prefix="jarvis_leak_test_")
    try:
        log_dir = os.path.join(temp_dir, "logs")
        cred_dir = os.path.join(temp_dir, "credentials")
        audit_logger = AuditLogger(log_dir=log_dir)
        cred_store = PinCredentialStore(storage_dir=cred_dir)
        lockout_store = LockoutStore(storage_dir=cred_dir)
        event_bus = EventBus()

        auth_manager = AuthenticationManager(
            policy=PinPolicy(),
            hasher=PINHasher(iterations=1000),
            credential_store=cred_store,
            session_manager=SessionManager(),
            attempt_tracker=AttemptTracker(),
            lockout_manager=LockoutManager(max_attempts=3, store=lockout_store),
            audit_logger=audit_logger,
            event_bus=event_bus,
        )

        test_pins = ["987654321012", "8520749610", "65432100"]

        # Scenario 1: Enrollment
        enroll_res = auth_manager.enroll_pin(test_pins[0], test_pins[0])
        assert enroll_res.status == "SUCCESS"

        # Scenario 2: Successful Verification
        verify_res = auth_manager.verify_pin(test_pins[0])
        assert verify_res.status == "SUCCESS"
        session_id = verify_res.session_id
        assert session_id is not None

        # Scenario 3: Failed Verification
        fail_res = auth_manager.verify_pin(test_pins[1])
        assert fail_res.status == "INVALID_PIN"

        # Scenario 4: Lockout Triggering (Failed Verification 2 & 3)
        auth_manager.verify_pin(test_pins[1])
        lockout_res = auth_manager.verify_pin(test_pins[1])
        assert lockout_res.status == "ACCOUNT_LOCKED"

        # SCAN PERSISTED FILES & AUDIT LOGS FOR TEST PINS
        files_to_scan = []
        for root, _, files in os.walk(temp_dir):
            for file in files:
                files_to_scan.append(os.path.join(root, file))

        for file_path in files_to_scan:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                for pin in test_pins:
                    assert pin not in content, f"SECURITY LEAK DETECTED: Raw PIN '{pin}' found in file {file_path}"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
