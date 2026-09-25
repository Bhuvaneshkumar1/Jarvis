import compileall
import re


def test_compileall_python_files():
    # Compile python files excluding virtual environments and build directories
    rx = re.compile(r"\.venv|\.git|build|dist")
    res = compileall.compile_dir(".", rx=rx, quiet=1)
    assert res is True
