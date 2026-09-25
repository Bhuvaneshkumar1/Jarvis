import pytest
from pydantic import ValidationError
from jarvis.core.contracts.llm import ChatMessage, LLMRequestContract, LLMResponseContract
from jarvis.core.enums import MessageRole

def test_llm_contracts_serialization():
    msg = ChatMessage(role=MessageRole.USER, content="Hello JARVIS")
    req = LLMRequestContract(
        model="meta/llama-3.3-70b-instruct",
        messages=[msg],
        temperature=0.2,
    )
    assert req.request_id.startswith("llmreq-")

    res = LLMResponseContract(
        request_id=req.request_id,
        provider="nvidia",
        model="meta/llama-3.3-70b-instruct",
        content="Hello! How can I assist you?",
        latency=0.45,
    )
    dumped = res.model_dump()
    reconstructed = LLMResponseContract.model_validate(dumped)
    assert reconstructed.latency == 0.45

def test_llm_response_immutability():
    res = LLMResponseContract(request_id="llmreq-1", provider="local", model="llama")
    with pytest.raises(ValidationError):
        res.content = "New content"
