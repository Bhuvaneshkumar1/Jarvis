import os
import shutil
import tempfile
import pytest


@pytest.fixture
def temp_dir():
    dirpath = tempfile.mkdtemp(prefix="jarvis_batch1_test_")
    yield dirpath
    if os.path.exists(dirpath):
        shutil.rmtree(dirpath, ignore_errors=True)
