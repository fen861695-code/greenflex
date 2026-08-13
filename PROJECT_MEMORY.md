# GreenFlex 项目记忆文档

> 本文档记录 GreenFlex 项目的核心设计、已完成修改、待办事项和关键路径。
> 新会话/新窗口读取本文档即可快速恢复项目上下文。
> 最后更新：2026-08-14

---

## 一、项目基本信息

- **项目名称**：GreenFlex — 本地绿色文本推理订单平台
- **版本**：v0.1.0（单租户、无登录、无支付的本地 MVP）
- **项目路径**：`/home/user/.super_doubao/super-doubao-runtime/workspace/greenflex/`
- **用户身份**：2026 AI 先锋未来人才大赛 参赛选手
- **API 默认只监听 `127.0.0.1`，不得直接暴露公网**

### 技术栈
- 前端：React + TypeScript
- 后端：FastAPI 模块化单体 + 持久化 Worker + SQLite WAL
- 推理：Ollama + Qwen2.5（本地模型）
- 遥测：NVIDIA nvidia-smi（GPU 能耗）

### 核心文档
- `README.md` — 项目说明、产品工作流、数据真实边界
- `ARCHITECTURE.md` — 架构图、容器边界、领域模块、GreenRouter 说明
- `AGENTS.md` — 编码代理规则（10 条，必须遵守）

---

## 二、产品工作流

1. 工作台输入单条文本，选择经济/标准/高质量档位并获取报价
2. 模型试跑页顺序比较已安装模型的输出、Token、延迟与 GPU 能耗
3. 上传 UTF-8 CSV/JSONL 批量任务，选择立即或截止时间前弹性执行
4. 查看订单逐项结果、实际仿真账单、能源记录并下载结果
5. 查看 Token Passport 的输入/输出哈希、模型、用量、能耗、碳排和声明边界

---

## 三、数据真实边界（三层）

| 层级 | 来源 | 说明 |
|------|------|------|
| **Measured（实测）** | 本地模型输出、token 计数、延迟、NVIDIA GPU board power | 真实测量 |
| **Estimated（估算）** | 实测 GPU 能耗 + 版本化 PUE 假设推导的设施能耗 | 基于实测推导 |
| **Simulated（仿真）** | 电价、电网碳强度、可再生比例、服务价格、折扣、绿色等级 | 完全模拟 |

GreenFlex 不声称零碳推理、政府认证或云厂商侧能源测量。

---

## 四、推荐系统详解（核心模块，讨论最多）

### 4.1 整体架构：三层流水线

**任务识别（TaskClassifier）→ 复杂度评估（ComplexityEstimator）→ 两阶段模型选择（GreenRouterRuleV1）**

### 4.2 任务识别（TaskClassifier）

- **文件**：`backend/src/greenflex/recommendation.py`
- **方法**：few-shot prompt + 强制 JSON 输出，使用 `qwen2.5:1.5b`（catalog 中 enabled=False，对用户隐藏，专门作分类器后端）
- **6 种任务类型**：`classification` / `extraction` / `summarization` / `analysis` / `generation` / `code`，外加 `auto`
- **输入截断**：只取 prompt 前 500 字符
- **生成参数**：`max_output_tokens=64, temperature=0.1`
- **失败处理**：任何异常 → 返回 `(TaskType.AUTO, 0)`

#### 分类器实测结果（已在本服务器实测）
- 用 llama-cpp-python + Qwen2.5-1.5B-Instruct-GGUF (q4_k_m) 在纯 CPU 2 核上测试
- 18 个用例，17 正确 = **94.4% 准确率**
- **唯一错误**："用 JavaScript 写一个快速排序"被分成 generation 而非 code（few-shot 缺少"写代码"式示例）
- **置信度完全不可信**：所有用例置信度 ≥0.88，包括分错的那个（报 0.95），模型"无脑报高置信度"
- 速度：首次 5.6s（冷启动），后续约 0.85s/次

### 4.3 复杂度评估（ComplexityEstimator）

- **文件**：`backend/src/greenflex/recommendation.py`，类定义约第 740 行
- **方法**：纯规则启发式，不调用模型，确定性可解释
- **5 项特征打分**：
  1. 文本长度：<100=0, <500=1, <2000=2, 更长=3
  2. 技术术语密度：命中 `_TECHNICAL_TERMS` 词数（法律/医学/代码/财务/数学等约 40 个）
  3. 推理需求信号：命中 `_REASONING_SIGNALS` 词数（分析/对比/评估/为什么/如何等）
  4. 结构化输出：命中 `_STRUCTURED_SIGNALS` 任一词 → +1
  5. 多问题：问号 ≥2 → +1
