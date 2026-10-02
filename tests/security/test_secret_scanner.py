from scripts.quality_gate import run_secret_scan, SECRET_REGEXES, SAFE_PLACEHOLDERS


def test_secret_scanner_clean_repo():
    passed, output = run_secret_scan()
    assert passed is True
    assert "Zero unredacted credentials detected" in output


def test_secret_scanner_regex_matching():
    sample_key = "TOKEN_PLACEHOLDER"
    regex, secret_type = SECRET_REGEXES[0]
    import re

    matches = re.findall(regex, sample_key)
    assert len(matches) == 1


def test_safe_placeholder_ignored():
    sample_placeholder = "OPENROUTER_API_KEY=YOUR_API_KEY_HERE_0"
    assert any(ph in sample_placeholder for ph in SAFE_PLACEHOLDERS)
