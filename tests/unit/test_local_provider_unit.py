"""
Unit Tests for LocalLLMProvider and MockLocalRuntime (Batch 23).
Deterministic offline tests verifying provider lifecycle, generation, streaming,
privacy classification handling, structured output, and tool isolation.
"""

import pytest
from pathlib import Path

from jarvis.core.enums import HealthState, MessageRole
from jarvis.llm.contracts import (
    LLMRequest,
    ChatMessage,
    DataClassification,
    LLMProviderState,
    StreamEventType,
)
from jarvis.llm.exceptions import (
    ProviderUnavailableError,
    InvalidLLMRequestError,
)
from jarvis.llm.local_runtime.llama_cpp_runtime import MockLocalRuntime
from jarvis.llm.providers.local import LocalLLMProvider
from jarvis.llm.factory import LLMProviderFactory
from jarvis.llm.registry import LLMProviderRegistry


@pytest.mark.asyncio
async def test_local_provider_disabled_by_default(tmp_path: Path):
    provider = LocalLLMProvider(
        enabled=False,
        models_dir=str(tmp_path),
        runtime=MockLocalRuntime(),
    )
    await provider.initialize()

    assert provider.state == LLMProviderState.UNAVAILABLE
    assert provider.is_local is True

    health = await provider.health_check()
    assert health == HealthState.UNHEALTHY

    with pytest.raises(ProviderUnavailableError):
        req = LLMRequest(
            model_id="local-default",
            messages=[ChatMessage(role=MessageRole.USER, content="Hello")],
        )
        await provider.generate(req)

    await provider.close()


@pytest.mark.asyncio
async def test_local_provider_mock_runtime_lifecycle(tmp_path: Path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model_file = models_dir / "test.gguf"
    model_file.write_bytes(b"GGUF_MOCK")

    runtime = MockLocalRuntime(default_response="JARVIS Local Output")
    provider = LocalLLMProvider(
        enabled=True,
        models_dir=str(models_dir),
        model_path=str(model_file),
        runtime=runtime,
    )

    await provider.initialize()
    assert provider.state == LLMProviderState.READY
    assert runtime.is_loaded() is True

    health = await provider.health_check()
    assert health == HealthState.HEALTHY

    # Synchronous generation
    req = LLMRequest(
        model_id="local-default",
        messages=[ChatMessage(role=MessageRole.USER, content="Offline test")],
    )
    res = await provider.generate(req)

    assert res.provider_id == "local"
    assert "JARVIS Local Output" in res.generated_content
    assert res.usage.total_tokens > 0

    # Unload model
    await provider.unload_model()
    assert runtime.is_loaded() is False

    await provider.close()


@pytest.mark.asyncio
async def test_local_provider_privacy_classification(tmp_path: Path):
    """Verifies that local provider allows CONFIDENTIAL and RESTRICTED data because is_local is True."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model_file = models_dir / "test.gguf"
    model_file.write_bytes(b"GGUF_MOCK")

    provider = LocalLLMProvider(
        enabled=True,
        models_dir=str(models_dir),
        model_path=str(model_file),
        runtime=MockLocalRuntime(),
    )
    await provider.initialize()

    # CONFIDENTIAL data classification request
    req_conf = LLMRequest(
        model_id="local-default",
        messages=[ChatMessage(role=MessageRole.USER, content="Top Secret local query")],
        data_classification=DataClassification.CONFIDENTIAL,
    )
    res_conf = await provider.generate(req_conf)
    assert res_conf is not None

    # RESTRICTED data classification request
    req_rest = LLMRequest(
        model_id="local-default",
        messages=[ChatMessage(role=MessageRole.USER, content="Restricted personal info")],
        data_classification=DataClassification.RESTRICTED,
    )
    res_rest = await provider.generate(req_rest)
    assert res_rest is not None

    await provider.close()


@pytest.mark.asyncio
async def test_local_provider_streaming(tmp_path: Path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model_file = models_dir / "test.gguf"
    model_file.write_bytes(b"GGUF_MOCK")

    provider = LocalLLMProvider(
        enabled=True,
        models_dir=str(models_dir),
        model_path=str(model_file),
        runtime=MockLocalRuntime(default_response="Token1 Token2 Token3"),
    )
    await provider.initialize()

    req = LLMRequest(
        model_id="local-default",
        messages=[ChatMessage(role=MessageRole.USER, content="Stream request")],
        stream=True,
    )

    events = []
    async for ev in provider.stream(req):
        events.append(ev)

    assert len(events) >= 3
    assert events[0].event_type == StreamEventType.STREAM_STARTED
    text_deltas = [e.text_delta for e in events if e.event_type == StreamEventType.TEXT_DELTA]
    assert len(text_deltas) > 0
    assert events[-1].event_type == StreamEventType.STREAM_COMPLETED

    await provider.close()


@pytest.mark.asyncio
async def test_local_provider_json_structured_output_validation(tmp_path: Path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model_file = models_dir / "test.gguf"
    model_file.write_bytes(b"GGUF_MOCK")

    # Mock runtime returning valid JSON string
    runtime_json = MockLocalRuntime(default_response='{"status": "success", "result": 42}')
    provider = LocalLLMProvider(
        enabled=True,
        models_dir=str(models_dir),
        model_path=str(model_file),
        runtime=runtime_json,
    )
    await provider.initialize()

    req = LLMRequest(
        model_id="local-default",
        messages=[ChatMessage(role=MessageRole.USER, content="Give me JSON")],
        response_format={"type": "json_object"},
    )
    res = await provider.generate(req)
    assert res.structured_output == {"status": "success", "result": 42}

    # Mock runtime returning invalid JSON string -> expect InvalidLLMRequestError
    runtime_bad = MockLocalRuntime(default_response="Invalid non-json output text")
    provider_bad = LocalLLMProvider(
        enabled=True,
        models_dir=str(models_dir),
        model_path=str(model_file),
        runtime=runtime_bad,
    )
    await provider_bad.initialize()

    with pytest.raises(InvalidLLMRequestError, match="failed JSON validation"):
        await provider_bad.generate(req)

    await provider.close()
    await provider_bad.close()


def test_factory_registers_local_provider():
    registry = LLMProviderRegistry()
    factory = LLMProviderFactory(registry=registry)
    assert "local" in factory._provider_classes
