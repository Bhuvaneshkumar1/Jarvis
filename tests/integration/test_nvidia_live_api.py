"""
Opt-in Live Integration Tests for NVIDIA NIM API (Batch 21).
Executed ONLY when NVIDIA_API_KEY is configured in local environment and network is available.
"""

import os
import pytest

from jarvis.core.enums import MessageRole
from jarvis.llm.contracts import ChatMessage, LLMRequest
from jarvis.llm.providers.nvidia import NVIDIAProvider

from dotenv import dotenv_values


def _get_nvidia_key() -> str | None:
    # First check process environment
    key = os.getenv("NVIDIA_API_KEY")
    if key and not key.startswith("YOUR_"):
        return key
    # Fallback to reading .env directly without mutating os.environ
    if os.path.exists(".env"):
        env_dict = dotenv_values(".env")
        key = env_dict.get("NVIDIA_API_KEY")
        if key and not key.startswith("YOUR_"):
            return key
    return None


NVIDIA_KEY = _get_nvidia_key()
SKIP_LIVE = not NVIDIA_KEY


@pytest.mark.skipif(SKIP_LIVE, reason="Live NVIDIA_API_KEY not configured in environment.")
@pytest.mark.asyncio
async def test_live_nvidia_model_discovery():
    provider = NVIDIAProvider(api_key=NVIDIA_KEY)
    await provider.initialize()

    models = await provider.list_models()
    assert len(models) > 0

    model_ids = [m.model_id for m in models]
    assert any("llama" in m.lower() or "nemotron" in m.lower() or "mistral" in m.lower() for m in model_ids)

    await provider.close()


@pytest.mark.skipif(SKIP_LIVE, reason="Live NVIDIA_API_KEY not configured in environment.")
@pytest.mark.asyncio
async def test_live_nvidia_chat_completion():
    provider = NVIDIAProvider(api_key=NVIDIA_KEY)
    await provider.initialize()

    # Discover available models
    models = await provider.list_models()
    if not models:
        pytest.skip("No live models available for account.")

    target_model = models[0].model_id

    msg = ChatMessage(role=MessageRole.USER, content="Reply with exactly 'OK'")
    req = LLMRequest(model_id=target_model, messages=[msg], max_tokens=10)

    try:
        res = await provider.generate(req)
        assert res.request_id == req.request_id
        assert res.provider_id == "nvidia"
        assert res.model_id == target_model
        assert res.latency > 0.0
    except Exception as ex:
        # Handle account 404/410 end-of-life model error gracefully
        if "404" in str(ex) or "410" in str(ex):
            pytest.skip(f"Live model '{target_model}' returned account 404/410 access restriction: {ex}")
        else:
            raise
    finally:
        await provider.close()
