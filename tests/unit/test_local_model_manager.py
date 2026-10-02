"""
Unit Tests for LocalModelManager (Batch 23).
Tests GGUF model discovery, path traversal prevention, extension checks, and readability checks.
"""

import pytest
from pathlib import Path
from jarvis.llm.local_runtime.model_manager import LocalModelManager, LocalModelMetadata


def test_model_metadata_inference(tmp_path: Path):
    model_file = tmp_path / "llama-3-8b-instruct.Q4_K_M.gguf"
    model_file.write_bytes(b"GGUF_HEADER_DUMMY_DATA")

    meta = LocalModelMetadata(
        model_id="llama-3-8b-instruct",
        file_path=model_file,
        file_size_bytes=model_file.stat().st_size,
    )

    assert meta.model_id == "llama-3-8b-instruct"
    assert meta.quantization == "Q4_K_M"
    assert meta.architecture == "llama"
    assert meta.file_size_bytes > 0
    d = meta.to_dict()
    assert d["quantization"] == "Q4_K_M"
    assert d["architecture"] == "llama"


def test_model_manager_discovery(tmp_path: Path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    m1 = models_dir / "test_model1.Q4_0.gguf"
    m1.write_bytes(b"DUMMY_GGUF_1")

    m2 = models_dir / "test_model2.Q8_0.gguf"
    m2.write_bytes(b"DUMMY_GGUF_2")

    # Unrelated file should be ignored
    unrelated = models_dir / "notes.txt"
    unrelated.write_text("Hello")

    mgr = LocalModelManager(models_dir=str(models_dir))
    discovered = mgr.discover_models()

    assert len(discovered) == 2
    model_ids = [m.model_id for m in discovered]
    assert "test_model1.Q4_0" in model_ids
    assert "test_model2.Q8_0" in model_ids


def test_model_manager_path_validation_success(tmp_path: Path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    valid_file = models_dir / "model.gguf"
    valid_file.write_bytes(b"GGUF")

    mgr = LocalModelManager(models_dir=str(models_dir))
    res_path = mgr.validate_model_path(str(valid_file))
    assert res_path == valid_file.resolve()


def test_model_manager_path_traversal_and_extension_rejection(tmp_path: Path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    non_gguf = models_dir / "malicious.sh"
    non_gguf.write_text("echo hacked")

    mgr = LocalModelManager(models_dir=str(models_dir))

    # Empty path rejection
    with pytest.raises(ValueError, match="path cannot be empty"):
        mgr.validate_model_path("")

    # Non-existent path rejection
    with pytest.raises(FileNotFoundError):
        mgr.validate_model_path(str(models_dir / "nonexistent.gguf"))

    # Non-gguf file rejection
    with pytest.raises(ValueError, match="must have a .gguf extension"):
        mgr.validate_model_path(str(non_gguf))
