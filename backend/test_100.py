"""
GreenFlex 100 例真实用户模拟测试
覆盖：7种任务类型 × 多种复杂度 × 批量规模 × 质量暗示 × 边界情况 × 安全测试
每例都有明确的验证规则，结果严格校验。
"""
import json
import urllib.request
import urllib.error
import time
import sys

BASE = "http://127.0.0.1:8000"

def api(method, path, body=None, headers=None):
    url = BASE + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}

# ─── 100 个测试用例 ───────────────────────────────────────────
# 格式: (id, 分类, 用户输入, 期望任务类型, 期望档位规则, 验证函数)
# 期望档位规则: "economy"/"balanced"/"quality"/"any"/"reject"

CASES = []

# ── 分类任务 (15例) ──
classification_cases = [
    ("判断这封邮件是不是垃圾邮件：恭喜您中奖100万", "economy"),
    ("帮我把这些评论分一下好评和差评", "economy"),
    ("判断这条消息是否包含色情内容", "economy"),
    ("把客服工单按紧急程度分类：紧急、一般、低", "balanced"),
    ("识别这些图片中哪些包含违规内容", "economy"),
    ("对1000条用户反馈做情感分析，正面负面中性", "economy"),
    ("判断这个用户是否有流失风险", "economy"),
    ("把简历按匹配度筛选，分成合适、待定、不合适", "balanced"),
    ("区分哪些是真实订单哪些是刷单", "economy"),
    ("判断这段话是不是AI生成的", "economy"),
    ("给这500条投诉打标签：物流、质量、服务、其他", "balanced"),
    ("识别文本中的敏感信息：手机号、身份证、银行卡", "economy"),
    ("判断这篇新闻是真实报道还是谣言", "economy"),
    ("把客户按消费等级分成VIP、普通、潜在", "balanced"),
    ("检测这段代码是否有安全漏洞", "quality"),
]
for i, (prompt, tier) in enumerate(classification_cases, 1):
    CASES.append((f"C{i:03d}", "分类判断", prompt, "classification", tier))

# ── 信息抽取 (10例) ──
extraction_cases = [
    ("从合同中提取甲方、乙方、金额、日期", "economy"),
    ("找出这篇文章中提到的所有人名和公司名", "economy"),
    ("提取发票上的开票日期、金额、税号", "economy"),
    ("从简历中抽取姓名、学历、工作年限、技能", "economy"),
    ("解析这个地址，提取省、市、区、街道", "economy"),
    ("从邮件中提取会议时间、地点、参会人", "economy"),
    ("抽取产品评论中提到的所有功能点", "economy"),
    ("从法律文书中提取判决结果和法律依据", "balanced"),
    ("从医疗报告中提取诊断结论和用药建议", "quality"),
    ("从100份合同中批量提取关键条款", "balanced"),
]
for i, (prompt, tier) in enumerate(extraction_cases, 1):
    CASES.append((f"E{i:03d}", "信息抽取", prompt, "extraction", tier))

# ── 摘要总结 (12例) ──
summarization_cases = [
    ("帮我总结一下这篇文章的要点", "balanced"),
    ("把这份20页的报告浓缩成500字摘要", "balanced"),
    ("概括一下今天的会议纪要", "balanced"),
    ("帮我梳理一下这篇论文的核心观点", "balanced"),
    ("总结这50条客户反馈的主要问题", "balanced"),
    ("把这段长文归纳成三个要点", "balanced"),
    ("给我一份本周工作周报的总结", "balanced"),
    ("提炼一下这份合同的关键条款", "balanced"),
    ("帮我汇总一下各部门的季度汇报", "balanced"),
    ("把这100条新闻标题整理成今日热点", "balanced"),
    ("总结一下这个产品的用户评价倾向", "balanced"),
    ("深度梳理这份行业白皮书的核心论据和结论", "quality"),
]
for i, (prompt, tier) in enumerate(summarization_cases, 1):
    CASES.append((f"S{i:03d}", "摘要总结", prompt, "summarization", tier))

