# GreenFlex 基准数据来源说明

本目录包含 GreenFlex 使用的所有基准数据，所有数据均来自公开可查的来源。
数据文件格式为 JSON，便于程序读取和人工核查。

## 数据来源清单

### 1. 模型能耗基准 (benchmarks/)

| 文件 | 来源 | URL | 测量方法 | 硬件/环境 |
|------|------|-----|----------|-----------|
| model-energy-bench-v1.json | arXiv 2608.00008 | https://arxiv.org/pdf/2608.00008 | NVML/nvidia-smi 2Hz 采样 | RTX 4060 Ti 16GB, Q4量化, Ollama |
| model-energy-bench-v1.json | arXiv 2607.26571 | https://arxiv.org/pdf/2607.26571 | 解析模型校准自实测 | H100 SXM, FP16/BF16 |
| model-energy-bench-v1.json | GitHub NCHWU/sustainableA1 | https://github.com/NCHWU/sustainableA1/blob/main/report.md | 直接功率测量 | RTX 3060, Qwen2.5 0.5B |
| model-energy-bench-v1.json | CyberNative Candle Index | https://cybernative.ai/t/the-candle-index-what-every-token-actually-costs-in-fire/34019 | 硬件功率计 | RTX 4090, 多模型 |
| **cloud-production-models-v1.json** | **博客园/ChinaSoft 综合** | https://www.cnblogs.com/chinasoft/p/19858851 | **多源综合估算** | **H100/H200/B200 数据中心, PUE 1.2** |
| cloud-production-models-v1.json | LLM API Comparison Matrix | https://github.com/janwilmake/state-of-llm-apis/blob/main/comparison.md | 官方定价+能耗模型 | 各厂商生产环境 |
| cloud-production-models-v1.json | Iternal On-Premise LLM Guide | https://iternal.ai/how-to-deploy-llm-on-premise | MLPerf 推理基准 | H200 FP8, 8xH100 |

**云API模型说明**：
- 包含 OpenAI、Anthropic、Google、DeepSeek、阿里、字节、Meta、智谱、月之暗面、百度、腾讯、Mistral 等主流厂商
- 共 20 个代表性生产模型，覆盖从旗舰推理到轻量高并发全档位
- 能耗值包含数据中心 PUE 1.2 的冷却和设施开销
- 价格按 1 USD ≈ 7.2 CNY 换算为模拟人民币价格
- 这些模型默认 `enabled=False`（本地 Ollama 无法运行），用于成本/能耗对比和未来云路由功能

### 2. 电价数据 (tariffs/)

| 文件 | 来源 | URL | 时间 |
|------|------|-----|------|
| cn-industrial-tariffs-2026.json | 国家电网/95598 | https://www.95598.cn/omg-static//omg-static/99304241763013365914101929287974.pdf | 2026年7月 |
| cn-industrial-tariffs-2026.json | 北极星电力网 | https://m.bjx.com.cn/mnews/20260703/1502780.shtml | 2026年7月 |
| cn-industrial-tariffs-2026.json | 沪发改价管﹝2022﹞50号 | 上海发改委文件 | 2026年夏季 |

覆盖华东、华北、南方、东北、西北、华中六大区域，含尖峰/高峰/平段/低谷/深谷五档分时电价。

### 3. 碳排放因子 (carbon/)

| 文件 | 来源 | URL | 时间 |
|------|------|-----|------|
| cn-grid-carbon-factors-v2.json | 生态环境部 | https://www.mee.gov.cn/ywdt/zbft/202601/t20260105_1139911.shtml | 2023年度官方值 |
| cn-grid-carbon-factors-v2.json | 国家统计局 | 2025年电力碳排放因子公告 | 2025年度估算值 |
| cn-grid-carbon-factors-v2.json | 中国电力企业联合会 | 区域电网基准线排放因子 | 2024-2025 |

包含年度基准值、分时段动态碳强度（午间光伏低至280g/kWh）、各区域非化石能源占比、PUE参考值和国际对比。

## 数据可信度分级

- **measured**: 硬件直接测量，置信度最高
- **measured_anchor**: 有公开实测锚点，生产环境有合理 overhead
- **analytical**: 基于实测校准的解析模型，误差 5-27%
- **interpolated**: 同架构插值，用于估算未直接测量的模型
- **estimated**: 多源综合估算（云API模型），基于定价和架构推算，误差范围较大
- **simulated**: 综合多源的合理仿真值

## 关键换算公式

```
1 kWh = 3.6 × 10^6 J
tokens_per_kwh = 3,600,000 / j_per_token
wh_per_1k_output = 1000 / tokens_per_kwh * 1000

MoE模型能耗 ≈ 激活参数 × 单位能耗 × overhead(3-10x)
推理模型能耗 = 基础模型 × 3-10x（多轮思考token）
```

## 模型规模参考（2026年生产环境）

| 档位 | 每kWh token数 | J/token | 代表模型 | 典型用途 |
|------|--------------|---------|----------|----------|
| 前沿推理 | 4万-15万 | 24-90 J | o3 Ultra, Opus Thinking | 数学证明、科学研究 |
| 旗舰通用 | 10万-50万 | 7-36 J | GPT-5, Claude Opus, Gemini Ultra | 企业级、高质量写作 |
| 高端生产 | 30万-80万 | 4-12 J | Sonnet, Gemini Pro, DeepSeek-V3 | 日常开发、RAG、代码 |
| 中端高并发 | 80万-300万 | 1-5 J | Haiku, Flash, GPT-5 Mini | 分类、抽取、高并发API |
| 轻量高速 | 300万-1000万 | 0.3-1.2 J | 4o Mini, Flash Lite | 简单任务、实时响应 |
| 本地/边缘 | 1000万+ | <0.3 J | Qwen2.5 0.5B-7B | 本地部署、隐私计算 |

## 更新记录

- 2026-08-06: 初始版本，整合本地消费级显卡数据
- 2026-08-06: 新增云API生产模型数据（20个主流厂商模型），更新电价和碳排数据
