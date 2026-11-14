"""Client factory with the safety defaults this app needs."""

from __future__ import annotations

import os
from typing import Any

from .llm import AIClient, AIConfig
from .redact import redact

HOSTED = {"anthropic", "openai"}


class GuardedClient:
    """Wraps :class:`AIClient` and redacts prompts before they are sent."""

    def __init__(self, client: AIClient, redact_input: bool):
        self.client = client
        self.redact_input = redact_input

    @property
    def label(self) -> str:
        return self.client.label + (" · redacted" if self.redact_input else "")

    def complete(self, system: str, user: str, schema: dict[str, Any] | None = None, schema_name: str = "result") -> Any:
        if self.redact_input:
            user = redact(user)
        return self.client.complete(system, user, schema=schema, schema_name=schema_name)


def make_client(redact_input: bool | None = None, env: dict[str, str] | None = None) -> GuardedClient:
    """Build a client from the environment.

    Redaction defaults to ON for hosted providers and OFF for local ones;
    override with ``INCIDENT_REDACT=0/1`` or the argument.
    """
    env = dict(os.environ if env is None else env)
    client = AIClient(AIConfig.from_env(env))
    if redact_input is None:
        flag = env.get("INCIDENT_REDACT")
        redact_input = (flag == "1") if flag in {"0", "1"} else client.config.provider in HOSTED
    return GuardedClient(client, redact_input)


def output_language(env: dict[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return env.get("AI_LANGUAGE", "Italian")