# ── 内容生成 (15例) ──
generation_cases = [
    ("写一句产品宣传语", "balanced"),
    ("帮我写一封商务合作邮件", "balanced"),
    ("写一篇关于环保的公众号文章", "balanced"),
    ("生成10条社交媒体文案", "balanced"),
    ("帮我写一份产品发布会的演讲稿", "balanced"),
    ("写一个童话故事给小朋友听", "balanced"),
    ("帮我起草一份公司年会主持稿", "balanced"),
    ("写一份详细的项目计划书，要有数据支撑", "quality"),
    ("撰写一份给董事会的年度报告，务必严谨准确", "quality"),
    ("帮我写一篇深度技术博客，分析大模型推理优化", "quality"),
    ("写一份正式的法律函件，不能出错", "quality"),
    ("生成产品描述文案，50字以内", "balanced"),
    ("帮我写一封辞职信，语气要委婉", "balanced"),
    ("写一个短视频脚本，30秒", "balanced"),
    ("创作一首关于春天的诗", "balanced"),
]
for i, (prompt, tier) in enumerate(generation_cases, 1):
    CASES.append((f"G{i:03d}", "内容生成", prompt, "generation", tier))

# ── 分析推理 (12例) ──
analysis_cases = [
    ("分析一下这个月销售额下降的原因", "balanced"),
    ("对比这三个方案的优劣势", "balanced"),
    ("评估一下这个投资项目的风险", "balanced"),
    ("解释一下为什么代码运行变慢了", "balanced"),
    ("分析用户流失的可能原因", "balanced"),
    ("帮我看看这组数据有什么趋势", "balanced"),
    ("深度分析全球芯片产业链竞争格局，给董事会汇报", "quality"),
    ("评估这个架构设计的性能瓶颈和扩展性", "quality"),
    ("分析竞品策略并给出我们的应对建议，下周给老板汇报", "quality"),
    ("诊断一下这个系统频繁宕机的根本原因", "quality"),
    ("比较Python和Go在高并发场景下的表现", "balanced"),
    ("分析这个A/B测试结果是否显著", "balanced"),
]
for i, (prompt, tier) in enumerate(analysis_cases, 1):
    CASES.append((f"A{i:03d}", "分析推理", prompt, "analysis", tier))

# ── 代码编程 (12例) ──
code_cases = [
    ("用Python写一个快速排序", "quality"),
    ("帮我写一个Java单例模式", "quality"),
    ("用JavaScript实现防抖函数", "quality"),
    ("写一个SQL查询，找出连续3天登录的用户", "quality"),
    ("用Python写一个连接MySQL的连接池工具类", "quality"),
    ("帮我调试这段报错的代码：TypeError: cannot read property", "quality"),
    ("写一个Redis分布式锁的实现", "quality"),
    ("用Go写一个HTTP中间件，记录请求日志", "quality"),
    ("写一个正则表达式匹配邮箱地址", "balanced"),
    ("帮我写一个Dockerfile部署Node.js应用", "quality"),
    ("用React写一个带分页的表格组件", "quality"),
    ("写一个Python脚本批量重命名文件", "balanced"),
]
for i, (prompt, tier) in enumerate(code_cases, 1):
    CASES.append((f"P{i:03d}", "代码编程", prompt, "code", tier))

# ── 翻译 (8例) ──
translation_cases = [
    ("把这句话翻译成英文：我们公司致力于创新", "balanced"),
    ("翻译成日文：欢迎光临", "balanced"),
    ("把这段中文翻译成地道的英文商务邮件", "balanced"),
    ("中译英：本合同自签字之日起生效", "balanced"),
    ("把这份产品说明书翻译成英文和日文", "balanced"),
    ("翻译成法语：生日快乐", "balanced"),
    ("把这段技术文档翻译成中文", "balanced"),
    ("英译中：The quick brown fox jumps over the lazy dog", "balanced"),
]
for i, (prompt, tier) in enumerate(translation_cases, 1):
    CASES.append((f"T{i:03d}", "翻译", prompt, "translation", tier))

# ── 边界/模糊/混合 (10例) ──
edge_cases = [
    ("你好", "general", "balanced"),
    ("帮我弄一下", "general", "balanced"),
    ("在吗", "general", "balanced"),
    ("谢谢", "general", "balanced"),
    ("1+1等于几", "general", "balanced"),
    ("帮我写一份报告并翻译成英文", "multi", "balanced"),
    ("分析这些数据并生成图表，然后写总结", "multi", "balanced"),
    ("把这些评论分类并总结主要问题", "multi", "balanced"),
    ("提取关键信息后翻译成英文发给客户", "multi", "balanced"),
    ("写代码实现一个分类器，然后写文档说明", "multi", "balanced"),
]
for i, (prompt, expected_type, tier) in enumerate(edge_cases, 1):
    CASES.append((f"X{i:03d}", "边界/混合", prompt, expected_type, tier))

