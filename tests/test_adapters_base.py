from jarvis.adapters.base import BaseAdapter

class DummyAdapter(BaseAdapter):
    def initialize(self) -> bool:
        return True

    def health_check(self):
        return {"status": "HEALTHY"}

def test_base_adapter_contract():
    adapter = DummyAdapter()
    assert adapter.initialize() is True
    assert adapter.health_check()["status"] == "HEALTHY"
