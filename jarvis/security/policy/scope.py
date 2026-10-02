"""
Resource Path Normalization & Cybersecurity Scope Evaluator for JARVIS (Batch 15).
"""

import os
import time
from typing import Optional
from jarvis.security.policy.models import CyberAuthorizationContext, CyberScopeCategory
from jarvis.security.policy.exceptions import ScopeViolationError, CyberAuthorizationError


def normalize_resource_path(path_str: str) -> str:
    """
    Safely normalize Windows filesystem path.
    - Resolves relative components (. and ..)
    - Resolves symbolic links and junctions via os.path.realpath
    - Converts backslashes/slashes into consistent absolute path format
    """
    if not path_str or not path_str.strip():
        raise ScopeViolationError("Resource path cannot be empty.")

    clean_path = os.path.expanduser(os.path.expandvars(path_str.strip()))

    # Absolutize
    if not os.path.isabs(clean_path):
        clean_path = os.path.abspath(clean_path)

    # Realpath to resolve symlinks & junctions
    try:
        real_p = os.path.realpath(clean_path)
    except Exception:
        real_p = os.path.normpath(clean_path)

    # On Windows, normalize casing for comparisons
    if os.name == "nt":
        real_p = os.path.normcase(real_p)

    return real_p


def is_path_in_scope(target_path: str, scope_root: str) -> bool:
    """
    Safely determine if target_path is within scope_root directory hierarchy.
    Prevents path traversal attacks, junctions escape, and case mismatch on Windows.
    """
    try:
        norm_target = normalize_resource_path(target_path)
        norm_scope = normalize_resource_path(scope_root)
    except Exception as e:
        raise ScopeViolationError(f"Path normalization error: {str(e)}") from e

    # Exact match or prefix match with path separator
    if norm_target == norm_scope:
        return True

    # Ensure trailing separator on scope for prefix comparison
    if not norm_scope.endswith(os.sep):
        norm_scope_sep = norm_scope + os.sep
    else:
        norm_scope_sep = norm_scope

    return norm_target.startswith(norm_scope_sep)


def validate_cybersecurity_scope(
    action: str,
    target_resource: str,
    cyber_context: Optional[CyberAuthorizationContext],
) -> CyberScopeCategory:
    """
    Validate cybersecurity activity scope against context.
    Strictly denies operations against UNKNOWN_TARGET or missing/expired contexts.
    """
    if not cyber_context:
        raise CyberAuthorizationError(f"Cybersecurity action '{action}' against target '{target_resource}' requires explicit CyberAuthorizationContext.")

    if cyber_context.scope_category == CyberScopeCategory.UNKNOWN_TARGET:
        raise CyberAuthorizationError(f"Active security operation '{action}' strictly denied against UNKNOWN_TARGET '{target_resource}'.")

    if cyber_context.scope_expiration and cyber_context.scope_expiration < time.time():
        raise CyberAuthorizationError(f"Cybersecurity scope for target '{target_resource}' has expired.")

    # Check target match
    if cyber_context.target_identifier.lower() not in target_resource.lower() and target_resource.lower() not in cyber_context.target_identifier.lower():
        raise CyberAuthorizationError(f"Target resource '{target_resource}' does not match authorized target '{cyber_context.target_identifier}'.")

    return cyber_context.scope_category
