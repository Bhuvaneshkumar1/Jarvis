from jarvis.core.config import Settings
from jarvis.core.privacy import PrivacyEngine

def test_config_redacted_dict():
    settings = Settings()
    redacted = settings.get_redacted_dict()
    assert redacted["telegram_bot_token"] in ["[CONFIGURED_SECRET]", "[NOT_SET]"]
    assert redacted["openai_api_key"] in ["[CONFIGURED_SECRET]", "[NOT_SET]"]

def test_privacy_filter():
    engine = PrivacyEngine()
    prompt = "Here is my secret TOKEN_PLACEHOLDER and email john@example.com"
    clean, was_redacted = engine.filter_text(prompt)
    assert was_redacted is True
    assert "TOKEN_PLACEHOLDER" not in clean
    assert "[REDACTED_API_KEY]" in clean
    assert "[REDACTED_EMAIL]" in clean
