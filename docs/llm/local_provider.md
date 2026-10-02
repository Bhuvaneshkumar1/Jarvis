# Local LLM Provider Architecture (Batch 23)

## 1. Subsystem Overview

The `LocalLLMProvider` (`jarvis/llm/providers/local.py`) enables offline, privacy-preserving local LLM inference directly on user Windows desktop systems using `llama.cpp` (`llama-cpp-python` GGUF model bindings). It implements `AbstractLLMProvider` (`provider_id="local"`, `is_local=True`), which allows `PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, and `RESTRICTED` data classifications to execute locally without cloud transmission privacy rejections.

---

## 2. Component Structure

```
jarvis/llm/
├── providers/
│   └── local.py                    # LocalLLMProvider implementing AbstractLLMProvider
└── local_runtime/
    ├── base.py                     # AbstractLocalRuntime interface
    ├── model_manager.py            # LocalModelManager (GGUF discovery & path security)
    ├── resource_manager.py         # LocalResourceManager (RAM limits & overhead estimation)
    └── llama_cpp_runtime.py        # LlamaCppRuntime (llama-cpp-python adapter) & MockLocalRuntime
```

---

## 3. Configuration & Environment Variables

| Setting / Env Variable | Description | Default Value |
| :--- | :--- | :--- |
| `LOCAL_LLM_ENABLED` | Enables local LLM provider startup | `false` |
| `LOCAL_LLM_MODELS_DIR` | Models directory for GGUF discovery | `data/models` |
| `LOCAL_LLM_MODEL_PATH` | Path to default GGUF model file | `None` |
| `LOCAL_LLM_CONTEXT_LENGTH` | Context window size in tokens | `2048` |
| `LOCAL_LLM_MAX_TOKENS` | Max output completion tokens | `512` |
| `LOCAL_LLM_THREADS` | CPU inference threads | `4` |
| `LOCAL_LLM_GPU_LAYERS` | Offloaded GPU layers (`0` = CPU only) | `0` |
| `LOCAL_LLM_MAX_MEMORY_MB` | Maximum allowed RAM ceiling in MB | `4096.0` |

---

## 4. Key Security & Operational Guarantees

1. **Path Safety & Traversal Prevention**: `LocalModelManager.validate_model_path` enforces `.gguf` extension validation, file readability checks, and resolves paths to prevent directory traversal outside authorized directories.
2. **Resource-Aware Load Checks**: `LocalResourceManager.can_load_model` estimates total RAM required (weights + KV cache + 200MB overhead) against system available memory and `LOCAL_LLM_MAX_MEMORY_MB` before loading.
3. **Graceful Degradation**: If `llama-cpp-python` or model files are missing, `LocalLLMProvider` transitions to `UNAVAILABLE` state without crashing the core application.
4. **Tool Isolation**: Untrusted model-generated tool calls are returned as `LLMToolCall` objects (`PENDING`) and are **never** executed directly inside the provider.

---

## 5. Usage Example

```python
import asyncio
from jarvis.llm.providers.local import LocalLLMProvider
from jarvis.llm.local_runtime.llama_cpp_runtime import MockLocalRuntime
from jarvis.llm.contracts import LLMRequest, ChatMessage
from jarvis.core.enums import MessageRole


async def main():
    # Instantiate with MockLocalRuntime for testing or LlamaCppRuntime for production
    provider = LocalLLMProvider(
        enabled=True,
        runtime=MockLocalRuntime(),
    )
    await provider.initialize()

    request = LLMRequest(
        model_id="local-default",
        messages=[ChatMessage(role=MessageRole.USER, content="Offline query.")],
        max_tokens=100,
    )

    response = await provider.generate(request)
    print(f"Content: {response.content}")
    print(f"Latency: {response.latency}s")

    await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
```
