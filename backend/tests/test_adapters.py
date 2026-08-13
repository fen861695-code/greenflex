from datetime import datetime, timezone
UTC = timezone.utc

import httpx
import respx

from greenflex.adapters import OllamaInferenceProvider, _parse_nvidia_smi_line
from greenflex.ports import GenerationRequest


@respx.mock
async def test_ollama_adapter_lists_models_and_generates() -> None:
    respx.get("http://127.0.0.1:11434/api/tags").mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "qwen2.5:0.5b",
                        "digest": "sha256:fixture-digest",
                    }
                ]
            },
        )
    )
    generate_route = respx.post("http://127.0.0.1:11434/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": "synthetic-result",
                "prompt_eval_count": 7,
                "eval_count": 11,
                "total_duration": 1_250_000_000,
            },
        )
    )
    provider = OllamaInferenceProvider("http://127.0.0.1:11434")

    assert await provider.available_models() == {"qwen2.5:0.5b": "sha256:fixture-digest"}
    result = await provider.generate(
        GenerationRequest(
            model_name="qwen2.5:0.5b",
            prompt="synthetic-input",
            system_prompt=None,
            max_output_tokens=32,
        )
    )

    assert result.output == "synthetic-result"
    assert result.prompt_tokens == 7
    assert result.output_tokens == 11
    assert result.duration_us == 1_250_000
    assert generate_route.calls.last.request.content.find(b"synthetic-input") >= 0


@respx.mock
async def test_ollama_adapter_degrades_when_runtime_is_offline() -> None:
    respx.get("http://127.0.0.1:11434/api/tags").mock(side_effect=httpx.ConnectError("offline"))
    provider = OllamaInferenceProvider("http://127.0.0.1:11434")
    assert await provider.available_models() == {}


def test_nvidia_smi_parser_normalizes_units() -> None:
    sample = _parse_nvidia_smi_line("42.75, 63, 1024\n")
    assert sample is not None
    assert sample.captured_at.tzinfo == UTC
    assert sample.captured_at <= datetime.now(UTC)
    assert sample.power_mw == 42_750
    assert sample.utilization_bps == 6_300
    assert sample.memory_used_mb == 1_024
    assert _parse_nvidia_smi_line("not supported, 0, 0") is None