- **任务类型基础复杂度**：classification=0, extraction=1, summarization=1, generation=2, analysis=3, code=3, auto=1
- **加权公式**：`total = length×2 + term×2 + reasoning×3 + structured×1 + multi×1 + task_base×2`
- **分档阈值**：≤5=LOW, ≤10=MEDIUM, >10=HIGH

### 4.4 模型选择（GreenRouterRuleV1，两阶段）

- **策略版本**：`green-router-rule-v2`
- **Profile 版本**：`model-task-profile-v1`

#### Phase 1：硬约束过滤（6 条）
1. 上下文长度：输入+输出 > model.context_limit → 淘汰
2. 截止时间：执行+等待 > 剩余时间 → 淘汰
3. 预算：价格 > budget → 淘汰
4. 质量底线：CRITICAL 要求 tier<quality / HIGH 要求 tier<balanced → 淘汰
5. 任务能力：code 任务 + economy 档 → 淘汰
6. 经济模式门控：economy 档 + 非 economy/smart 模式 → 淘汰

#### Phase 2：多目标加权打分
| 维度 | 权重 |
|------|------|
| 质量风险 | 35% |
| 价格 | 20% |
| 能耗 | 15% |
| 碳排 | 10% |
| 延迟 | 10% |
| 等待 | 5% |
| 可再生能源 | -5%（负权重，越高越好） |

- 每个维度归一化到 [0,1]（除以候选集最大值）
- 能耗和碳排乘以不确定性惩罚系数
- 分数越低越好

#### 模式选择
- **SMART（默认）**：综合分最低；分差 5% 以内偏向更高质量档
- **ECONOMY**：直接选最低价
- **QUALITY**：只在 quality 档里选最优
- **MANUAL**：用户手动选

#### 安全兜底
- 选中模型质量风险 HIGH/VERY_HIGH 且置信度 <60% → 强制回退 quality 档

### 4.5 质量风险矩阵（3D：任务 × 复杂度 × 档位）

`get_quality_risk(task_type, complexity, tier)` 函数优先查 3D 矩阵，fallback 到 2D。

关键规则：
- analysis/code 任务 + HIGH 复杂度 + economy 档 = VERY_HIGH 风险
- generation 任务 + HIGH 复杂度 + economy 档 = VERY_HIGH 风险
- classification 任务即使 HIGH 复杂度，economy 也只是 MEDIUM 风险

### 4.6 能耗数据分级（L1-L3）

| Tier | 来源 | 置信度 | 惩罚系数 |
|------|------|--------|----------|
| L1 | 本地 NVML 实测 | 95% | 1.00x |
| L2 | 精确模型+GPU 基准匹配 | 85% | 1.05x |
| L3 | 跨 GPU 归一化基准 | 65% | 1.15x |
| 数据不足 | 无 L1-L3 数据 | 0% | 10.0x（基本排除） |

内置基准数据 18 条，来自 JouleBench、arXiv 2608.00008、Watt Counts。

---

## 五、已完成的修改与修复（按时间顺序）

### 5.1 复杂度评估接入修复（重要 Bug 修复）
**问题**：`ComplexityEstimator` 类和 3D 质量风险矩阵已定义，但 `GreenRouterRuleV1._estimate_candidate()` 完全没有调用，直接用 2D 矩阵。复杂度评估是死代码。
**修复**：`_estimate_candidate` 增加 `complexity` 参数，调用 `get_quality_risk(task_type, complexity, tier)` 使用 3D 矩阵。
**文件**：`backend/src/greenflex/recommendation.py`

### 5.2 能耗/时间计算修正（重要 Bug 修复）
**问题**：能耗和执行时间只算输出 token，完全忽略输入 token（prefill 阶段）：
```python
energy = energy_per_1k * total_output // 1_000        # 只算输出
execution_seconds = total_output // tokens_per_second + 1  # 只算 decode
```
**修复**：
```python
# 能耗：输入+输出都算
total_tokens = total_input + total_output
energy = energy_per_1k * total_tokens // 1_000

# 执行时间：prefill（假设 3x 速度）+ decode
prefill_seconds = total_input // (tokens_per_second * 3)
decode_seconds = total_output // tokens_per_second
execution_seconds = prefill_seconds + decode_seconds + 1
```
**文件**：`backend/src/greenflex/recommendation.py`
**验证**：输入 64→57,600 µWh/2s，输入 2000→406,080 µWh/5s（相同输出 256 token）

