from __future__ import annotations

import asyncio
import contextlib
import shutil
import statistics
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import httpx

from greenflex.domain import DomainError
from greenflex.ports import GenerationRequest, GenerationResult, PowerSample


class OllamaInferenceProvider:
    def __init__(
        self,
        base_url: str,
        *,
        connect_timeout_seconds: float = 1.0,
        request_timeout_seconds: float = 300.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(
            request_timeout_seconds,
            connect=connect_timeout_seconds,
        )

    async def available_models(self) -> dict[str, str]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return {}

        models = payload.get("models", []) if isinstance(payload, dict) else []
        available: dict[str, str] = {}
        for item in models:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("model")
            digest = item.get("digest")
            if isinstance(name, str):
                available[name] = digest if isinstance(digest, str) else "installed"
        return available

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload: dict[str, Any] = {
            "model": request.model_name,
            "prompt": request.prompt,
            "stream": False,
            "keep_alive": "5m",
            "options": {
                "num_predict": request.max_output_tokens,
                "temperature": request.temperature,
            },
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(f"{self._base_url}/api/generate", json=payload)
                response.raise_for_status()
                result = response.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise DomainError("inference_unavailable", "无法连接本地 Ollama 服务。", 503) from exc
        except httpx.TimeoutException as exc:
            raise DomainError("inference_timeout", "本地模型推理超时, 请稍后重试。", 504) from exc
        except httpx.HTTPStatusError as exc:
            status = 503 if exc.response.status_code >= 500 else 422
            raise DomainError("inference_failed", "本地模型未能完成推理。", status) from exc
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DomainError("inference_unavailable", "无法连接本地 Ollama 服务。", 503) from exc

        output = result.get("response") if isinstance(result, dict) else None
        if not isinstance(output, str):
            raise DomainError("invalid_inference_response", "本地模型返回了无效结果。", 502)
        return GenerationResult(
            output=output,
            prompt_tokens=_non_negative_int(result.get("prompt_eval_count")),
            output_tokens=_non_negative_int(result.get("eval_count")),
            duration_us=_nanoseconds_to_microseconds(result.get("total_duration")),
        )


class NvidiaSmiTelemetryProvider:
    source = "nvidia-smi"

    def __init__(self, *, interval_ms: int = 500, gpu_index: int = 0) -> None:
        self._interval_ms = interval_ms
        self._gpu_index = gpu_index
        self._executable = shutil.which("nvidia-smi")

    async def idle_power_mw(self, duration_seconds: float = 3.0) -> int | None:
        values: list[int] = []
        iterator = self.samples()
        deadline = asyncio.get_running_loop().time() + duration_seconds
        try:
            while asyncio.get_running_loop().time() < deadline:
                remaining = max(0.1, deadline - asyncio.get_running_loop().time())
                try:
                    sample = await asyncio.wait_for(anext(iterator), timeout=remaining)
                except (TimeoutError, StopAsyncIteration):
                    break
                values.append(sample.power_mw)
        finally:
            await iterator.aclose()
        return int(statistics.median(values)) if values else None

    async def samples(self) -> AsyncGenerator[PowerSample]:
        if self._executable is None:
            return
        process = await asyncio.create_subprocess_exec(
            self._executable,
            f"--id={self._gpu_index}",
            "--query-gpu=power.draw,utilization.gpu,memory.used",
            "--format=csv,noheader,nounits",
            f"--loop-ms={self._interval_ms}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            if process.stdout is None:
                return
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                parsed = _parse_nvidia_smi_line(line.decode("utf-8", errors="replace"))
                if parsed is not None:
                    yield parsed
        finally:
            if process.returncode is None:
                process.terminate()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(process.wait(), timeout=2)
                if process.returncode is None:
                    process.kill()
                    await process.wait()


def _parse_nvidia_smi_line(line: str) -> PowerSample | None:
    parts = [part.strip() for part in line.split(",")]
    if len(parts) != 3:
        return None
    try:
        power_mw = round(float(parts[0]) * 1_000)
        utilization_bps = round(float(parts[1]) * 100)
        memory_used_mb = round(float(parts[2]))
    except ValueError:
        return None
    return PowerSample(
        captured_at=datetime.now(UTC),
        power_mw=max(0, power_mw),
        utilization_bps=max(0, min(10_000, utilization_bps)),
        memory_used_mb=max(0, memory_used_mb),
    )


def _non_negative_int(value: object) -> int:
    return max(0, value) if isinstance(value, int) else 0


def _nanoseconds_to_microseconds(value: object) -> int:
    return max(1, value // 1_000) if isinstance(value, int) and value > 0 else 1
