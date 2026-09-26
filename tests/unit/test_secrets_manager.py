"""
Comprehensive Unit, Security & Integration Tests for Secrets Management Subsystem (Batch 10).
"""

import threading
import pytest

from jarvis.core.exceptions import (
    ConfigurationError,
    EnvironmentSecurityError,
)
from jarvis.core.secrets.crypto import MasterKeyManager, EncryptedSecretStore
from jarvis.core.secrets.manager import SecretsManager
from jarvis.core.secrets.models import (
    SecretAccessRequest,
    SecretClassification,
    SecretOperation,
    SecretRotationRequest,
    SecretValue,
)
from jarvis.core.secrets.policy import SecretPolicyEvaluator
from jarvis.core.secrets.redaction import SecretRedactor


# ============================================================================
# 1. SECRET VALUE & MODEL TESTS
# ============================================================================


def test_secret_value_anti_leak_repr_str():
    raw_key = "TEST_SECRET_DO_NOT_EXPOSE_123"
    sec_val = SecretValue(raw_key)

    assert repr(sec_val) == "[REDACTED_SECRET_VALUE]"
    assert str(sec_val) == "[REDACTED_SECRET_VALUE]"
    assert f"{sec_val}" == "[REDACTED_SECRET_VALUE]"
    assert sec_val.get_unredacted_value() == raw_key
    assert len(sec_val.compute_fingerprint()) == 64  # SHA-256 hex string


def test_secret_value_invalid_input():
    with pytest.raises(ValueError, match="requires a string value"):
        SecretValue(12345)  # type: ignore


# ============================================================================
# 2. MASTER KEY & ENCRYPTED STORE TESTS
# ============================================================================


def test_master_key_generation_and_validation():
    key = MasterKeyManager.generate_master_key()
    assert isinstance(key, str)
    MasterKeyManager.validate_master_key(key)


def test_master_key_invalid_format():
    with pytest.raises(ConfigurationError, match="Invalid master key format"):
        MasterKeyManager.validate_master_key("not_base64_and_too_short")


def test_encrypted_secret_store_crud(tmp_path):
    key = MasterKeyManager.generate_master_key()
    store_file = tmp_path / "test_store.json"

    store = EncryptedSecretStore(master_key=key, store_path=str(store_file))

    # Set secret
    ident = "TEST_DB_PASSWORD"
    val = SecretValue("super_secret_db_pass_99")
    meta = store.set_secret(ident, val, SecretClassification.SECRET)

    assert meta.identifier == ident
    assert meta.version == 1

    # Read secret
    read_val, read_meta = store.get_secret(ident)
    assert read_val is not None
    assert read_val.get_unredacted_value() == "super_secret_db_pass_99"
    assert read_meta is not None
    assert read_meta.version == 1

    # Raw file inspection (Must NOT contain plaintext secret string)
    raw_contents = store_file.read_text(encoding="utf-8")
    assert "super_secret_db_pass_99" not in raw_contents
    assert "ciphertext" in raw_contents

    # Delete secret
    deleted = store.delete_secret(ident)
    assert deleted is True
    assert store.get_secret(ident)[0] is None


def test_encrypted_store_tamper_detection(tmp_path):
    key1 = MasterKeyManager.generate_master_key()
    key2 = MasterKeyManager.generate_master_key()
    store_file = tmp_path / "tamper_store.json"

    store1 = EncryptedSecretStore(master_key=key1, store_path=str(store_file))
    store1.set_secret("KEY", SecretValue("secret_val"))

    # Attempting to decrypt with wrong master key raises EnvironmentSecurityError
    store2 = EncryptedSecretStore(master_key=key2, store_path=str(store_file))
    with pytest.raises(EnvironmentSecurityError, match="TAMPER DETECTED / WRONG MASTER KEY"):
        store2.get_secret("KEY")


# ============================================================================
# 3. LEAST-PRIVILEGE ACCESS CONTROL POLICY TESTS
# ============================================================================


def test_policy_evaluator_authorized_access():
    evaluator = SecretPolicyEvaluator()
    req = SecretAccessRequest(
        requester="llm_router",
        secret_identifier="NVIDIA_API_KEY",
        purpose="LLM inference routing",
        requested_operation=SecretOperation.READ,
    )
    res = evaluator.evaluate(req, SecretClassification.SECRET)
    assert res.allowed is True


def test_policy_evaluator_unauthorized_access_denied():
    evaluator = SecretPolicyEvaluator()
    req = SecretAccessRequest(
        requester="telegram",
        secret_identifier="GITHUB_TOKEN",
        purpose="Unauthorized cross-component query",
        requested_operation=SecretOperation.READ,
    )
    res = evaluator.evaluate(req, SecretClassification.SECRET)
    assert res.allowed is False
    assert "not scoped to access" in res.reason


def test_policy_evaluator_critical_secret_denied_for_normal_components():
    evaluator = SecretPolicyEvaluator()
    req = SecretAccessRequest(
        requester="llm_router",
        secret_identifier="MASTER_ENCRYPTION_KEY",
        purpose="Attempt to read master key",
        requested_operation=SecretOperation.READ,
    )
    res = evaluator.evaluate(req, SecretClassification.CRITICAL_SECRET)
    assert res.allowed is False
    assert "CRITICAL_SECRET" in res.reason


