import pytest
from jarvis.core.contracts.requests import RequestContract
from jarvis.core.enums import RequestSource, InputType

def test_request_contract_construction_and_serialization():
    req = RequestContract(
        content="Analyze workspace baseline",
        source=RequestSource.LOCAL_UI,
        input_type=InputType.TEXT,
    )
    assert req.request_id.startswith("req-")
    assert req.content == "Analyze workspace baseline"

    # Serialization test
    dumped = req.model_dump()
    assert dumped["source"] == "LOCAL_UI"
    assert dumped["input_type"] == "TEXT"

    # Deserialization test
    reconstructed = RequestContract.model_validate(dumped)
    assert reconstructed.request_id == req.request_id

def test_request_contract_invalid_empty_id():
    with pytest.raises(ValueError):
        RequestContract(request_id="   ", content="Valid content")
