"""
Secret Provider Architecture & Implementations for JARVIS (Batch 10).
"""

import abc
import os
from typing import Dict, List, Optional, Tuple

from config.env_security import ENV_REGISTRY, is_secret_variable
from jarvis.core.secrets.crypto import EncryptedSecretStore
from jarvis.core.secrets.models import (
    SecretClassification,
    SecretMetadata,
    SecretSource,
    SecretValue,
)


class BaseSecretProvider(abc.ABC):
    """Abstract base provider for credential retrieval and storage."""

    @property
    @abc.abstractmethod
    def source(self) -> SecretSource:
        """Provider source classification."""
        pass

    @abc.abstractmethod
    def get_secret(self, identifier: str) -> Tuple[Optional[SecretValue], Optional[SecretMetadata]]:
        """Retrieves secret value and metadata for identifier if present."""
        pass

    @abc.abstractmethod
    def list_metadata(self) -> Dict[str, SecretMetadata]:
        """Lists metadata snapshots for all secrets owned by this provider."""
        pass

    def has_secret(self, identifier: str) -> bool:
        """Checks if identifier exists in provider."""
        _, meta = self.get_secret(identifier)
        return meta is not None and meta.present


class EnvironmentSecretProvider(BaseSecretProvider):
    """
    Secret provider loading credentials directly from environment variables / .env.
    Integrates with Batch 9 environment registry and secret classification.
    """

    @property
    def source(self) -> SecretSource:
        return SecretSource.ENVIRONMENT

    def get_secret(self, identifier: str) -> Tuple[Optional[SecretValue], Optional[SecretMetadata]]:
        raw_val = os.environ.get(identifier)
        if raw_val is None:
            return None, None

        # Determine classification from registry or pattern detector
        reg_def = ENV_REGISTRY.get(identifier)
        if reg_def:
            cls_enum = SecretClassification(reg_def.classification.value)
        elif is_secret_variable(identifier):
            cls_enum = SecretClassification.SECRET
        else:
            cls_enum = SecretClassification.INTERNAL

        s_val = SecretValue(raw_val)
        meta = SecretMetadata(
            identifier=identifier,
            classification=cls_enum,
            source=self.source,
            present=True,
            valid_format=True,
            fingerprint=s_val.compute_fingerprint(),
            version=1,
        )
        return s_val, meta

    def list_metadata(self) -> Dict[str, SecretMetadata]:
        results: Dict[str, SecretMetadata] = {}

        # Scan environment for registered or detected secrets
        for k, v in os.environ.items():
            if k in ENV_REGISTRY and ENV_REGISTRY[k].classification in (
                SecretClassification.SECRET,
                SecretClassification.CRITICAL_SECRET,
                SecretClassification.SENSITIVE,
            ):
                s_val, meta = self.get_secret(k)
                if meta:
                    results[k] = meta
            elif is_secret_variable(k):
                s_val, meta = self.get_secret(k)
                if meta:
                    results[k] = meta

        return results


class EncryptedFileSecretProvider(BaseSecretProvider):
    """Secret provider backed by local EncryptedSecretStore (Fernet AES-128-CBC + HMAC-SHA256)."""

    def __init__(self, store: EncryptedSecretStore):
        self.store = store

    @property
    def source(self) -> SecretSource:
        return SecretSource.ENCRYPTED_STORE

    def get_secret(self, identifier: str) -> Tuple[Optional[SecretValue], Optional[SecretMetadata]]:
        return self.store.get_secret(identifier)

    def set_secret(
        self,
        identifier: str,
        value: SecretValue,
        classification: SecretClassification = SecretClassification.SECRET,
    ) -> SecretMetadata:
        """Stores encrypted secret entry."""
        return self.store.set_secret(identifier, value, classification)

    def delete_secret(self, identifier: str) -> bool:
        """Removes secret entry."""
        return self.store.delete_secret(identifier)

    def list_metadata(self) -> Dict[str, SecretMetadata]:
        return self.store.list_metadata()


class CompositeSecretProvider(BaseSecretProvider):
    """
    Composite provider chaining multiple secret providers in priority order.
    Default order: EncryptedStore -> Environment.
    """

    def __init__(self, providers: List[BaseSecretProvider]):
        if not providers:
            raise ValueError("CompositeSecretProvider requires at least one provider.")
        self.providers = providers

    @property
    def source(self) -> SecretSource:
        return self.providers[0].source

    def get_secret(self, identifier: str) -> Tuple[Optional[SecretValue], Optional[SecretMetadata]]:
        for provider in self.providers:
            s_val, meta = provider.get_secret(identifier)
            if s_val is not None and meta is not None:
                return s_val, meta
        return None, None

    def list_metadata(self) -> Dict[str, SecretMetadata]:
        combined: Dict[str, SecretMetadata] = {}
        # Reverse list so higher-priority providers overwrite lower-priority ones
        for provider in reversed(self.providers):
            combined.update(provider.list_metadata())
        return combined