# ── 批量规模 (6例) ──
batch_cases = [
    ("帮我分类这10条评论", "classification", "economy"),
    ("总结这50条客服记录", "summarization", "balanced"),
    ("分析1000条用户评价的情感倾向", "classification", "economy"),
    ("把这200份简历按匹配度排序", "classification", "balanced"),
    ("批量翻译这300条产品描述", "translation", "balanced"),
    ("帮我处理一批数据，大概几十条", "general", "balanced"),
]
for i, (prompt, expected_type, tier) in enumerate(batch_cases, 1):
    CASES.append((f"B{i:03d}", "批量规模", prompt, expected_type, tier))

assert len(CASES) == 100, f"Expected 100 cases, got {len(CASES)}"

# ─── 验证规则 ───────────────────────────────────────────────
TIER_ORDER = {"economy": 0, "balanced": 1, "quality": 2, "enterprise": 3}

def validate(case, resp):
    """返回 (passed: bool, detail: str)"""
    cid, category, prompt, expected_type, expected_tier = case
    tu = resp.get("task_understanding") or {}
    actual_type = tu.get("task_type", "unknown")
    actual_tier = resp.get("recommended_tier", "unknown")
    model = resp.get("recommended_model_name", "?")
    price = float(resp.get("estimated_price_rmb", 0))
    energy = float(resp.get("estimated_energy_wh", 0))
    carbon = float(resp.get("estimated_carbon_g", 0))
    confidence = tu.get("confidence_label", "?")

    errors = []

    # 1. 任务类型验证
    if expected_type == "multi":
        # 混合任务：至少识别出一种非general类型
        intents = tu.get("detected_intents", [])
        non_general = [i for i in intents if i != "通用任务"]
        if len(non_general) < 1:
            errors.append(f"混合任务只识别到{intents}")
    elif expected_type == "general":
        if actual_type != "general":
            errors.append(f"模糊输入应识别为general，实际{actual_type}")
        if confidence != "低":
            errors.append(f"模糊输入置信度应为低，实际{confidence}")
    else:
        if actual_type != expected_type:
            errors.append(f"期望{expected_type}，实际{actual_type}")

    # 2. 档位验证（允许升档不允许降档）
    if expected_tier != "any":
        expected_level = TIER_ORDER.get(expected_tier, 1)
        actual_level = TIER_ORDER.get(actual_tier, 1)
        if actual_level < expected_level:
            errors.append(f"档位过低：期望>={expected_tier}，实际{actual_tier}")

    # 3. 数据合理性
    if price < 0:
        errors.append(f"费用为负: {price}")
    if energy < 0:
        errors.append(f"能耗为负: {energy}")
    if carbon < 0:
        errors.append(f"碳排为负: {carbon}")
    if price == 0 and model:
        errors.append("费用为0但有模型")
    if not model or model == "?":
        errors.append("未返回模型名称")

    # 4. 备选模型
    alts = resp.get("alternatives", [])
    if len(alts) < 5:
        errors.append(f"备选模型过少: {len(alts)}")

    passed = len(errors) == 0
    detail = f"类型={tu.get('task_type_label','?')} 档位={actual_tier} 模型={model[:20]} 费用=¥{price:.6f} 能耗={energy:.4f}Wh 置信={confidence}"
    if errors:
        detail += f" | 问题: {'; '.join(errors)}"
    return passed, detail


# ─── 执行测试 ───────────────────────────────────────────────
print("=" * 90)
print(f"GreenFlex 100 例真实用户模拟测试")
print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 90)

passed_count = 0
failed_count = 0
results = []
type_stats = {}
tier_stats = {}
start_time = time.time()

for idx, case in enumerate(CASES, 1):
    cid, category, prompt, expected_type, expected_tier = case
    status, resp = api("POST", "/api/v1/recommendations", {
        "mode": "smart",
        "task_type": "auto",
        "prompt_preview": prompt,
        "quality_requirement": "standard",
        "execution_mode": "immediate",
    })

    if status != 200:
        passed = False
        detail = f"HTTP {status}: {resp.get('code', resp.get('message', 'unknown error'))}"
    else:
        passed, detail = validate(case, resp)
        # stats
        tu = resp.get("task_understanding") or {}
        t = tu.get("task_type_label", "?")
        tier = resp.get("recommended_tier", "?")
        type_stats[t] = type_stats.get(t, 0) + 1
        tier_stats[tier] = tier_stats.get(tier, 0) + 1

    if passed:
        passed_count += 1
    else:
        failed_count += 1
    results.append((cid, category, prompt[:30], passed, detail))

    # Print progress every 10
    if idx % 10 == 0:
        print(f"  进度: {idx}/100 通过:{passed_count} 失败:{failed_count}")

