"""Optional read-only metadata check; no generation and no implicit runtime probe."""

import os

import pytest

from workflow_reuse_orchestrator.config import ollama_base_url
from workflow_reuse_orchestrator.runtime.ollama import OllamaProvider


@pytest.mark.live
def test_explicit_installed_model_metadata() -> None:
    model_name = os.environ.get("OLLAMA_TEST_MODEL")
    if not model_name:
        pytest.skip("Set OLLAMA_TEST_MODEL to an exact installed name for this live check.")
    with OllamaProvider(base_url=ollama_base_url()) as provider:
        model = provider.inspect_model(model_name)
    assert model.model_name == model_name
    assert model.native_context_tokens > 0
