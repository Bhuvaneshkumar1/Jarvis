"""
Approval Startup Recovery Service for JARVIS (Batch 18).

Detects approvals that expired while offline or during system operations,
transitions overdue pending requests to EXPIRED, and syncs linked tasks.
"""

import logging
import time
from typing import List, Optional, Any

from jarvis.security.policy.models import ApprovalRequest, ApprovalStatus
from jarvis.security.policy.store import PolicyRepository

logger = logging.getLogger(__name__)


class ApprovalRecoveryService:
    """
    Service responsible for recovering approval state on startup and maintenance cycles.
    """

    def __init__(
        self,
        repository: PolicyRepository,
        task_manager: Optional[Any] = None,
    ) -> None:
        self.repository = repository
        self.task_manager = task_manager

    def recover_expired_approvals(self, now: Optional[float] = None) -> List[ApprovalRequest]:
        """
        Scans for and transitions overdue pending approval requests to EXPIRED.
        Updates associated tasks if task manager is registered.
        """
        current_time = now if now is not None else time.time()
        expired_requests = self.repository.expire_outdated_approvals(now=current_time)

        if not expired_requests:
            logger.info("Approval recovery completed: 0 expired approvals found.")
            return []

        logger.warning(
            f"Approval recovery: processed {len(expired_requests)} overdue approval requests."
        )

        # Notify task manager if linked tasks exist
        if self.task_manager:
            for req in expired_requests:
                if req.task_id:
                    try:
                        self._handle_task_approval_expired(req.task_id, req.approval_id)
                    except Exception as e:
                        logger.error(
                            f"Failed to sync task '{req.task_id}' for expired approval '{req.approval_id}': {e}"
                        )

        return expired_requests

    def _handle_task_approval_expired(self, task_id: str, approval_id: str) -> None:
        """Helper to inform task manager about approval expiry."""
        if hasattr(self.task_manager, "on_approval_expired"):
            self.task_manager.on_approval_expired(task_id=task_id, approval_id=approval_id)
        elif hasattr(self.task_manager, "handle_approval_decision"):
            self.task_manager.handle_approval_decision(
                task_id=task_id,
                approval_id=approval_id,
                decision=ApprovalStatus.EXPIRED,
            )
