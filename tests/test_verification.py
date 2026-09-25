import os
import time
from jarvis.core.verification import VerificationEngine


def test_verify_file_created(temp_dir):
    test_file = os.path.join(temp_dir, "created.txt")

    # Before creation
    res_before = VerificationEngine.verify_file_created(test_file)
    assert res_before.passed is False

    # After creation
    with open(test_file, "w") as f:
        f.write("Hello World")

    res_after = VerificationEngine.verify_file_created(test_file, min_bytes=5)
    assert res_after.passed is True
    assert res_after.details["size"] == 11


def test_verify_file_modified(temp_dir):
    test_file = os.path.join(temp_dir, "mod.txt")
    with open(test_file, "w") as f:
        f.write("v1")

    orig_mtime = os.path.getmtime(test_file)
    time.sleep(0.05)

    with open(test_file, "w") as f:
        f.write("v2")

    res = VerificationEngine.verify_file_modified(test_file, original_mtime=orig_mtime)
    assert res.passed is True


def test_verify_command_result():
    res_success = VerificationEngine.verify_command_result(exit_code=0)
    assert res_success.passed is True

    res_failed = VerificationEngine.verify_command_result(exit_code=1)
    assert res_failed.passed is False
