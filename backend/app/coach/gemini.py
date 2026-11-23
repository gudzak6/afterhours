"""Gemini is the only model client. A failed call is returned as an error."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.config import Settings
from app.security import redact_secrets

logger = logging.getLogger(__name__)

_THINKING = {
    "none": "MINIMAL",
    "minimal": "MINIMAL",
    "low": "LOW",
    "medium": "MEDIUM",
    "high": "HIGH",
}


def gemini_configured(settings: Settings) -> bool:
    return bool(settings.gemini_api_key.strip())


def complete_messages(
    settings: Settings,
    *,
    model: str,
    messages: list[dict],
    response_format: dict | None = None,
    reasoning_effort: str = "high",
    timeout: float = 180.0,
) -> str:
    """Return the model's text. Structured callers pass the existing JSON schema."""
    system, contents = _contents(messages)
    schema = None
    if response_format is not None:
        schema = response_format.get("json_schema", {}).get("schema")
    response = _generate(
        settings,
        model=model,
        system=system,
        contents=contents,
        schema=schema,
        tools=None,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
    )
    return _text(response)


def run_tool_chat(
    settings: Settings,
    *,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
    run_tool,
    reasoning_effort: str = "low",
    timeout: float = 120.0,
) -> tuple[str, list[dict]]:
    """Continue a chat for at most six tool rounds. Tools are the app's existing definitions."""
    from google.genai import types

    contents = _contents(messages)[1]
    trace: list[dict] = []
    reply = ""
    declarations = _declarations(tools)
    for _round in range(6):
        response = _generate(
            settings,
            model=model,
            system=system,
            contents=contents,
            schema=None,
            tools=declarations,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
        calls = list(response.function_calls or [])
        if not calls:
            reply = _text(response)
            break
        content = response.candidates[0].content if response.candidates else None
        if content is not None:
            contents.append(content)
        parts = []
        for call in calls:
            arguments = dict(call.args or {})
            try:
                result = run_tool(call.name, arguments)
            except Exception as exc:
                result = {"error": redact_secrets(str(exc))}
            trace.append({"name": call.name, "arguments": arguments})
            payload = result if isinstance(result, dict) else {"result": result}
            payload = json.loads(json.dumps(payload, default=str))
            parts.append(types.Part.from_function_response(name=call.name, response=payload))
        contents.append(types.Content(role="tool", parts=parts))
    return reply, trace


def _generate(
    settings: Settings,
    *,
    model: str,
    system: str,
    contents: list,
    schema: dict | None,
    tools: list | None,
    reasoning_effort: str,
    timeout: float,
):
    if not gemini_configured(settings):
        raise RuntimeError("gemini_not_configured")
    client = _client(settings, timeout)
    attempts = [reasoning_effort]
    if reasoning_effort != "none":
        attempts.append("none")
    last_error: Exception | None = None
    for index, effort in enumerate(attempts):
        started = time.perf_counter()
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=_config(system, schema, tools, effort),
            )
        except Exception as exc:
            last_error = exc
            if index == 0 and _thinking_rejected(exc):
                logger.info(
                    "Gemini model %s rejected thinking level %s; retrying the same model",
                    model,
                    reasoning_effort,
                )
                continue
            _log_failure(model, exc, started)
            _raise_clear(exc, model)
        _log_success(model, response, started)
        return response
    _raise_clear(last_error or RuntimeError("gemini returned no response"), model)


def _client(settings: Settings, timeout: float):
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(
            api_version="v1beta",
            timeout=int(timeout * 1000),
            retry_options=types.HttpRetryOptions(
                attempts=4,
                initial_delay=1.0,
                max_delay=20.0,
                http_status_codes=[408, 429, 500, 502, 503, 504],
            ),
        ),
    )


def _config(system: str, schema: dict | None, tools: list | None, reasoning_effort: str):
    from google.genai import types

    config: dict[str, Any] = {
        "system_instruction": system or None,
        "max_output_tokens": 16384,
    }
    if reasoning_effort != "none":
        level = _THINKING.get(reasoning_effort, "HIGH")
        config["thinking_config"] = types.ThinkingConfig(thinking_level=types.ThinkingLevel[level])
    if schema is not None:
        config["response_mime_type"] = "application/json"
        config["response_json_schema"] = _json_schema(schema)
    if tools:
        config["tools"] = tools
    return types.GenerateContentConfig(**config)


def _contents(messages: list[dict]) -> tuple[str, list]:
    from google.genai import types

    system: list[str] = []
    contents = []
    for message in messages:
        content = str(message.get("content") or "")
        role = message.get("role")
        if role == "system":
            if content:
                system.append(content)
            continue
        model_role = "model" if role == "assistant" else "user"
        contents.append(types.Content(role=model_role, parts=[types.Part.from_text(text=content)]))
    if not contents:
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text="Continue.")]))
    return "\n\n".join(system), contents


def _declarations(tools: list[dict]) -> list:
    from google.genai import types

    functions = []
    for tool in tools:
        function = tool["function"]
        functions.append(
            types.FunctionDeclaration(
                name=function["name"],
                description=function["description"],
                parameters_json_schema=_json_schema(function["parameters"]),
            )
        )
    return [types.Tool(function_declarations=functions)]


def _json_schema(schema: dict) -> dict:
    """Copy a JSON schema into the subset Gemini accepts. The app schema stays unchanged."""
    cleaned: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "additionalProperties":
            continue
        if isinstance(value, dict):
            cleaned[key] = _json_schema(value)
        elif isinstance(value, list):
            cleaned[key] = [_json_schema(item) if isinstance(item, dict) else item for item in value]
        else:
            cleaned[key] = value
    return cleaned


def _text(response) -> str:
    text = getattr(response, "text", None)
    return text if isinstance(text, str) else ""


def _thinking_rejected(exc: Exception) -> bool:
    text = str(exc).lower()
    return "thinking" in text and any(word in text for word in ("unsupported", "not supported", "invalid", "cannot"))


def _usage(response) -> tuple[int | None, int | None, int | None, int | None]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None, None, None, None
    return (
        getattr(usage, "prompt_token_count", None),
        getattr(usage, "candidates_token_count", None),
        getattr(usage, "thoughts_token_count", None),
        getattr(usage, "total_token_count", None),
    )


def _log_success(model: str, response, started: float) -> None:
    prompt, output, thoughts, total = _usage(response)
    logger.info(
        "Gemini response model=%s latency_ms=%s prompt_tokens=%s output_tokens=%s thought_tokens=%s total_tokens=%s",
        model,
        int((time.perf_counter() - started) * 1000),
        prompt,
        output,
        thoughts,
        total,
    )


def _log_failure(model: str, exc: Exception, started: float) -> None:
    logger.error(
        "Gemini error model=%s latency_ms=%s error=%s",
        model,
        int((time.perf_counter() - started) * 1000),
        redact_secrets(f"{exc.__class__.__name__}: {exc}"),
    )


def _raise_clear(exc: Exception, model: str) -> None:
    text = redact_secrets(f"{exc.__class__.__name__}: {exc}")
    lowered = text.lower()
    if "429" in text or "rate" in lowered or "resource_exhausted" in lowered:
        raise RuntimeError(
            f"gemini_rate_limited: Gemini model {model} was rate limited after retries. No other model was used. {text}"
        ) from exc
    if "timeout" in lowered or "timed out" in lowered:
        raise RuntimeError(f"gemini_timeout: Gemini model {model} timed out. No other model was used. {text}") from exc
    raise RuntimeError(f"gemini_unavailable: Gemini model {model} did not respond. No other model was used. {text}") from exc
