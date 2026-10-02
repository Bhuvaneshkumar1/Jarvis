"""
Opt-in Integration Test for Real GGUF Local LLM Inference (Batch 23).
Skipped automatically if llama-cpp-python is not installed or no GGUF model is found.
"""

import os
import pytest
from pathlib import Path

from jarvis.llm.contracts import LLMRequest, ChatMessage
from jarvis.core.enums import MessageRole, HealthState
from jarvis.llm.local_runtime.llama_cpp_runtime import (
    LLAMA_CPP_AVAILABLE,
    LlamaCppRuntime,
)
from jarvis.llm.local_runtime.model_manager import LocalModelManager
from jarvis.llm.providers.local import LocalLLMProvider


@pytest.mark.asyncio
async def test_live_local_gguf_inference():
    if not LLAMA_CPP_AVAILABLE:
        pytest.skip("llama-cpp-python is not installed in the test environment.")

    models_dir = os.getenv("LOCAL_LLM_MODELS_DIR", "data/models")
    model_path = os.getenv("LOCAL_LLM_MODEL_PATH")

    mgr = LocalModelManager(models_dir=models_dir)
    discovered = mgr.discover_models()

    target_model_path = model_path
    if not target_model_path and discovered:
        target_model_path = str(discovered[0].file_path)

    if not target_model_path or not Path(target_model_path).exists():
        pytest.skip("No real GGUF model file configured or discovered in data/models.")

    provider = LocalLLMProvider(
        enabled=True,
        models_dir=models_dir,
        model_path=target_model_path,
        runtime=LlamaCppRuntime(),
    )

    try:
        await provider.initialize()
        health = await provider.health_check()
        assert health in (HealthState.HEALTHY, HealthState.DEGRADED)

        req = LLMRequest(
            model_id="local-live-test",
            messages=[ChatMessage(role=MessageRole.USER, content="Hello, reply with 1 word: Ready.")],
            max_tokens=10,
        )

        res = await provider.generate(req)
        assert res.generated_content is not None
        assert res.usage.total_tokens > 0
        assert res.latency > 0.0

    finally:
        await provider.close()