# ============================================================================
# 4. REDACTION & ANTI-LEAKAGE TESTS
# ============================================================================


def test_secret_redactor_text_and_dict():
    redactor = SecretRedactor()
    raw_secret = "TEST_CONFIDENTIAL_TOKEN_9999"
    redactor.register_secret_value(raw_secret)

    # Text redaction
    sample_text = f"User logged in with token {raw_secret} and Authorization: Bearer eyJhbGciOiJIUzI1Ni..."
    clean = redactor.redact_text(sample_text)
    assert raw_secret not in clean
    assert "[REDACTED_SECRET]" in clean
    assert "Bearer [REDACTED_TOKEN]" in clean

    # Dict redaction
    data = {
        "api_key": raw_secret,
        "username": "admin",
        "nested": {"password": "my_password_123"},
    }
    clean_dict = redactor.redact_dict(data)
    assert clean_dict["api_key"] == "[REDACTED_SECRET]"
    assert clean_dict["nested"]["password"] == "[REDACTED_SECRET]"
    assert clean_dict["username"] == "admin"


# ============================================================================
# 5. ROTATION WORKFLOW & ROLLBACK TESTS
# ============================================================================


def test_secrets_manager_rotation_workflow(tmp_path):
    key = MasterKeyManager.generate_master_key()
    store_file = tmp_path / "rotation_store.json"
    mgr = SecretsManager(master_key=key, store_path=str(store_file))

    ident = "TELEGRAM_BOT_TOKEN"
    old_val = SecretValue("123456789:ABC_old_telegram_token_xyz")
    new_val = SecretValue("987654321:XYZ_new_telegram_token_abc")

    # Set initial secret
    mgr.set_secret(ident, old_val, requester="system_admin", classification=SecretClassification.SECRET)

    # Execute rotation
    rot_req = SecretRotationRequest(
        secret_identifier=ident,
        new_secret_value=new_val,
        requester="system_admin",
    )
    res = mgr.rotate_secret(rot_req)

    assert res.success is True
    assert res.old_fingerprint == old_val.compute_fingerprint()
    assert res.new_fingerprint == new_val.compute_fingerprint()

    # Verify updated secret is retrieved
    access_req = SecretAccessRequest(requester="telegram", secret_identifier=ident)
    retrieved = mgr.get_secret(access_req)
    assert retrieved.allowed is True
    assert retrieved.secret_value.get_unredacted_value() == new_val.get_unredacted_value()


def test_secrets_manager_rotation_validation_failure(tmp_path):
    key = MasterKeyManager.generate_master_key()
    store_file = tmp_path / "rot_val_store.json"
    mgr = SecretsManager(master_key=key, store_path=str(store_file))

    ident = "OPENAI_API_KEY"
    old_val = SecretValue("sk-valid_old_token_123456789")
    invalid_new_val = SecretValue("   ")  # Whitespace invalid key

    mgr.set_secret(ident, old_val, requester="system_admin")

    rot_req = SecretRotationRequest(
        secret_identifier=ident,
        new_secret_value=invalid_new_val,
        requester="system_admin",
    )
    res = mgr.rotate_secret(rot_req)
    assert res.success is False
    assert "format validation failed" in res.error


# ============================================================================
# 6. CONCURRENCY TESTS
# ============================================================================


def test_concurrent_secret_access(tmp_path):
    key = MasterKeyManager.generate_master_key()
    store_file = tmp_path / "concurrency_store.json"
    mgr = SecretsManager(master_key=key, store_path=str(store_file))

    mgr.set_secret("SHARED_KEY", SecretValue("initial_value"), requester="system_admin")

    errors = []

    def reader_thread():
        try:
            for _ in range(10):
                req = SecretAccessRequest(requester="system_admin", secret_identifier="SHARED_KEY")
                res = mgr.get_secret(req)
                assert res.allowed is True
        except Exception as e:
            errors.append(e)

    def writer_thread():
        try:
            for i in range(10):
                mgr.set_secret("SHARED_KEY", SecretValue(f"value_{i}"), requester="system_admin")
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=reader_thread),
        threading.Thread(target=writer_thread),
        threading.Thread(target=reader_thread),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0


# ============================================================================
# 7. AUTOMATED SECRET LEAK TEST
# ============================================================================


def test_secret_leak_scanner_for_logs_and_snapshots(tmp_path):
    key = MasterKeyManager.generate_master_key()
    store_file = tmp_path / "leak_test_store.json"
    mgr = SecretsManager(master_key=key, store_path=str(store_file))

    raw_test_secret = "SYNTHETIC_TEST_SECRET_VALUE_99999"
    sec_val = SecretValue(raw_test_secret)

    mgr.set_secret("TEST_TARGET_KEY", sec_val, requester="system_admin")

    # Inspect diagnostic snapshot (MUST NOT contain raw_test_secret)
    snapshot = mgr.get_diagnostics_snapshot()
    assert raw_test_secret not in snapshot

    # Inspect inventory summary (MUST NOT contain raw_test_secret)
    inv = mgr.get_sanitized_inventory()
    assert raw_test_secret not in str(inv)
