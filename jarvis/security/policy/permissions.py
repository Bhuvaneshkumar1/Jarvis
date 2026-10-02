"""
Typed Permission Taxonomy & Delegation Enforcer for JARVIS (Batch 15).
"""

from typing import List, Set
from jarvis.security.policy.models import Principal, PrincipalType
from jarvis.security.policy.exceptions import DelegationError


# Category Constants
FILESYSTEM_PERMISSIONS: Set[str] = {
    "filesystem.read",
    "filesystem.create",
    "filesystem.modify",
    "filesystem.delete",
    "filesystem.rename",
    "filesystem.move",
    "filesystem.execute",
}

SYSTEM_PERMISSIONS: Set[str] = {
    "system.app.launch",
    "system.app.close",
    "system.process.inspect",
    "system.process.terminate",
    "system.settings.read",
    "system.settings.modify",
    "system.shutdown",
    "system.restart",
}

DEVELOPMENT_PERMISSIONS: Set[str] = {
    "code.read",
    "code.create",
    "code.modify",
    "code.delete",
    "code.test",
    "code.build",
    "git.status",
    "git.commit",
    "git.push",
}

AGENT_PERMISSIONS: Set[str] = {
    "agent.create",
    "agent.spawn",
    "agent.delegate",
    "agent.terminate",
    "agent.inspect",
}

INTEGRATION_PERMISSIONS: Set[str] = {
    "integration.read",
    "integration.write",
    "integration.send",
    "integration.delete",
}

CYBERSECURITY_PERMISSIONS: Set[str] = {
    "security.recon",
    "security.scan",
    "security.analyze",
    "security.exploit",
    "security.credential_test",
    "security.modify_target",
}

LEGACY_PERMISSIONS_MAP = {
    "READ": "filesystem.read",
    "CREATE": "filesystem.create",
    "MODIFY": "filesystem.modify",
    "DELETE": "filesystem.delete",
    "EXECUTE_COMMAND": "system.app.launch",
    "GIT_COMMIT": "git.commit",
    "GIT_PUSH": "git.push",
    "FINANCIAL": "integration.send",
    "EXTERNAL_API_CALL": "integration.send",
    "SYSTEM_CONTROL": "system.settings.modify",
}

ALL_KNOWN_PERMISSIONS = (
    FILESYSTEM_PERMISSIONS | SYSTEM_PERMISSIONS | DEVELOPMENT_PERMISSIONS | AGENT_PERMISSIONS | INTEGRATION_PERMISSIONS | CYBERSECURITY_PERMISSIONS
)

# Forbidden permissions for child/delegated agents
FORBIDDEN_DELEGATED_PERMISSIONS: Set[str] = {
    "security.exploit",
    "security.modify_target",
    "system.shutdown",
    "system.restart",
    "system.settings.modify",
    "agent.spawn",
}


def normalize_permission_name(action: str) -> str:
    """Map legacy action strings or return clean permission string."""
    action_clean = action.strip()
    if action_clean in LEGACY_PERMISSIONS_MAP:
        return LEGACY_PERMISSIONS_MAP[action_clean]
    return action_clean.lower()


def has_explicit_permission(principal: Principal, required_action: str) -> bool:
    """
    Check if principal explicitly holds the required permission or wildcard match.
    System principals hold implicit system permission if explicitly registered.
    Wildcards are supported (e.g., 'filesystem.*', '*').
    """
    if principal.principal_type == PrincipalType.SYSTEM and principal.principal_id == "system":
        return True

    perm_norm = normalize_permission_name(required_action)
    user_perms = {normalize_permission_name(p) for p in principal.permissions}

    if "*" in user_perms:
        return True

    if perm_norm in user_perms:
        return True

    # Check wildcard patterns e.g., "filesystem.*"
    if "." in perm_norm:
        category = perm_norm.split(".", 1)[0] + ".*"
        if category in user_perms:
            return True

    return False


def validate_delegation(
    parent_principal: Principal,
    delegated_permissions: List[str],
    max_delegation_depth: int = 3,
) -> None:
    """
    Validate that an agent delegation does not attempt privilege escalation.
    Child agent cannot receive permissions the parent lacks, nor sensitive credentials/forbidden perms.
    """
    if parent_principal.delegation_depth >= max_delegation_depth:
        raise DelegationError(f"Maximum delegation depth of {max_delegation_depth} exceeded by principal '{parent_principal.principal_id}'.")

    for perm in delegated_permissions:
        perm_norm = normalize_permission_name(perm)
        if perm_norm in FORBIDDEN_DELEGATED_PERMISSIONS:
            raise DelegationError(f"Permission '{perm_norm}' cannot be delegated to sub-agents.")

        if not has_explicit_permission(parent_principal, perm_norm):
            raise DelegationError(f"Privilege escalation attempt: parent '{parent_principal.principal_id}' lacks permission '{perm_norm}'.")
