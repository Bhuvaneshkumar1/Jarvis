import os
import shutil
import tempfile
from typing import List, Dict, Any, Optional

class RollbackAction:
    def __init__(self, action_type: str, target: str, backup_path: Optional[str] = None):
        self.action_type = action_type  # e.g., 'RESTORE_FILE', 'DELETE_CREATED_FILE', 'CUSTOM'
        self.target = target
        self.backup_path = backup_path

class RollbackManager:
    """
    Rollback & State Recovery Manager enforcing Rule 12.
    Tracks state changes during multi-step operations and safely restores previous state on failure.
    """

    def __init__(self):
        self.rollback_stack: List[RollbackAction] = []
        self._temp_dir = tempfile.mkdtemp(prefix="jarvis_rollback_")

    def create_file_backup(self, filepath: str) -> Optional[str]:
        if not os.path.exists(filepath):
            return None
        backup_filename = f"backup_{os.path.basename(filepath)}_{len(self.rollback_stack)}.bak"
        backup_path = os.path.join(self._temp_dir, backup_filename)
        shutil.copy2(filepath, backup_path)
        return backup_path

    def register_file_modification(self, filepath: str):
        backup_path = self.create_file_backup(filepath)
        if backup_path:
            self.rollback_stack.append(
                RollbackAction(action_type="RESTORE_FILE", target=filepath, backup_path=backup_path)
            )

    def register_file_creation(self, filepath: str):
        self.rollback_stack.append(
            RollbackAction(action_type="DELETE_CREATED_FILE", target=filepath)
        )

    def execute_rollback(self) -> Dict[str, Any]:
        """
        Executes registered rollback steps in reverse order (LIFO).
        Returns a detailed summary of restored state and any rollback errors.
        """
        results = []
        errors = []
        while self.rollback_stack:
            action = self.rollback_stack.pop()
            try:
                if action.action_type == "RESTORE_FILE":
                    if action.backup_path and os.path.exists(action.backup_path):
                        shutil.copy2(action.backup_path, action.target)
                        results.append(f"Restored file '{action.target}' from backup.")
                    else:
                        errors.append(f"Backup missing for RESTORE_FILE target '{action.target}'.")

                elif action.action_type == "DELETE_CREATED_FILE":
                    if os.path.exists(action.target):
                        os.remove(action.target)
                        results.append(f"Cleaned up created file '{action.target}'.")
                    else:
                        results.append(f"Created file '{action.target}' was already absent.")
            except Exception as e:
                errors.append(f"Failed rollback for {action.action_type} on {action.target}: {str(e)}")

        return {
            "success": len(errors) == 0,
            "restored_actions": results,
            "rollback_errors": errors,
        }

    def cleanup(self):
        if os.path.exists(self._temp_dir):
            try:
                shutil.rmtree(self._temp_dir)
            except Exception:
                pass
