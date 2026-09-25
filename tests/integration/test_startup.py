from main import main


def test_main_startup_clean_exit():
    """Integration test verifying main entry point initializes config and exits cleanly with 0."""
    exit_code = main()
    assert exit_code == 0
