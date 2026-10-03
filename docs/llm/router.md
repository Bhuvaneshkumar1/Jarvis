# Intelligent LLM Router Architecture (Batch 24)

## 1. Subsystem Overview

The `LLMRouter` (`jarvis/llm/router.py`) provides centralized, policy-aware, privacy-preserving LLM request routing, provider candidate ranking, and controlled fallback across all registered JARVIS providers (NVIDIA NIM, OpenRouter, and Local LLM).

---

## 2. Component Structure

```
jarvis/llm/
├── router.py                       # LLMRouter central entry point
└── routing/
    ├── classifier.py               # TaskClassifier (Explicit metadata precedence + prompt heuristics)
    ├── routing_policy.py           # RoutingPolicyEngine (Data classification privacy boundaries)
    ├── capability_matcher.py       # CapabilityMatcher (Model capabilities & context window matching)
    ├── candidate_selector.py       # CandidateSelector (Profile-based ranking & tie-breaking)
    ├── fallback_manager.py         # FallbackManager (Error retryability & attempt budget isolation)
    ├── routing_metrics.py          # RoutingMetricsTracker (Rolling latency & success metrics)
    └── routing_explainer.py        # RoutingExplainer (Sanitized audit explanations)
```

---

## 3. Task Classification Categories

| Category | Description |
| :--- | :--- |
| `SIMPLE_CHAT` | Short conversational prompts |
| `REASONING` | Multi-step logical problems and derivations |
| `CODING` | Code generation and refactoring assistance |
| `DEBUGGING` | Error analysis and stack trace troubleshooting |
| `RESEARCH` | Information synthesis and analysis |
| `SUMMARIZATION` | Document and text summarization |
| `CLASSIFICATION` | Labeling and text categorization |
| `STRUCTURED_OUTPUT` | Schema-constrained JSON responses |
| `VISION` | Multimodal image understanding |
| `TOOL_PLANNING` | Planning tool and function execution |
| `GENERAL` | Unclassified requests |

---

## 4. Privacy & Data Handling Policies

- **`CONFIDENTIAL` / `RESTRICTED` / `local_only=True`**: Strictly routed to local providers (`is_local=True`). External cloud providers (`nvidia`, `openrouter`) are **excluded** and blocked from candidate selection and fallback chains.
- **`PUBLIC` / `INTERNAL`**: Routeable to eligible local or cloud providers according to active `RoutingProfile`.

---

## 5. Routing Profiles

- **`LATENCY_FIRST`**: Prefers providers with lowest rolling response latency.
- **`COST_AWARE`**: Prefers zero-cost local inference or cheaper cloud models.
- **`QUALITY_PREFERRED`**: Prefers models with higher context window and capability coverage.
- **`PRIVACY_FIRST`**: Prioritizes local providers (`is_local=True`) whenever available.
- **`BALANCED`**: Default profile balancing local preference, context capacity, and measured latency.

---

## 6. Configuration & Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `LLM_ROUTING_ENABLED` | Enables centralized router | `true` |
| `LLM_ROUTING_PROFILE` | Default routing profile | `BALANCED` |
| `LLM_ROUTING_MAX_ATTEMPTS` | Max provider fallback attempts | `3` |
| `LLM_ROUTING_ALLOW_FALLBACK` | Allows fallback on retryable errors | `true` |
