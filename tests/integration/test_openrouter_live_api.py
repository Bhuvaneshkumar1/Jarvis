"""
Opt-in Live Integration Tests for OpenRouter API (Batch 22).
Executed ONLY when OPENROUTER_API_KEY is configured in environment and network is available.
"""

import os
import pytest
from dotenv import dotenv_values

from jarvis.core.enums import MessageRole
from jarvis.llm.contracts import ChatMessage, LLMRequest
from jarvis.llm.providers.openrouter import OpenRouterProvider


def _get_openrouter_key() -> str | None:
    # First check process environment
    key = os.getenv("OPENROUTER_API_KEY")
    if key and not key.startswith("YOUR_"):
        return key
    # Fallback to reading .env directly without mutating os.environ
    if os.path.exists(".env"):
        env_dict = dotenv_values(".env")
        key = env_dict.get("OPENROUTER_API_KEY")
        if key and not key.startswith("YOUR_"):
            return key
    return None


OPENROUTER_KEY = _get_openrouter_key()
SKIP_LIVE = not OPENROUTER_KEY


@pytest.mark.skipif(SKIP_LIVE, reason="Live OPENROUTER_API_KEY not configured in environment.")
@pytest.mark.asyncio
async def test_live_openrouter_model_discovery():
    provider = OpenRouterProvider(api_key=OPENROUTER_KEY)
    await provider.initialize()

    models = await provider.list_models()
    assert len(models) > 0

    model_ids = [m.model_id for m in models]
    assert any("openai" in m.lower() or "anthropic" in m.lower() or "meta" in m.lower() for m in model_ids)

    await provider.close()


@pytest.mark.skipif(SKIP_LIVE, reason="Live OPENROUTER_API_KEY not configured in environment.")
@pytest.mark.asyncio
async def test_live_openrouter_chat_completion():
    provider = OpenRouterProvider(api_key=OPENROUTER_KEY)
    await provider.initialize()

    target_model = "openai/gpt-4o-mini"
    msg = ChatMessage(role=MessageRole.USER, content="Reply with exactly 'OK'")
    req = LLMRequest(model_id=target_model, messages=[msg], max_tokens=10)

    try:
        res = await provider.generate(req)
        assert res.request_id == req.request_id
        assert res.provider_id == "openrouter"
        assert res.latency > 0.0
    except Exception as ex:
        err_str = str(ex)
        if any(code in err_str for code in ("401", "402", "403", "404", "410", "429")):
            pytest.skip(f"Live OpenRouter API access restriction/quota response: {ex}")
        else:
            raise
    finally:
        await provider.close()
