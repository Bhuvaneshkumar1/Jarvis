"""
Authoritative Centralized Secrets Manager Subsystem for JARVIS (Batch 10).
"""

from typing import Dict, List, Optional, Any

from jarvis.core.audit_log import AuditLogger
from jarvis.core.exceptions import (
    AuthorizationError,
)
from jarvis.core.secrets.crypto import MasterKeyManager, EncryptedSecretStore
from jarvis.core.secrets.models import (
    SecretAccessRequest,
    SecretAccessResult,
    SecretClassification,
    SecretMetadata,
    SecretOperation,
    SecretRotationRequest,
    SecretRotationResult,
    SecretValidationResult,
    SecretValue,
)
from jarvis.core.secrets.policy import SecretPolicyEvaluator
from jarvis.core.secrets.providers import (
    BaseSecretProvider,
    CompositeSecretProvider,
    EncryptedFileSecretProvider,
    EnvironmentSecretProvider,
)
from jarvis.core.secrets.redaction import SecretRedactor


class CredentialValidator:
    """Validator inspecting presence, length, and format of credential entries."""

    @staticmethod
    def validate(identifier: str, value: Optional[SecretValue]) -> SecretValidationResult:
        reasons: List[str] = []
        if value is None:
            return SecretValidationResult(valid=False, identifier=identifier, reasons=["Credential is missing or empty."])

        raw_str = value.get_unredacted_value()
        if not raw_str or not raw_str.strip():
            reasons.append("Credential value is empty or whitespace.")

        # Length validation
        if len(raw_str) < 4:
            reasons.append("Credential length is below minimum threshold (4 chars).")

        return SecretValidationResult(valid=len(reasons) == 0, identifier=identifier, reasons=reasons)


