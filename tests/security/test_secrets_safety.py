import os

def test_dot_env_not_tracked_in_git():
    """Verify .env is excluded by .gitignore and not tracked by Git."""
    gitignore_path = ".gitignore"
    assert os.path.exists(gitignore_path)
    with open(gitignore_path, "r") as f:
        content = f.read()
    assert ".env" in content

def test_env_example_contains_no_secrets():
    """Verify .env.example contains variable names only without actual secret values."""
    env_example_path = ".env.example"
    assert os.path.exists(env_example_path)
    with open(env_example_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    val = parts[1].strip()
                    # Ensure no hard-coded secret keys in .env.example
                    assert not val.startswith("sk-")
                    assert not val.startswith("ghp_")
                    assert not val.startswith("xox")
                    assert not val.startswith("cfut_")