### 5.3 输出 Token 上限放宽
**问题**：全局硬上限 2048，限制了长文本生成/代码生成。
**修复**：2048 → 8192。context_limit 硬约束仍然生效（输入+输出≤模型上下文）。
**文件**：
- `backend/src/greenflex/domain.py`：`MAX_OUTPUT_TOKENS_CEILING = 8192`
- `backend/src/greenflex/schemas.py`：PreviewRequest、BatchItemInput、SolutionItemInput 三处 `le=2048` → `le=8192`

### 5.4 离线评估脚本创建与扩充
**脚本路径**：`backend/scripts/evaluate_recommendation.py`
- 初始 33 个用例 → 扩充到 **85 个用例**
- 覆盖：6 种任务类型 × 3 种质量要求 × 3 种模式、复杂度边界、对抗场景、prompt 规则路径、批量场景、预算/截止时间边界、极端场景
- 8 项评估维度：档位命中率、Top-3 覆盖率、约束满足率、模式一致性、置信度校准、鲁棒性、能耗分级影响、失败案例详情
- **当前结果：85/85 = 100% 通过**
- 支持 `--strict` 模式（CI 门禁）和 `-o report.json` 输出

### 5.5 pytest 离线评估测试
**文件**：`backend/tests/test_recommendation_offline.py`
- 复用评估脚本逻辑，作为自动化回归测试
- 断言：命中率≥90%、Top3≥95%、约束/模式必须 100%
- 包含复杂度接入专项测试

### 5.6 核心逻辑验证脚本
**文件**：`backend/scripts/verify_recommendation.py`
- 25 项核心逻辑断言
- **当前结果：25/25 通过**

---

## 六、模型目录（catalog.py）

### 本地模型（enabled=True 的 9 个）

| 档位 | 模型 | 参数 | 上下文 | 速度 | 能耗 |
|------|------|------|--------|------|------|
| economy | gemma3-1b-q4 | 1B | 128K | 180 t/s | 0.18 Wh/1k |
| economy | llama3.2-1b-q4 | 1B | 128K | 150 t/s | 0.20 Wh/1k |
| balanced | gemma4-e2b-q4 | 2B | 128K | 100 t/s | 0.35 Wh/1k |
| balanced | llama3.2-3b-q4 | 3B | 128K | 95 t/s | 0.38 Wh/1k |
| balanced | phi4-mini-3.8b-q4 | 3.8B | 128K | 75 t/s | 0.48 Wh/1k |
| quality | gemma3-4b-q4 | 4B | — | 70 t/s | 0.50 Wh/1k |
| quality | mistral-7b-q4 | 7B | — | 50 t/s | 0.75 Wh/1k |
| quality | qwen2.5-7b-q4 | 7B | 32K | 45 t/s | 0.80 Wh/1k |
| quality | llama3.1-8b-q4 | 8B | — | 40 t/s | 0.85 Wh/1k |

### 隐藏模型（enabled=False）
- `qwen2.5-0.5b-q4`：对用户隐藏
- `qwen2.5-1.5b-q4`：分类器后端
- `qwen2.5-3b-q4`：对用户隐藏
- `qwen2.5-14b-q4`：需 10GB+ VRAM
- `qwen3-32b-q4` / `llama3.3-70b-q4`：企业档，需数据中心

---

## 七、已知问题与待办事项

### 高优先级
1. **置信度展示误导**：分类器置信度未校准，所有用例都报 ≥0.88。建议改成"高/中/低"三档且经过校准，不要直接展示百分比。
2. **中文 token 估算偏低**：`estimate_input_tokens` 用 `characters / 3`，这是英文经验值。中文 1 字通常 1~1.5 token，会严重低估中文 token 数，导致价格/能耗预估偏低。建议按 CJK 字符比例加权。
3. **前端输出 token 滑块**：后端已放宽到 8192，前端手动模式的滑块可能还是 2048，需要同步更新。
4. **能耗数据惩罚方向**：无能耗数据的模型被 10x 惩罚后，系统倾向选有数据的更小模型，而不是选更合适的模型。惩罚可能过重。
5. **queue_depth 永远=0**：代码写了 TODO，等待时间维度完全不生效。

