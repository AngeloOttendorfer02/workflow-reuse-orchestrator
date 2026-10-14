"""Ollama transport, model fingerprint verification, and generation telemetry."""

import hashlib
import math
from time import perf_counter
from types import TracebackType
from typing import Any, Self

import httpx

from workflow_reuse_orchestrator.domain.providers import (
    GenerationRequest,
    GenerationResponse,
    InferenceProfile,
    ModelBinding,
    ProviderResponseError,
    ProviderUnavailableError,
)
from workflow_reuse_orchestrator.storage import canonical_sha256


class OllamaProvider:
    """Reuse one HTTP client; injected clients remain owned by their caller."""

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        url = httpx.URL(base_url)
        if url.scheme not in ("http", "https") or not url.host:
            raise ValueError("Ollama base URL must be an absolute HTTP or HTTPS URL.")
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("Ollama timeout must be finite and positive.")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=timeout_seconds)
        self._closed = False

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if self._closed:
            raise ProviderUnavailableError("Ollama provider is closed.")
        timeout = self._timeout if timeout_seconds is None else min(self._timeout, timeout_seconds)
        try:
            response = self._client.request(
                method, f"{self._base_url}{endpoint}", json=payload, timeout=timeout
            )
        except httpx.RequestError as exc:
            raise ProviderUnavailableError(
                f"Cannot reach Ollama at {self._base_url}: {exc}"
            ) from exc
        if response.is_error:
            raise ProviderResponseError(
                f"Ollama {endpoint} returned HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            value = response.json()
        except ValueError as exc:
            raise ProviderResponseError(f"Ollama {endpoint} returned invalid JSON.") from exc
        if not isinstance(value, dict):
            raise ProviderResponseError(f"Ollama {endpoint} must return a JSON object.")
        if value.get("error"):
            raise ProviderResponseError(f"Ollama {endpoint}: {str(value['error'])[:500]}")
        return value

    def version(self) -> str:
        value = self._request("GET", "/api/version").get("version")
        if not isinstance(value, str) or not value.strip():
            raise ProviderResponseError("Ollama version response is incomplete.")
        return value

    def models(self) -> list[dict[str, str]]:
        value = self._request("GET", "/api/tags").get("models")
        if not isinstance(value, list):
            raise ProviderResponseError("Ollama model list is incomplete.")
        installed: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                raise ProviderResponseError("Ollama model entries must be objects.")
            name = item.get("name")
            digest = item.get("digest")
            if not isinstance(name, str) or not name.strip() or not isinstance(digest, str):
                raise ProviderResponseError("Ollama model entry lacks its name or digest.")
            digest = digest.removeprefix("sha256:")
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ProviderResponseError("Ollama returned an invalid model digest.")
            installed.append({"name": name, "digest": digest})
        if len({item["name"] for item in installed}) != len(installed):
            raise ProviderResponseError("Ollama returned duplicate model names.")
        return sorted(installed, key=lambda item: item["name"])

    def inspect_model(self, model_name: str) -> ModelBinding:
        """Fingerprint the exact installed name, tokenizer, template, and defaults."""
        installed = {item["name"]: item["digest"] for item in self.models()}
        if model_name not in installed:
            raise ProviderResponseError(
                f"Model {model_name!r} is not installed. Choose an exact name from runtime models."
            )
        version = self.version()
        value = self._request("POST", "/api/show", payload={"model": model_name, "verbose": True})
        info = value.get("model_info")
        if not isinstance(info, dict):
            raise ProviderResponseError("Model response lacks model_info.")
        architecture = info.get("general.architecture")
        context = info.get(f"{architecture}.context_length")
        if not isinstance(architecture, str) or type(context) is not int or context < 1:
            raise ProviderResponseError("Model response lacks a native context length.")
        tokenizer = {key: item for key, item in info.items() if key.startswith("tokenizer.")}
        vocabulary = tokenizer.get("tokenizer.ggml.tokens")
        if (
            not isinstance(vocabulary, list)
            or not vocabulary
            or not all(isinstance(token, str) for token in vocabulary)
        ):
            raise ProviderResponseError("Verbose model response lacks the tokenizer vocabulary.")
        template = value.get("template")
        if not isinstance(template, str) or not template.strip():
            raise ProviderResponseError("Model response lacks a prompt template.")
        # Check that the tag did not change while its metadata was being read.
        current = {item["name"]: item["digest"] for item in self.models()}
        if current.get(model_name) != installed[model_name]:
            raise ProviderResponseError("Model digest changed during inspection.")
        return ModelBinding(
            model_name=model_name,
            model_digest=installed[model_name],
            ollama_version=version,
            native_context_tokens=context,
            tokenizer_sha256=canonical_sha256(tokenizer),
            template_sha256=hashlib.sha256(template.encode("utf-8")).hexdigest(),
            model_metadata_sha256=canonical_sha256(
                {
                    "model_info": info,
                    "template": template,
                    "system": value.get("system", ""),
                    "parameters": value.get("parameters", ""),
                    "capabilities": value.get("capabilities", []),
                }
            ),
        )

    def verify_model(self, expected: ModelBinding) -> None:
        if self.inspect_model(expected.model_name) != expected:
            raise ProviderResponseError("The installed model or runtime differs from its binding.")

    def generate(
        self,
        *,
        model: ModelBinding,
        inference: InferenceProfile,
        request: GenerationRequest,
    ) -> GenerationResponse:
        if inference.num_ctx > model.native_context_tokens:
            raise ValueError("Inference context exceeds the model's native context.")
        if request.max_output_tokens > inference.num_predict:
            raise ValueError("Requested output exceeds the bound inference profile.")
        options = inference.model_dump(exclude={"think", "keep_alive"})
        options["num_predict"] = request.max_output_tokens
        payload: dict[str, Any] = {
            "model": model.model_name,
            "prompt": request.prompt,
            "stream": False,
            "think": inference.think,
            "keep_alive": inference.keep_alive,
            "options": options,
        }
        if request.output_schema is not None:
            payload["format"] = request.output_schema
        started = perf_counter()
        value = self._request(
            "POST", "/api/generate", payload=payload, timeout_seconds=request.timeout_seconds
        )
        wall_seconds = perf_counter() - started
        if value.get("done") is not True:
            raise ProviderResponseError("Ollama returned an incomplete generation.")
        if value.get("model") != model.model_name:
            raise ProviderResponseError("Ollama returned output from a different model name.")
        if value.get("thinking"):
            raise ProviderResponseError("Ollama returned thinking output despite think=false.")
        output = value.get("response")
        reason = value.get("done_reason")
        if not isinstance(output, str) or (not output.strip() and reason != "length"):
            raise ProviderResponseError("Ollama returned no generated text.")
        if reason is not None and not isinstance(reason, str):
            raise ProviderResponseError("Ollama returned an invalid completion reason.")
        return GenerationResponse(
            output_text=output,
            wall_seconds=wall_seconds,
            input_tokens=_token_count(value.get("prompt_eval_count")),
            output_tokens=_token_count(value.get("eval_count")),
            finish_reason=reason,
            provider_total_seconds=_duration_seconds(value.get("total_duration")),
            model_load_seconds=_duration_seconds(value.get("load_duration")),
            prompt_eval_seconds=_duration_seconds(value.get("prompt_eval_duration")),
            generation_seconds=_duration_seconds(value.get("eval_duration")),
        )

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            if self._owns_client:
                self._client.close()

    def __enter__(self) -> Self:
        if self._closed:
            raise ProviderUnavailableError("Ollama provider is closed.")
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _token_count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _duration_seconds(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return None
    try:
        seconds = float(value) / 1_000_000_000.0
    except OverflowError:
        return None
    return seconds if math.isfinite(seconds) else None
