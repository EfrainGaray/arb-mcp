"""LlmPort adapter over any OpenAI-compatible chat endpoint.

Works against a local llama-server, or any gateway that speaks the same
protocol — the bank picks the backend by environment, the code commits to no
vendor. The spec's node and relation types are pushed into the prompt as the
contract, and the model is told to answer with a single JSON object holding
only nodes/relations/views. Whatever comes back is still validated upstream by
the use case; this adapter only has to return parsed JSON or fail loudly.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

_SYSTEM = (
    "You are an architecture assistant. Turn the described system into a C4 model. "
    "Answer with a SINGLE JSON object and nothing else, with exactly these keys: "
    '"nodes", "relations", "views". Do not include a "spec" key. '
    "Each node: {id, type, name, description, and technology when the type is a container}. "
    "Node types allowed: person, softwareSystem, container, component, deploymentNode, "
    "infrastructureNode, decision. Nest children under a node's \"nodes\" array. "
    'Each relation: {from, to, type, description, technology} where type is "uses". '
    "ids are lowercase slugs."
)


class OpenAICompatibleLlm:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 120.0):
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._key = api_key
        self._timeout = timeout

    def draft_design(self, description: str, stories: list[str]) -> dict[str, Any]:
        user = description
        if stories:
            user += "\n\nUser stories:\n" + "\n".join(f"- {s}" for s in stories)
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self._key}"} if self._key else {}),
            },
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
            body = json.loads(resp.read())
        content = body["choices"][0]["message"]["content"]
        draft: dict[str, Any] = json.loads(content)
        return draft


def from_env() -> OpenAICompatibleLlm:
    """Build the adapter from ARB_LLM_BASE_URL / ARB_LLM_MODEL / ARB_LLM_API_KEY."""
    base = os.environ.get("ARB_LLM_BASE_URL")
    model = os.environ.get("ARB_LLM_MODEL")
    if not base or not model:
        raise RuntimeError(
            "generation needs ARB_LLM_BASE_URL and ARB_LLM_MODEL in the environment"
        )
    return OpenAICompatibleLlm(base, model, os.environ.get("ARB_LLM_API_KEY", ""))
