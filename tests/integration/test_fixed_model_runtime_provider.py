"""HTTP fixtures verify model identity, wire options, telemetry, and ownership."""

import json
from typing import Any

import httpx
import pytest

from workflow_reuse_orchestrator.domain.providers import (
    GenerationRequest,
    InferenceProfile,
    ModelBinding,
    ProviderResponseError,
    ProviderUnavailableError,
)
from workflow_reuse_orchestrator.runtime.ollama import OllamaProvider


def request() -> GenerationRequest:
    return GenerationRequest(prompt="Question", max_output_tokens=8, timeout_seconds=2.0)


def test_inspection_uses_verbose_metadata_and_verifies_all_fingerprints(
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
) -> None:
    client, state = ollama_fixture
    with OllamaProvider(client=client) as provider:
        binding = provider.inspect_model("test-model:latest")
        provider.verify_model(binding)
    assert binding.native_context_tokens == 8192
    assert binding.model_digest == "a" * 64
    assert len(binding.tokenizer_sha256) == len(binding.template_sha256) == 64
    assert ("POST", "/api/show", {"model": "test-model:latest", "verbose": True}) in state["calls"]
    assert client.is_closed is False


@pytest.mark.parametrize("changed", ["digest", "version", "template", "tokenizer"])
def test_verification_rejects_identity_drift(
    ollama_fixture: tuple[httpx.Client, dict[str, Any]], changed: str
) -> None:
    client, state = ollama_fixture
    with OllamaProvider(client=client) as provider:
        binding = provider.inspect_model("test-model:latest")
        if changed == "digest":
            state["digest"] = "e" * 64
        elif changed == "version":
            state["version"] = "new-version"
        elif changed == "template":
            state["show"]["template"] = "new-template"
        else:
            state["show"]["model_info"]["tokenizer.ggml.tokens"] = ["different"]
        with pytest.raises(ProviderResponseError, match="differs"):
            provider.verify_model(binding)


def test_missing_installed_name_fails_before_show_or_generation(
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
) -> None:
    client, state = ollama_fixture
    with (
        OllamaProvider(client=client) as provider,
        pytest.raises(ProviderResponseError, match="exact name"),
    ):
        provider.inspect_model("resource-id-from-old-registry")
    assert all(path not in {"/api/show", "/api/generate"} for _, path, _ in state["calls"])


def test_generation_binds_options_and_keeps_timings_in_seconds(
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
    model_binding: ModelBinding,
    inference_profile: InferenceProfile,
) -> None:
    client, state = ollama_fixture
    with OllamaProvider(client=client) as provider:
        response = provider.generate(
            model=model_binding, inference=inference_profile, request=request()
        )
    payload = state["calls"][-1][2]
    assert payload["model"] == model_binding.model_name
    assert payload["stream"] is False and payload["think"] is False
    assert payload["options"]["num_ctx"] == 64
    assert payload["options"]["num_predict"] == 8
    assert payload["options"]["seed"] == 2609
    assert response.input_tokens == 10 and response.output_tokens == 2
    assert response.provider_total_seconds == 0.5
    assert response.model_load_seconds == 0.1


@pytest.mark.parametrize("value", [None, True, -1, "10"])
def test_invalid_token_counts_remain_unavailable(
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
    model_binding: ModelBinding,
    inference_profile: InferenceProfile,
    value: object,
) -> None:
    client, state = ollama_fixture
    state["generation"]["prompt_eval_count"] = value
    with OllamaProvider(client=client) as provider:
        response = provider.generate(
            model=model_binding, inference=inference_profile, request=request()
        )
    assert response.input_tokens is None
    assert response.output_tokens == 2


@pytest.mark.parametrize(
    "change", [{"done": False}, {"model": "other"}, {"response": ""}, {"thinking": "hidden"}]
)
def test_rejects_incomplete_or_unbound_generation(
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
    model_binding: ModelBinding,
    inference_profile: InferenceProfile,
    change: dict[str, Any],
) -> None:
    client, state = ollama_fixture
    state["generation"].update(change)
    with OllamaProvider(client=client) as provider, pytest.raises(ProviderResponseError):
        provider.generate(model=model_binding, inference=inference_profile, request=request())


def test_truncated_output_keeps_measured_usage(
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
    model_binding: ModelBinding,
    inference_profile: InferenceProfile,
) -> None:
    client, state = ollama_fixture
    state["generation"].update({"response": "", "done_reason": "length", "eval_count": 8})
    with OllamaProvider(client=client) as provider:
        response = provider.generate(
            model=model_binding, inference=inference_profile, request=request()
        )
    assert response.finish_reason == "length" and response.output_tokens == 8


@pytest.mark.parametrize(
    "status,content", [(500, b'{"error":"failed"}'), (200, b"invalid-json"), (200, b"[]")]
)
def test_invalid_http_responses_become_provider_errors(status: int, content: bytes) -> None:
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(status, content=content))
        ) as client,
        OllamaProvider(client=client) as provider,
        pytest.raises(ProviderResponseError),
    ):
        provider.models()


def test_timeout_and_output_schema_are_sent_to_transport(
    model_binding: ModelBinding, inference_profile: InferenceProfile
) -> None:
    schema = {"type": "object"}

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.extensions["timeout"]["read"] == 0.5
        assert json.loads(request.content)["format"] == schema
        return httpx.Response(
            200, json={"model": model_binding.model_name, "response": "{}", "done": True}
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as client,
        OllamaProvider(client=client) as provider,
    ):
        provider.generate(
            model=model_binding,
            inference=inference_profile,
            request=GenerationRequest(
                prompt="Question",
                max_output_tokens=8,
                timeout_seconds=0.5,
                output_schema=schema,
            ),
        )


def test_closed_provider_cannot_reuse_a_borrowed_client(
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
) -> None:
    client, _ = ollama_fixture
    provider = OllamaProvider(client=client)
    provider.close()
    assert client.is_closed is False
    with pytest.raises(ProviderUnavailableError, match="closed"):
        provider.models()


def test_network_error_becomes_provider_unavailable() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as client,
        OllamaProvider(client=client) as provider,
        pytest.raises(ProviderUnavailableError, match="Cannot reach"),
    ):
        provider.models()
