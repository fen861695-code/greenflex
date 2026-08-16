"""
End-to-end verification for usage document.
Runs real API calls and saves verified results.
"""
import json
import urllib.request
import urllib.error
import time

BASE = "http://127.0.0.1:8000"

def api(method, path, body=None, headers=None):
    url = BASE + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    h = {"Content-Type": "application/json"}
    if headers: h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))

results = {}

# 1. Model catalog
s, models = api("GET", "/api/v1/models")
enabled = [m for m in models if m["enabled"]]
disabled = [m for m in models if not m["enabled"]]
results["model_catalog"] = {
    "total": len(models),
    "enabled": len(enabled),
    "disabled": len(disabled),
    "local": len([m for m in models if not m.get("is_cloud_model")]),
    "cloud": len([m for m in models if m.get("is_cloud_model")]),
    "all_have_data_source": all(m.get("official_data_source") for m in models),
    "disabled_ids": [m["id"] for m in disabled],
}

# 2. Smart recommendations for 8 representative user prompts
prompts = [
    ("帮我把这些评论分一下好评和差评", "二分类，经济档"),
    ("用Python写一个连接MySQL的连接池工具类", "代码生成，质量档"),
    ("写一份详细的项目计划书，要有数据支撑", "长文生成，质量档"),
    ("帮我总结一下这篇文章的要点", "摘要，均衡档"),
    ("深度分析全球芯片产业链竞争格局，给董事会汇报", "深度分析，企业档"),
    ("中译英：本合同自签字之日起生效", "翻译，经济档"),
    ("从合同中提取甲方、乙方、金额、日期", "信息抽取，经济档"),
    ("你好", "模糊输入，低置信度"),
]
rec_results = []
for prompt, desc in prompts:
    s, r = api("POST", "/api/v1/recommendations", {
        "mode": "smart", "task_type": "auto",
        "prompt_preview": prompt,
        "quality_requirement": "standard",
        "execution_mode": "immediate",
    })
    tu = r.get("task_understanding", {})
    rec_results.append({
        "prompt": prompt,
        "expected": desc,
        "task_type": tu.get("task_type_label", "?"),
        "tier": r.get("recommended_tier", "?"),
        "model": r.get("recommended_model_name", "?"),
        "price_rmb": r.get("estimated_price_rmb", 0),
        "energy_wh": r.get("estimated_energy_wh", 0),
        "carbon_g": r.get("estimated_carbon_g", 0),
        "confidence": tu.get("confidence_label", "?"),
        "alternatives_count": len(r.get("alternatives", [])),
    })
results["recommendations"] = rec_results

# 3. AI Chat (simulated)
s, chat = api("POST", "/api/v1/chat", {
    "model_id": "gemma3-1b-q4",
    "messages": [{"role": "user", "content": "什么是绿色算力？"}],
})
results["chat"] = {
    "status": s,
    "model": chat.get("model_name"),
    "reply": chat.get("reply"),
    "prompt_tokens": chat.get("prompt_tokens"),
    "completion_tokens": chat.get("completion_tokens"),
    "duration_ms": chat.get("duration_ms"),
    "price_micro_rmb": chat.get("estimated_price_micro_rmb"),
    "energy_micro_wh": chat.get("estimated_energy_micro_wh"),
    "carbon_micro_g": chat.get("estimated_carbon_micro_g"),
    "source": chat.get("inference_source"),
}

# 4. Model preview/comparison
s, prev = api("POST", "/api/v1/previews", {
    "model_id": "gemma3-1b-q4",
    "prompt": "用一句话解释机器学习",
    "max_output_tokens": 64,
})
results["preview"] = {
    "status": s,
    "latency_ms": prev.get("latency_ms"),
    "output": prev.get("output"),
    "output_tokens": prev.get("output_tokens"),
    "gross_gpu_energy_wh": prev.get("gross_gpu_energy_wh"),
    "joules_per_token": prev.get("joules_per_output_token"),
    "source": prev.get("inference_source"),
}

# 5. Carbon signals
s, regions = api("GET", "/api/v1/signals/regions")
s2, cal = api("GET", "/api/v1/signals/calendar?region=CN-East&days=7")
results["carbon_signals"] = {
    "regions": len(regions.get("regions", [])),
    "region_names": [r["name_zh"] for r in regions.get("regions", [])],
    "calendar_hours": len(cal) if isinstance(cal, list) else 0,
    "east_china_carbon": next((r["carbon_g_per_kwh"] for r in regions.get("regions",[]) if r["code"]=="CN-East"), None),
}

# 6. Security verification
s, r1 = api("POST", "/api/v1/chat", {"model_id": "fake-model", "messages": [{"role":"user","content":"hi"}]})
s, r2 = api("PUT", "/api/v1/settings/cloud-api", {"openai_api_key": "sk-test"})
s, r3 = api("PUT", "/api/v1/settings/cloud-api", {"openai_api_key": "sk-test"}, {"X-Admin-Token": "wrong"})
s, r4 = api("POST", "/api/v1/previews", {"model_id": "qwen2.5-0.5b-q4", "prompt": "test", "max_output_tokens": 64})
results["security"] = {
    "invalid_model_returns_404": r1.get("code") == "model_not_found",
    "no_token_returns_401": r2.get("code") == "admin_token_required",
    "wrong_token_returns_401": r3.get("code") in ("admin_token_required", "admin_token_invalid"),
    "disabled_model_returns_404": r4.get("code") in ("model_not_found", "model_not_available"),
}

# 7. Quote flow
s, quote = api("POST", "/api/v1/quotes", {
    "items": [{"client_item_id": "item-1", "prompt": "总结这篇文章", "max_output_tokens": 256}],
})
results["quote"] = {
    "status": s,
    "quote_id": quote.get("quote_id", "?")[:8] + "...",
    "total_price_rmb": quote.get("total_price_micro_rmb", 0) / 1_000_000,
    "total_energy_wh": quote.get("total_energy_micro_wh", 0) / 1_000_000,
    "total_carbon_g": quote.get("total_carbon_micro_g", 0) / 1_000_000,
}

with open("D:/GreenFlex/backend/e2e_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(json.dumps(results, ensure_ascii=False, indent=2))
