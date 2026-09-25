from typing import Dict, Any, Optional
from jarvis.core.privacy import PrivacyEngine
from jarvis.core.config import get_settings

class LLMRouter:
    """
    LLM Router Interface enforcing local/cloud privacy routing (Rule 14 & Rule 17).
    """

    def __init__(self, privacy_engine: Optional[PrivacyEngine] = None):
        self.privacy_engine = privacy_engine or PrivacyEngine()
        self.settings = get_settings()

    def route_and_generate(
        self,
        prompt: str,
        system_instruction: str = "",
        force_local: bool = False,
        provider: str = "auto",
    ) -> Dict[str, Any]:
        """
        Evaluates input prompt for sensitive information.
        If sensitive information is detected or force_local is True, routes to local LLM endpoint.
        Otherwise routes to requested provider with sanitized payload.
        """
        sanitized_prompt, prompt_redacted = self.privacy_engine.filter_text(prompt)
        sanitized_sys, sys_redacted = self.privacy_engine.filter_text(system_instruction)

        has_sensitive_data = prompt_redacted or sys_redacted

        target_mode = "LOCAL" if (force_local or has_sensitive_data or provider == "local") else "CLOUD"

        # Construct sanitized request payload
        request_payload = {
            "prompt": sanitized_prompt,
            "system_instruction": sanitized_sys,
            "provider": provider,
            "target_mode": target_mode,
            "redacted_sensitive_info": has_sensitive_data,
        }

        # Simulated adapter routing response (Adapters will implement full provider calls)
        if target_mode == "LOCAL":
            response_text = f"[LOCAL_LLM_RESPONSE]: Processed prompt locally at {self.settings.local_llm_url}."
        else:
            response_text = f"[CLOUD_LLM_RESPONSE]: Processed prompt via cloud provider {provider}."

        return {
            "text": response_text,
            "target_mode": target_mode,
            "payload_sent": request_payload,
            "redacted_sensitive_info": has_sensitive_data,
        }
