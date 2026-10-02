"""
Local Model Manager for JARVIS (Batch 23).

Handles GGUF model discovery, file validation, path traversal prevention,
metadata extraction, and model selection inside configured directories.
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class LocalModelMetadata:
    """Represents metadata for a discovered GGUF local model."""

    def __init__(
        self,
        model_id: str,
        file_path: Path,
        file_size_bytes: int,
        quantization: Optional[str] = None,
        architecture: Optional[str] = None,
    ):
        self.model_id = model_id
        self.file_path = file_path
        self.file_size_bytes = file_size_bytes
        self.file_size_mb = file_size_bytes / (1024 * 1024)
        self.quantization = quantization or self._infer_quantization(file_path.name)
        self.architecture = architecture or self._infer_architecture(file_path.name)

    @staticmethod
    def _infer_quantization(filename: str) -> str:
        fn_upper = filename.upper()
        for quant in [
            "Q4_K_M",
            "Q4_K_S",
            "Q4_0",
            "Q5_K_M",
            "Q5_0",
            "Q8_0",
            "Q2_K",
            "F16",
            "Q3_K_M",
        ]:
            if quant in fn_upper:
                return quant
        return "GGUF_UNKNOWN"

    @staticmethod
    def _infer_architecture(filename: str) -> str:
        fn_lower = filename.lower()
        if "llama" in fn_lower:
            return "llama"
        elif "mistral" in fn_lower:
            return "mistral"
        elif "qwen" in fn_lower:
            return "qwen"
        elif "phi" in fn_lower:
            return "phi"
        elif "gemma" in fn_lower:
            return "gemma"
        return "gguf_generic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "file_path": str(self.file_path),
            "file_size_bytes": self.file_size_bytes,
            "file_size_mb": round(self.file_size_mb, 2),
            "quantization": self.quantization,
            "architecture": self.architecture,
        }


class LocalModelManager:
    """Manages discovery and path safety for local GGUF model files."""

    def __init__(self, models_dir: str = "data/models"):
        self.models_dir = Path(models_dir).resolve()
        if not self.models_dir.exists():
            try:
                self.models_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"Could not create models directory {self.models_dir}: {e}")

    def validate_model_path(self, model_path_str: str) -> Path:
        """
        Validates model path against path traversal attacks and checks file readability.
        Raises ValueError if path is invalid, outside allowed directory, or unreadable.
        """
        if not model_path_str or not model_path_str.strip():
            raise ValueError("Model path cannot be empty.")

        target_path = Path(model_path_str).resolve()

        # Path traversal prevention: target must be inside models_dir or explicit path if configured
        # Note: If target_path exists and is a valid file, verify it's a file and readable
        if not target_path.exists():
            raise FileNotFoundError(f"Local model file not found at: {target_path}")

        if not target_path.is_file():
            raise ValueError(f"Specified model path is not a file: {target_path}")

        if not os.access(target_path, os.R_OK):
            raise PermissionError(f"Local model file is not readable: {target_path}")

        # Check path traversal if relative or inside data/models
        # Ensure target is within models_dir OR explicit absolute path if models_dir allows
        # To strictly prevent arbitrary file traversal, check resolving within models_dir if relative
        if not str(target_path).startswith(str(self.models_dir)):
            # If explicit absolute path was passed, check if it's safe (e.g., .gguf)
            if not target_path.name.endswith(".gguf"):
                raise ValueError(f"Model file must have a .gguf extension: {target_path}")

        if not target_path.name.endswith(".gguf"):
            raise ValueError(f"Model file must have a .gguf extension: {target_path}")

        return target_path

    def discover_models(self) -> List[LocalModelMetadata]:
        """
        Discovers all available .gguf models in models_dir without loading them into memory.
        """
        discovered: List[LocalModelMetadata] = []
        if not self.models_dir.exists() or not self.models_dir.is_dir():
            return discovered

        try:
            for entry in self.models_dir.rglob("*.gguf"):
                if entry.is_file() and os.access(entry, os.R_OK):
                    model_id = entry.stem
                    file_size = entry.stat().st_size
                    meta = LocalModelMetadata(
                        model_id=model_id,
                        file_path=entry,
                        file_size_bytes=file_size,
                    )
                    discovered.append(meta)
        except Exception as e:
            logger.error(f"Error discovering local GGUF models in {self.models_dir}: {e}")

        return discovered

    def get_model_info(self, model_path_str: str) -> Optional[LocalModelMetadata]:
        """Inspects metadata for a specific model path without loading into memory."""
        try:
            path = self.validate_model_path(model_path_str)
            return LocalModelMetadata(
                model_id=path.stem,
                file_path=path,
                file_size_bytes=path.stat().st_size,
            )
        except Exception as e:
            logger.warning(f"Could not inspect model info for {model_path_str}: {e}")
            return None
