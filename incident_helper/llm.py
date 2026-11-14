"""Provider-agnostic LLM client (same as aikit.client in ai-devops-starter-kit).

One function, one contract: give it a system prompt, a user prompt and
(optionally) a JSON schema; get back text or a dict that matches the schema.

Configuration is read from the environment so the same code runs against a
hosted API in CI and against a model on your own hardware:

    AI_PROVIDER   anthropic | openai | local | fake        (default: anthropic)
    AI_MODEL      model id; required for openai and local
    AI_BASE_URL   OpenAI-compatible endpoint for "local"
                  (llama.cpp server, vLLM, Ollama, LM Studio...)
    AI_API_KEY    key for "local" if the server wants one (default: "none")
    AI_MAX_TOKENS output token budget (default: 8000)

Provider keys use their usual names: ANTHROPIC_API_KEY, OPENAI_API_KEY.

No model id is hard-coded for OpenAI or local servers on purpose: the 2025
version of this kit pinned gpt-3.5-turbo / gpt-4 in code and stopped working
when those models were shut down on 23 October 2026.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"


class AIConfigError(RuntimeError):
    """Raised when the environment does not describe a usable provider."""


class AIResponseError(RuntimeError):
    """Raised when the model answer cannot be turned into the requested shape."""


@dataclass
class AIConfig:
    provider: str = "anthropic"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    max_tokens: int = 8000

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> AIConfig:
        env = dict(os.environ if env is None else env)
        provider = env.get("AI_PROVIDER", "anthropic").strip().lower()
        if provider not in {"anthropic", "openai", "local", "fake"}:
            raise AIConfigError(f"AI_PROVIDER={provider!r} is not supported (use anthropic, openai, local or fake)")
        model = env.get("AI_MODEL") or None
        if provider == "anthropic" and not model:
            model = DEFAULT_ANTHROPIC_MODEL
        if provider in {"openai", "local"} and not model:
            raise AIConfigError(f"AI_MODEL must be set when AI_PROVIDER={provider} (model ids change; this kit does not guess them)")
        base_url = env.get("AI_BASE_URL") or None
        if provider == "local" and not base_url:
            raise AIConfigError(
                "AI_BASE_URL must point at an OpenAI-compatible server when AI_PROVIDER=local, e.g. http://nero.local:8080/v1"
            )
        try:
            max_tokens = int(env.get("AI_MAX_TOKENS", "8000"))
        except ValueError as exc:
            raise AIConfigError("AI_MAX_TOKENS must be an integer") from exc
        return cls(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=env.get("AI_API_KEY") or None,
            max_tokens=max_tokens,
        )


def extract_json(text: str) -> Any:
    """Parse JSON from a model answer, tolerating code fences and chatter.

    Local models without grammar-constrained decoding sometimes wrap JSON in
    ```json fences or add a sentence before it.
    """
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise AIResponseError("model answer did not contain valid JSON")


def check_required(data: Any, schema: dict[str, Any], path: str = "$") -> None:
    """Light structural check: required keys and basic types, recursively.

    Hosted providers enforce the schema server-side; this guards the local
    fallback path without pulling in a jsonschema dependency.
    """
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(data, dict):
            raise AIResponseError(f"{path}: expected object")
        for key in schema.get("required", []):
            if key not in data:
                raise AIResponseError(f"{path}: missing key {key!r}")
        for key, sub in schema.get("properties", {}).items():
            if key in data:
                check_required(data[key], sub, f"{path}.{key}")
    elif expected == "array":
        if not isinstance(data, list):
            raise AIResponseError(f"{path}: expected array")
        for i, item in enumerate(data):
            check_required(item, schema.get("items", {}), f"{path}[{i}]")
    elif expected == "string" and not isinstance(data, str):
        raise AIResponseError(f"{path}: expected string")
    elif expected == "integer" and not (isinstance(data, int) and not isinstance(data, bool)):
        raise AIResponseError(f"{path}: expected integer")
    if "enum" in schema and data not in schema["enum"]:
        raise AIResponseError(f"{path}: {data!r} not in {schema['enum']}")


@dataclass
class AIClient:
    config: AIConfig
    # For tests and dry runs: a callable(system, user, schema) -> str | dict
    fake_responder: Callable[[str, str, dict | None], Any] | None = None
    _sdk: Any = field(default=None, init=False, repr=False)

    @classmethod
    def from_env(cls) -> AIClient:
        return cls(AIConfig.from_env())

    @property
    def label(self) -> str:
        return f"{self.config.provider}:{self.config.model or 'n/a'}"

    # -- public API -------------------------------------------------------
    def complete(
        self,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        schema_name: str = "result",
    ) -> Any:
        """Return text, or a dict matching ``schema`` when one is given."""
        provider = self.config.provider
        if provider == "fake":
            result = self._fake(system, user, schema)
        elif provider == "anthropic":
            result = self._anthropic(system, user, schema, schema_name)
        else:
            result = self._openai_compatible(system, user, schema, schema_name)
        if schema is not None:
            check_required(result, schema)
        return result

    # -- providers --------------------------------------------------------
    def _fake(self, system: str, user: str, schema: dict | None) -> Any:
        if self.fake_responder is None:
            raise AIConfigError("AI_PROVIDER=fake needs a fake_responder (tests only)")
        out = self.fake_responder(system, user, schema)
        if schema is not None and isinstance(out, str):
            return extract_json(out)
        return out

    def _anthropic(self, system: str, user: str, schema: dict | None, name: str) -> Any:
        if self._sdk is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - env specific
                raise AIConfigError("pip install anthropic") from exc
            self._sdk = anthropic.Anthropic()
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if schema is not None:
            # Forcing a single tool call is the most reliable way to get
            # schema-shaped output from the Messages API.
            kwargs["tools"] = [
                {
                    "name": name,
                    "description": "Return the result in this exact structure.",
                    "input_schema": schema,
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": name}
        msg = self._sdk.messages.create(**kwargs)
        if schema is not None:
            for block in msg.content:
                if getattr(block, "type", None) == "tool_use":
                    return block.input
            raise AIResponseError("model did not return the structured result")
        return "".join(getattr(b, "text", "") for b in msg.content).strip()

    def _openai_compatible(self, system: str, user: str, schema: dict | None, name: str) -> Any:
        if self._sdk is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - env specific
                raise AIConfigError("pip install openai") from exc
            if self.config.provider == "local":
                self._sdk = OpenAI(
                    base_url=self.config.base_url,
                    api_key=self.config.api_key or "none",
                )
            else:
                self._sdk = OpenAI(base_url=self.config.base_url)
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.config.provider == "local":
            kwargs["max_tokens"] = self.config.max_tokens
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": name, "schema": schema, "strict": True},
            }
        resp = self._sdk.chat.completions.create(**kwargs)
        text = (resp.choices[0].message.content or "").strip()
        if schema is None:
            return text
        return extract_json(text)


def strict_object(properties: dict[str, Any]) -> dict[str, Any]:
    """Build an object schema in the strict form every provider accepts:
    all properties required, no extras."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }
