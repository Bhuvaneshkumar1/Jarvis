import importlib


def test_core_and_contracts_imports():
    modules = [
        "main",
        "config",
        "config.settings",
        "jarvis",
        "jarvis.core",
        "jarvis.core.exceptions",
        "jarvis.core.logging",
        "jarvis.core.enums",
        "jarvis.core.contracts",
        "jarvis.core.contracts.requests",
        "jarvis.core.contracts.responses",
        "jarvis.core.contracts.tasks",
        "jarvis.core.contracts.agents",
        "jarvis.core.contracts.tools",
        "jarvis.core.contracts.memory",
        "jarvis.core.contracts.llm",
        "jarvis.core.contracts.security",
        "jarvis.core.contracts.verification",
        "jarvis.core.contracts.audit",
        "jarvis.core.contracts.integrations",
        "jarvis.core.contracts.health",
        "jarvis.core.runtime",
        "jarvis.core.runtime.lifecycle",
        "jarvis.core.runtime.context",
        "jarvis.core.runtime.registry",
        "jarvis.core.runtime.application",
    ]
    for mod_name in modules:
        mod = importlib.import_module(mod_name)
        assert mod is not None