elapsed = time.time() - start_time

# ── 安全测试 (额外10项) ──────────────────────────────────
print(f"\n{'─' * 90}")
print("安全与边界测试 (10项)")
print(f"{'─' * 90}")
security_tests = [
    ("空prompt", "POST", "/api/v1/recommendations", {"mode":"smart","task_type":"auto","prompt_preview":"","quality_requirement":"standard","execution_mode":"immediate"}, lambda s,r: s==200),
    ("超长prompt(10000字)", "POST", "/api/v1/recommendations", {"mode":"smart","task_type":"auto","prompt_preview":"测"*5000,"quality_requirement":"standard","execution_mode":"immediate"}, lambda s,r: s==200),
    ("无效模型对话", "POST", "/api/v1/chat", {"model_id":"fake-model","messages":[{"role":"user","content":"hi"}]}, lambda s,r: s==404),
    ("空消息对话", "POST", "/api/v1/chat", {"model_id":"gemma3-1b-q4","messages":[{"role":"user","content":""}]}, lambda s,r: s==422),
    ("无令牌改设置", "PUT", "/api/v1/settings/cloud-api", {"openai_api_key":"sk-test"}, lambda s,r: s==401),
    ("错误令牌改设置", "PUT", "/api/v1/settings/cloud-api", {"openai_api_key":"sk-test"}, lambda s,r: s==401),
    ("禁用模型试跑", "POST", "/api/v1/previews", {"model_id":"qwen2.5-0.5b-q4","prompt":"test","max_output_tokens":64}, lambda s,r: s==404),
    ("超量报价(>500条)", "POST", "/api/v1/quotes", {"items":[{"prompt":"test","max_output_tokens":64}]*600}, lambda s,r: s in (400,422)),
    ("模型列表完整", "GET", "/api/v1/models", None, lambda s,r: s==200 and len(r)>=35),
    ("碳信号7区域", "GET", "/api/v1/signals/regions", None, lambda s,r: s==200 and len(r.get("regions",[]))==7),
]

sec_passed = 0
for name, method, path, body, check in security_tests:
    h = {}
    if name == "错误令牌改设置":
        h["X-Admin-Token"] = "wrong-token"
    s, r = api(method, path, body, h if h else None)
    ok = check(s, r)
    if ok: sec_passed += 1
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name}: HTTP {s}")

total_pass = passed_count + sec_passed
total_fail = failed_count + (10 - sec_passed)

# ── 汇总报告 ────────────────────────────────────────────
print(f"\n{'=' * 90}")
print(f"测试汇总")
print(f"{'=' * 90}")
print(f"  智能推荐测试: {passed_count}/100 通过, {failed_count} 失败")
print(f"  安全边界测试: {sec_passed}/10 通过")
print(f"  总通过率:     {total_pass}/110 ({total_pass/110*100:.1f}%)")
print(f"  耗时:         {elapsed:.1f}s")

print(f"\n任务类型分布:")
for t, c in sorted(type_stats.items(), key=lambda x: -x[1]):
    print(f"  {t:<10} {c:>3} 例")

print(f"\n推荐档位分布:")
for t, c in sorted(tier_stats.items(), key=lambda x: -x[1]):
    print(f"  {t:<10} {c:>3} 例")

if failed_count > 0:
    print(f"\n失败用例详情:")
    for cid, cat, prompt, passed, detail in results:
        if not passed:
            print(f"  ❌ [{cid}] {cat}: 「{prompt}」")
            print(f"     {detail}")

# Save results as JSON for document generation
output = {
    "total": 110,
    "passed": total_pass,
    "failed": total_fail,
    "pass_rate": round(total_pass / 110 * 100, 1),
    "elapsed_s": round(elapsed, 1),
    "type_stats": type_stats,
    "tier_stats": tier_stats,
    "failures": [
        {"id": cid, "category": cat, "prompt": prompt, "detail": detail}
        for cid, cat, prompt, passed, detail in results if not passed
    ],
    "results": [
        {"id": cid, "category": cat, "prompt": prompt, "passed": passed, "detail": detail}
        for cid, cat, prompt, passed, detail in results
    ],
}
with open("D:/GreenFlex/backend/test_100_results.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n结果已保存: D:/GreenFlex/backend/test_100_results.json")