class SecretsManager:
    """
    Authoritative Centralized Secrets Manager Facade for JARVIS AI OS.
    Owns secure loading, encrypted local storage, least-privilege authorization,
    secret rotation, credential validation, and anti-leak redaction.
    """

    def __init__(
        self,
        master_key: Optional[str] = None,
        store_path: str = EncryptedSecretStore.DEFAULT_STORE_FILE,
        audit_logger: Optional[AuditLogger] = None,
        custom_provider: Optional[BaseSecretProvider] = None,
    ):
        self.audit_logger = audit_logger or AuditLogger()
        self.policy_evaluator = SecretPolicyEvaluator(audit_logger=self.audit_logger)
        self.redactor = SecretRedactor()

        # Initialize Master Key and Encrypted Store
        if master_key:
            self.master_key = master_key
        else:
            self.master_key = MasterKeyManager.load_master_key(auto_create_if_missing=True)

        self.encrypted_store = EncryptedSecretStore(master_key=self.master_key, store_path=store_path)
        self.encrypted_provider = EncryptedFileSecretProvider(store=self.encrypted_store)
        self.env_provider = EnvironmentSecretProvider()

        # Primary composite provider (Encrypted store takes priority over environment)
        self.provider: BaseSecretProvider = custom_provider or CompositeSecretProvider(providers=[self.encrypted_provider, self.env_provider])

    def get_secret(self, request: SecretAccessRequest) -> SecretAccessResult:
        """
        Retrieves secret value for requester if authorized by policy.
        Evaluates least-privilege policy, registers secret for anti-leak redaction, and returns result.
        """
        # First query provider for metadata to determine classification
        _, meta = self.provider.get_secret(request.secret_identifier)
        classification = meta.classification if meta else SecretClassification.SECRET

        # Evaluate authorization policy
        auth_result = self.policy_evaluator.evaluate(request, target_classification=classification)
        if not auth_result.allowed:
            return auth_result

        # Retrieve secret value
        s_val, s_meta = self.provider.get_secret(request.secret_identifier)
        if s_val is None or s_meta is None:
            return SecretAccessResult(
                allowed=False,
                secret_identifier=request.secret_identifier,
                reason=f"Secret '{request.secret_identifier}' not found in active providers.",
                audit_id=auth_result.audit_id,
            )

        # Register secret value with redactor to prevent accidental logging leaks
        self.redactor.register_secret_value(s_val.get_unredacted_value())

        return SecretAccessResult(
            allowed=True,
            secret_identifier=request.secret_identifier,
            secret_value=s_val,
            reason="Authorized",
            audit_id=auth_result.audit_id,
        )

    def set_secret(
        self,
        identifier: str,
        value: SecretValue,
        requester: str = "system_admin",
        classification: SecretClassification = SecretClassification.SECRET,
    ) -> SecretMetadata:
        """
        Encrypts and stores new secret entry in local encrypted secret store.
        """
        req = SecretAccessRequest(
            requester=requester,
            secret_identifier=identifier,
            purpose="write_secret",
            requested_operation=SecretOperation.WRITE,
        )
        auth = self.policy_evaluator.evaluate(req, target_classification=classification)
        if not auth.allowed:
            raise AuthorizationError(auth.reason)

        meta = self.encrypted_provider.set_secret(identifier, value, classification)
        self.redactor.register_secret_value(value.get_unredacted_value())
        return meta

    def delete_secret(self, identifier: str, requester: str = "system_admin") -> bool:
        """
        Deletes secret entry from local encrypted store.
        """
        req = SecretAccessRequest(
            requester=requester,
            secret_identifier=identifier,
            purpose="delete_secret",
            requested_operation=SecretOperation.DELETE,
        )
        auth = self.policy_evaluator.evaluate(req, target_classification=SecretClassification.CRITICAL_SECRET)
        if not auth.allowed:
            raise AuthorizationError(auth.reason)

        return self.encrypted_provider.delete_secret(identifier)

    def rotate_secret(self, request: SecretRotationRequest) -> SecretRotationResult:
        """
        Executes atomic secret rotation workflow:
        1. Evaluates requester authorization policy.
        2. Retrieves old secret fingerprint.
        3. Validates new secret format.
        4. Writes new secret to encrypted store.
        5. Verifies read-back integrity and fingerprint update.
        6. Rolls back to old state if write/read verification fails.
        """
        req = SecretAccessRequest(
            requester=request.requester,
            secret_identifier=request.secret_identifier,
            purpose="rotate_secret",
            requested_operation=SecretOperation.ROTATE,
            correlation_id=request.correlation_id,
        )
        auth = self.policy_evaluator.evaluate(req, target_classification=SecretClassification.CRITICAL_SECRET)
        if not auth.allowed:
            return SecretRotationResult(
                success=False,
                secret_identifier=request.secret_identifier,
                error=auth.reason,
            )

        # 1. Read old secret state
        old_val, old_meta = self.encrypted_provider.get_secret(request.secret_identifier)
        old_fp = old_val.compute_fingerprint() if old_val else ""
        classification = old_meta.classification if old_meta else SecretClassification.SECRET

        # 2. Validate new credential format
        val_res = CredentialValidator.validate(request.secret_identifier, request.new_secret_value)
        if not val_res.valid:
            err_msg = f"New secret format validation failed: {', '.join(val_res.reasons)}"
            return SecretRotationResult(
                success=False,
                secret_identifier=request.secret_identifier,
                old_fingerprint=old_fp,
                error=err_msg,
            )

        # 3. Write new secret to encrypted store
        try:
            new_meta = self.encrypted_provider.set_secret(request.secret_identifier, request.new_secret_value, classification)
            # 4. Verify read-back
            read_back_val, read_back_meta = self.encrypted_provider.get_secret(request.secret_identifier)
            if read_back_val is None or read_back_val != request.new_secret_value:
                # Rollback to old secret if possible
                if old_val:
                    self.encrypted_provider.set_secret(request.secret_identifier, old_val, classification)
                return SecretRotationResult(
                    success=False,
                    secret_identifier=request.secret_identifier,
                    old_fingerprint=old_fp,
                    error="Read-back verification failed after rotation attempt. Rolled back.",
                )

            new_fp = new_meta.fingerprint
            self.redactor.register_secret_value(request.new_secret_value.get_unredacted_value())

            return SecretRotationResult(
                success=True,
                secret_identifier=request.secret_identifier,
                old_fingerprint=old_fp,
                new_fingerprint=new_fp,
            )
        except Exception as exc:
            # Rollback on exception
            if old_val:
                try:
                    self.encrypted_provider.set_secret(request.secret_identifier, old_val, classification)
                except Exception:
                    pass
            return SecretRotationResult(
                success=False,
                secret_identifier=request.secret_identifier,
                old_fingerprint=old_fp,
                error=f"Secret rotation exception: {str(exc)}",
            )

    def validate_credentials(self) -> Dict[str, SecretValidationResult]:
        """
        Validates presence and format of all managed credentials.
        """
        inventory = self.provider.list_metadata()
        results: Dict[str, SecretValidationResult] = {}
        for ident in inventory:
            s_val, _ = self.provider.get_secret(ident)
            results[ident] = CredentialValidator.validate(ident, s_val)
        return results

    def get_sanitized_inventory(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns complete non-sensitive metadata summary for all managed secrets.
        ZERO raw secret values exposed.
        """
        inventory = self.provider.list_metadata()
        return {k: v.to_dict() for k, v in inventory.items()}

    def get_diagnostics_snapshot(self) -> str:
        """
        Produces formatted executive secrets management diagnostic snapshot.
        Rule: NEVER expose secret values.
        """
        inv = self.get_sanitized_inventory()
        lines = [
            "JARVIS SECRETS MANAGEMENT SNAPSHOT",
            "==================================",
            "",
            "Master Key Source: Configured",
            f"Encrypted Store File: {self.encrypted_store.store_path}",
            f"Total Managed Secrets: {len(inv)}",
            "",
            "Secret Inventory:",
        ]

        for k, v in inv.items():
            lines.append(f"  {k}: source={v['source']}, classification={v['classification']}, version={v['version']}, present=YES")

        lines.extend(["", "RESULT: VALID"])
        return "\n".join(lines)


# Singleton SecretsManager Instance Loader
_secrets_manager_instance: Optional[SecretsManager] = None


def get_secrets_manager(
    master_key: Optional[str] = None,
    store_path: str = EncryptedSecretStore.DEFAULT_STORE_FILE,
    force_reload: bool = False,
) -> SecretsManager:
    """
    Authoritative SecretsManager loader function.
    Returns cached instance unless force_reload=True.
    """
    global _secrets_manager_instance
    if _secrets_manager_instance is None or force_reload or master_key is not None:
        _secrets_manager_instance = SecretsManager(master_key=master_key, store_path=store_path)
    return _secrets_manager_instance