### 中优先级
6. **推荐理由具体化**：从模板句改成对比式（"选 A 而非 B：价格低 60%，质量风险同为低"）
7. **任务分类可修正**：置信度 <70% 时显示"系统判断为 XX，是否修正？"，修正后即时重新推荐
8. **上下文超限提示具体化**：从"没有满足约束的模型"改成"输入 X + 输出 Y = Z，超过模型 A 的 N K 上下文，建议选模型 B"
9. **few-shot 示例补全**：code 类加"写代码"示例，generation 类加"改写/润色"示例
10. **关键词规则兜底**：分类失败时加一层关键词规则匹配，成本几乎为零

### 低优先级
11. 权重（35/20/15/10/10/5/5）无数据驱动，可做 A/B 测试或偏好学习
12. 归一化用候选集最大值，候选集变化时分数不可比
13. 批量任务实时预览（执行中已完成条目先展示输出）
14. 备选方案采纳反馈记录，为 RL 路由器提供训练信号

### 训练数据方向（用户已询问）
- **任务分类器**：NVIDIA NeMo Curator Prompt Task & Complexity Classifier（现成模型，最匹配）
- **RL 路由器/奖励模型**：HelpSteer 2（有 complexity 维度评分，最推荐）、Anthropic HH-RLHF、StackExchange SHP
- **代码专项**：Magicoder OSS-Instruct-75K、Evol-CodeAlpaca、The Stack Dedup
- **复杂度标注**：HelpSteer 2 的 complexity 维度 / 用 GPT-4 合成标注
- **能耗数据**：无公开通用数据集，需自己实测（这是核心壁垒）

---

## 八、关键文件路径索引

### 后端源码
- 推荐系统：`backend/src/greenflex/recommendation.py`
- 领域模型：`backend/src/greenflex/domain.py`
- API Schema：`backend/src/greenflex/schemas.py`
- 模型目录：`backend/src/greenflex/catalog.py`
- 服务层：`backend/src/greenflex/services.py`
- 端口定义：`backend/src/greenflex/ports.py`

### 测试与脚本
- 离线评估：`backend/scripts/evaluate_recommendation.py`
- 核心验证：`backend/scripts/verify_recommendation.py`
- 单元测试：`backend/tests/test_recommendation.py`
- 离线评估 pytest：`backend/tests/test_recommendation_offline.py`

### 前端
- 工作台：`apps/web/src/pages/WorkspacePage.tsx`
- 推荐卡片：`apps/web/src/components/RecommendationCard.tsx`

### 数据
- 数据目录：`data/`
- 分类器模型（实测用）：`/home/user/.super_doubao/super-doubao-runtime/workspace/.tmp-tool-results/models/qwen2.5-1.5b-instruct-q4_k_m.gguf`

---

## 九、环境信息

- **操作系统**：Ubuntu 22.04.3 LTS
- **CPU**：AMD EPYC 9Y24 96-Core（2 核可用）
- **内存**：3.9GB（可用 3.2GB），无 Swap
- **GPU**：无
- **后端虚拟环境**：`backend/.venv/`（Python 3.10，仅装 pydantic、SQLAlchemy，无 ML 库）
- **Ollama**：未安装（sudo 不可用，官方脚本失败）
- **llama-cpp-python**：可安装，支持 Qwen2 架构
- **模型下载**：modelscope.cn 可用，hf-mirror.com 不可用

### 运行评估脚本
```bash
cd /home/user/.super_doubao/super-doubao-runtime/workspace/greenflex/backend
python scripts/evaluate_recommendation.py              # 控制台报告
python scripts/evaluate_recommendation.py --strict     # CI 门禁模式
python scripts/verify_recommendation.py                # 核心逻辑验证
```

---

## 十、AGENTS.md 编码规则（必须遵守）

1. 模块化边界：领域逻辑放 domain，服务编排放 services，API 放 api
2. 禁止在业务代码中使用 print，用 logger
3. 数据来源必须声明（measured/estimated/simulated）
4. 价格和碳排是 simulated，不得声称真实
5. API 默认只监听 127.0.0.1
6. 新增模型必须在 catalog.py 注册
7. 推荐策略变更必须更新 policy_version
8. 能耗数据必须标注 provenance tier（L1-L3）
9. 不得硬编码业务魔法数字，用常量或配置
10. 修改推荐逻辑必须跑离线评估

---

*本文档由对话上下文整理生成，新会话读取本文档即可恢复项目状态。*
