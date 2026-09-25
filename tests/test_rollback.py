import os
from jarvis.core.rollback import RollbackManager


def test_rollback_file_modification(temp_dir):
    mgr = RollbackManager()
    target_file = os.path.join(temp_dir, "original.txt")
    with open(target_file, "w") as f:
        f.write("Initial state")

    # Register modification backup
    mgr.register_file_modification(target_file)

    # Mutate file
    with open(target_file, "w") as f:
        f.write("Corrupted state")

    # Execute rollback
    res = mgr.execute_rollback()
    assert res["success"] is True

    # Verify original state restored
    with open(target_file, "r") as f:
        content = f.read()
    assert content == "Initial state"

    mgr.cleanup()


def test_rollback_file_creation(temp_dir):
    mgr = RollbackManager()
    new_file = os.path.join(temp_dir, "new_file.txt")

    mgr.register_file_creation(new_file)
    with open(new_file, "w") as f:
        f.write("Data")

    res = mgr.execute_rollback()
    assert res["success"] is True
    assert not os.path.exists(new_file)

    mgr.cleanup()
