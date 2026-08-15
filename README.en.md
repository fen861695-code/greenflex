# GreenFlex — Green AI Inference Routing Platform

> Route your AI tasks to the optimal model across **cost, speed, quality, and carbon emissions**.
> 35 built-in models (13 local + 20 cloud). Works out of the box — no GPU, no Ollama, no API key required.

[中文](./README.md) | English

---

## Table of Contents

- [What Is This](#what-is-this)
- [Key Features](#key-features)
- [Screenshots](#screenshots)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
- [Model Catalog](#model-catalog)
- [Configuration](#configuration)
- [Cloud API Integration](#cloud-api-integration)
- [Carbon Signals & Green Scheduling](#carbon-signals--green-scheduling)
- [API Reference](#api-reference)
- [Architecture](#architecture)
- [Data Sources & Provenance](#data-sources--provenance)
- [Security](#security)
- [FAQ](#faq)
- [Development](#development)
- [License](#license)

---

## What Is This

GreenFlex is a **green AI inference routing platform**: describe your task in natural language, and it automatically analyzes the task type and complexity, then recommends the best model out of 35 — saving money, energy, and carbon while meeting your quality requirements.

### Problems It Solves

| Pain Point | GreenFlex Solution |
|------------|-------------------|
| Too many models, don't know which to pick | Describe your task; get an instant recommendation |
| Small models are cheap but quality is risky | 7 task types × 3 complexity levels risk matrix; auto-upgrades when needed |
| Large models are great but expensive | Smart mode picks the cheapest model that meets quality — up to 90% savings |
| No visibility into carbon footprint | Every inference shows energy (Wh), carbon (g CO₂), and real-world equivalents |
| Cloud APIs are a hassle to integrate | Unified interface for 6 providers — just paste your key in Settings |
| Batch jobs need cost-speed-carbon tradeoffs | Flexible scheduling with grid carbon signals for low-carbon execution windows |

### Design Principles

- **Zero-config startup**: Simulated inference mode by default — no GPU, Ollama, or API keys needed
- **Data provenance**: Every model's energy and pricing data cites official sources; no fabricated numbers
- **Security first**: API keys stay server-side; user content is never logged; passports store only hashes
- **Extensible**: Reserved interfaces for cloud APIs, external agents (GreenConcierge), and RL-based routing

---

## Key Features

### 1. Smart Workspace

Enter a task description (vague natural language works). The system automatically:
- Identifies **7 task types**: classification, extraction, summarization, generation, analysis, code, translation
- Assesses **3 complexity levels**: simple / medium / complex (based on text length, batch size, output length)
- Recommends **4 tiers**: economy / balanced / quality / enterprise
- Provides price, energy, carbon, and latency estimates with 3 alternatives

Four modes:
- **Smart**: Auto-balances quality and cost
- **Economy**: Lowest price first, ideal for simple batch tasks
- **Quality**: Highest quality first, for critical tasks
- **Manual**: Pick the model yourself

### 2. AI Concierge

The integrated GreenConcierge agent offers two modes:

**Concierge mode** (default): describe tasks in natural language; the agent recommends models
- Auto-detects task type (classification, extraction, summarization, generation, analysis, code, translation)
- Returns recommended model with price, energy, carbon, latency, and alternatives
- Queries grid carbon signals, model list, order status
- With a cloud API key (DeepSeek recommended), uses LLM function calling for full conversation and task execution
- Without a key, runs in rule-based mode — task analysis and recommendations still work

**Direct chat mode**: pick a model and chat directly
- Multi-turn context
- Per-message model, price, energy, and carbon display
- Real model responses when cloud API keys are configured; simulated output otherwise

### 3. Model Preview

Run the same task across multiple models and compare:
- Output content
- Token usage (input/output)
- Latency (seconds)
- Energy (Wh) and carbon (g CO₂)
- Price (CNY)

### 4. Carbon Signal Map

Dedicated page showing real-time carbon intensity across China's 7 major grid regions:
- China map heatmap (greener = cleaner)
- Regional carbon intensity ranking
- 7-day carbon intensity calendar heatmap
- Cleanest/dirtiest grid summary cards
- Green scheduling recommendations

### 5. Batch Orders

- Upload CSV/JSONL files (UTF-8, max 5MB, 500 items)
- Immediate or flexible scheduling (with deadline)
- Automatic optimal model selection
- Per-item results, billing, and energy reports
- Cancel and content purge support

### 6. Token Passport

Every inference generates an auditable Token Passport:
- SHA-256 hashes of input/output (never raw content)
- Model used, token counts, latency
- Energy, carbon, and data provenance
- C2PA 1.3-compatible manifest (HMAC-SHA256 signed)
- Online verification supported

### 7. Compliance & Advanced

- **EU AI Act compliance reports**: Transparency and energy reporting per Articles 50/53
- **RL router** (optional): PPO algorithm learns optimal selection from order history; shadow mode by default
- **External agent integration**: GreenConcierge agent interface reserved for future task analysis and model selection

---

## Screenshots

| Workspace | AI Chat |
|:---:|:---:|
| ![Workspace](docs/images/01-workspace-empty.png) | ![Chat](docs/images/05-chat-conversation.png) |

| Model Preview | Carbon Map |
|:---:|:---:|
| ![Preview](docs/images/07-preview-results.png) | ![Carbon](docs/images/08-carbon-map.png) |

| Batch Orders | Settings |
|:---:|:---:|
| ![Orders](docs/images/12-orders.png) | ![Settings](docs/images/11-settings.png) |

---

## Quick Start

### Requirements

- Python 3.11+
- Node.js 18+
- Windows / macOS / Linux

> No GPU, Ollama, or API key required. Simulated inference is used by default.

### Windows One-Click Start

```powershell
# 1. Start backend (auto-creates venv and installs deps on first run)
cd backend
.\start-windows.bat

# 2. In a new terminal, start frontend
cd apps\web
npm install
npx vite
```

Then open http://127.0.0.1:5173

### Manual Setup

```powershell
# === Backend ===
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # Windows
# source .venv/bin/activate      # macOS/Linux
pip install -e .

# Initialize database
$env:PYTHONPATH="src"            # Windows
# export PYTHONPATH=src          # macOS/Linux
alembic upgrade head

# Start backend
python -m uvicorn greenflex.api:app --host 127.0.0.1 --port 8000

# === Frontend (new terminal) ===
cd apps/web
npm install
npx vite
```

Open http://127.0.0.1:5173 in your browser.
Interactive API docs: http://127.0.0.1:8000/docs

### Verify

```powershell
# Health check
curl http://127.0.0.1:8000/health

# Model catalog
curl http://127.0.0.1:8000/api/v1/models
```

---

## Usage Guide

### Example 1: Vague Task → Smart Recommendation

You don't need to know token counts or model names:

**Input**:
```
Summarize this 3000-word meeting transcript and highlight action items
```

**System analysis**:
- Task type: summarization
- Complexity: medium (long input)
- Recommended tier: balanced
- Recommended model: Qwen2.5 3B (local) or GPT-4o (cloud)
- Estimated: ¥0.002 / 0.8 Wh / 0.5 g CO₂

**Why not economy?** A 3000-word summarization carries quality risk on small models, so the system auto-upgrades to balanced.

### Example 2: Batch Classification → Economy Mode

**Input**:
```
I have 500 customer messages — classify each as complaint, inquiry, or suggestion
```

**Recommendation**:
- Task type: classification
- Complexity: simple (small models handle classification well)
- Recommended tier: economy
- Model: Gemma 3 1B or GPT-4o Mini
- 500 items for ~¥0.05 total

### Example 3: Code Generation → Auto Upgrade

**Input**:
```
Write a Python HTTP client with retry and timeout
```

**Recommendation**:
- Task type: code
- Complexity: medium
- Recommended tier: quality
- Code tasks have a hard tier floor — economy models are excluded

### Example 4: Real Chat with Cloud API

1. Go to **Settings**
2. Enter the admin token (auto-generated on first run, saved at `backend/artifacts/admin_token.txt`)
3. Paste your API key (e.g., DeepSeek)
4. Return to **AI Chat** and start chatting with a real model
5. Each message shows model, price, energy, and carbon

### Example 5: Check Carbon Emissions

1. Open the **Carbon Signal** page
2. View real-time carbon intensity across China's grid regions
3. Hover over the map for regional details
4. Check the 7-day heatmap to pick low-carbon windows for batch jobs

---

## Model Catalog

GreenFlex includes **35 models** across 4 tiers:

### Local Open-Source Models (13)

| Tier | Model | Parameters | Best For |
|------|-------|-----------|----------|
| Economy | Gemma 3 1B | 1B | Simple classification, extraction |
| Economy | Llama 3.2 1B | 1B | Simple classification, short text |
| Balanced | Gemma 4 E2B | 2B | Lightweight general tasks |
| Balanced | Llama 3.2 3B | 3B | Summarization, extraction |
| Balanced | Qwen2.5 3B | 3B | Chinese tasks, summarization |
| Balanced | Phi-4 Mini | 3.8B | Reasoning, analysis |
| Quality | Gemma 3 4B | 4B | General tasks |
| Quality | Mistral 7B | 7B | Generation, analysis |
| Quality | Qwen2.5 7B | 7B | Chinese high-quality tasks |
| Quality | Llama 3.1 8B | 8B | General high-quality |
| Quality | Qwen2.5 14B | 14B | Complex tasks |
| Enterprise | Qwen3 32B | 32B | High-complexity tasks |
| Enterprise | Llama 3.3 70B | 70B | Maximum quality |

### Cloud API Models (20)

| Tier | Model | Provider |
|------|-------|----------|
| Economy | GPT-4o Mini | OpenAI |
| Economy | Gemini Flash Lite | Google |
| Balanced | GPT-4o | OpenAI |
| Balanced | Claude Haiku 4.5 | Anthropic |
| Balanced | Gemini 3.1 Flash | Google |
| Balanced | Qwen Turbo | Alibaba |
| Balanced | Doubao Lite | ByteDance |
| Quality | GPT-5 | OpenAI |
| Quality | Claude Sonnet 4.6 | Anthropic |
| Quality | Gemini 3.1 Pro | Google |
| Quality | DeepSeek-V3 | DeepSeek |
| Quality | Qwen Plus | Alibaba |
| Enterprise | GPT-o3 Ultra | OpenAI |
| Enterprise | Claude Opus Thinking | Anthropic |
| Enterprise | DeepSeek-R1 | DeepSeek |
| Enterprise | GPT-5 Pro | OpenAI |
| Enterprise | Claude Opus 4.6 | Anthropic |
| Enterprise | Gemini 3.1 Ultra | Google |
| Enterprise | Qwen Max | Alibaba |
| Enterprise | Doubao Pro 1.5 | ByteDance |

### Task Classifiers (2, disabled by default)

| Model | Purpose |
|-------|---------|
| Qwen2.5 0.5B | Lightweight task classification, intent recognition |
| Qwen2.5 1.5B | Task classification, complexity assessment |

> Task classification currently uses a rule engine (MVP). Qwen2.5 models are reserved for future model-based classification.

---

## Configuration

All settings are via environment variables with the `GREENFLEX_` prefix. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

### Basic Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `GREENFLEX_API_HOST` | 127.0.0.1 | Listen address; use 0.0.0.0 for deployment |
| `GREENFLEX_API_PORT` | 8000 | Backend port |
| `GREENFLEX_WEB_ORIGIN` | http://127.0.0.1:5173 | Frontend URL (CORS) |
| `GREENFLEX_DATABASE_URL` | sqlite+aiosqlite:///./data/greenflex.db | Database URL |
| `GREENFLEX_LOG_LEVEL` | INFO | Logging level |
| `GREENFLEX_GRID_REGION` | CN-East | Default grid region |

### Cloud API Keys (Optional)

| Variable | Provider | Get Key |
|----------|----------|---------|
| `GREENFLEX_OPENAI_API_KEY` | OpenAI | https://platform.openai.com/api-keys |
| `GREENFLEX_ANTHROPIC_API_KEY` | Anthropic | https://console.anthropic.com/ |
| `GREENFLEX_DEEPSEEK_API_KEY` | DeepSeek | https://platform.deepseek.com/ |
| `GREENFLEX_ALIBABA_API_KEY` | Alibaba Cloud | https://help.aliyun.com/zh/model-studio/ |
| `GREENFLEX_BYTEDANCE_API_KEY` | Volcengine | https://www.volcengine.com/product/doubao |
| `GREENFLEX_GOOGLE_API_KEY` | Google AI | https://aistudio.google.com/apikey |

> The platform works fully without any API keys — chat and preview use simulated output.

### Admin Token

A random admin token is auto-generated on first run and saved to `backend/artifacts/admin_token.txt`.
You can also set `GREENFLEX_ADMIN_TOKEN` to customize it.

---

## Cloud API Integration

GreenFlex provides a unified interface for 6 cloud providers:

```
User request → CloudAPIProvider → Routes to provider
                                  ├─ OpenAI (GPT-4o, GPT-5, o3)
                                  ├─ Anthropic (Claude Haiku/Sonnet/Opus)
                                  ├─ DeepSeek (V3, R1)
                                  ├─ Alibaba (Qwen Turbo/Plus/Max)
                                  ├─ ByteDance (Doubao Lite/Pro)
                                  └─ Google (Gemini Flash/Pro/Ultra)
```

### Setup

1. Register and get an API key from the provider
2. Open GreenFlex **Settings**, enter the admin token
3. Paste your API key and save
4. Select a cloud model in Chat or Workspace

### Security Design

- API keys are stored server-side only, never exposed to the browser
- The frontend calls cloud APIs through the backend proxy
- Custom API base URLs supported (for proxy gateways or self-hosted endpoints)
- Friendly error messages when keys are missing

---

## Carbon Signals & Green Scheduling

### Data Coverage

GreenFlex uses carbon intensity data for China's 7 major grid regions:

| Region | Provinces |
|--------|-----------|
| North China | Beijing, Tianjin, Hebei, Shanxi, Shandong, Inner Mongolia |
| Northeast | Liaoning, Jilin, Heilongjiang |
| East China | Shanghai, Jiangsu, Zhejiang, Anhui, Fujian |
| Central China | Henan, Hubei, Hunan, Jiangxi, Sichuan, Chongqing |
| Northwest | Shaanxi, Gansu, Qinghai, Ningxia, Xinjiang |
| South China | Guangdong, Guangxi, Yunnan, Guizhou, Hainan |
| Southwest | Tibet |

### Carbon Intensity Levels

| Level | Intensity (gCO₂/kWh) | Meaning |
|-------|----------------------|---------|
| Very Low | < 200 | Hydro/nuclear dominant, very clean |
| Low | 200–400 | High renewable share |
| Medium | 400–600 | Mixed energy |
| High | 600–800 | Significant coal |
| Very High | > 800 | Coal-dominant |

### Green Scheduling

For batch jobs with flexible deadlines, the system uses grid carbon signals to:
- Execute during low-carbon-intensity windows
- Show 7-day carbon intensity forecasts
- Display estimated savings vs. the highest-carbon period

---

## API Reference

Start the backend and visit http://127.0.0.1:8000/docs for the full interactive Swagger UI.

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/models` | Model catalog |
| POST | `/api/v1/recommendations` | Get model recommendation |
| POST | `/api/v1/chat` | AI chat |
| POST | `/api/v1/previews` | Multi-model preview |
| GET | `/api/v1/signals/calendar` | Carbon signal calendar |
| GET | `/api/v1/signals/regions` | Grid regions |
| POST | `/api/v1/quotes` | Price quote |
| POST | `/api/v1/quotes/upload` | File upload quote |
| POST | `/api/v1/orders` | Create batch order |
| GET | `/api/v1/orders` | List orders |
| GET | `/api/v1/orders/{id}` | Order detail |
| GET | `/api/v1/passports/{id}` | Token passport |
| GET | `/api/v1/settings/cloud-api` | Cloud API settings |
| PUT | `/api/v1/settings/cloud-api` | Update API keys |

### Example

```bash
curl -X POST http://127.0.0.1:8000/api/v1/recommendations \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "smart",
    "task_type": "auto",
    "prompt_preview": "Summarize this article",
    "estimated_input_tokens": 500,
    "estimated_output_tokens": 200,
    "item_count": 1,
    "quality_requirement": "standard"
  }'
```

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  React Web  │────▶│  FastAPI     │────▶│   SQLite    │
│  (Vite)     │◀────│  (modular    │◀────│  (WAL mode) ││
│             │     │   monolith)  │     └─────────────┘
└─────────────┘     └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │Simulated │ │ Cloud API│ │ Ollama   │
        │ Provider │ │ Provider │ │ (optional)│
        └──────────┘ └──────────┘ └──────────┘
```

### Backend Modules

| Module | Responsibility |
|--------|---------------|
| `task_classifier.py` | Task type identification and complexity assessment (rule engine) |
| `simulated_provider.py` | Simulated inference (default, no external dependencies) |
| `cloud_provider.py` | Unified routing for 6 cloud providers |
| `agent_integration.py` | External agent integration (GreenConcierge reserved) |
| `recommendation.py` | GreenRouter multi-objective scoring |
| `catalog.py` | 35-model catalog with energy data |
| `carbon_intensity_service.py` | Grid carbon intensity service |
| `c2pa.py` | C2PA content provenance signing |
| `ai_act_compliance.py` | EU AI Act compliance reporting |
| `rl_router.py` | PPO reinforcement learning router (optional) |

### Recommendation Strategy

GreenRouter uses multi-objective weighted scoring:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Quality risk | 35% | Task-model fit; higher risk = higher penalty |
| Price | 20% | Normalized price; cheaper is better |
| Energy | 15% | Inference energy consumption |
| Carbon | 10% | Combined with grid carbon intensity |
| Latency | 10% | Inference speed |
| Wait time | 5% | Queue wait |
| Renewable | 5% | Green energy bonus |

---

## Data Sources & Provenance

GreenFlex is committed to **never fabricating data**. Every model parameter and energy figure cites an official source:

### Energy Data Tiers

| Tier | Source | Confidence | Notes |
|------|--------|------------|-------|
| L1 | Local NVML measurement | 95% | Real-time via nvidia-smi |
| L2 | Exact benchmark match | 85% | JouleBench / arXiv papers |
| L3 | Cross-GPU normalized | 65% | Same architecture, different size |
| — | Insufficient data | 0% | Excluded from energy scoring |

### Official Sources

- **OpenAI**: [Pricing](https://openai.com/api/pricing) · GPT-4 report arXiv:2303.08774 · Watt Counts (H100)
- **Anthropic**: [Pricing](https://www.anthropic.com/pricing) · Claude 3 model card · Watt Counts (H100)
- **Google**: [Pricing](https://ai.google.dev/pricing) · Gemini technical report · Watt Counts (H100)
- **DeepSeek**: [Pricing](https://platform.deepseek.com/pricing) · V3 report arXiv:2412.19437 · R1 report arXiv:2501.12948
- **Alibaba**: [Bailian Pricing](https://help.aliyun.com/zh/model-studio/billing-for-model-studio) · Qwen reports · JouleBench (A100)
- **ByteDance**: [Ark Pricing](https://www.volcengine.com/docs/82379/1099320) · Doubao docs · MoE analysis (H100)
- **Qwen**: [Official blog](https://qwenlm.github.io/blog/qwen2.5/) · JouleBench (arXiv 2608.00008)

---

## Security

- **No user content logging**: Prompts and outputs are never written to logs
- **API key protection**: Cloud keys are read only from server-side environment variables
- **Hash-only passports**: Token Passports store SHA-256 hashes, never raw content
- **Localhost by default**: API listens on 127.0.0.1 only; not exposed to the internet
- **Content purge**: Delete order prompts/outputs on demand while retaining anonymous stats
- **CORS restriction**: Only configured frontend origins are allowed
- **Admin token**: Write operations in Settings require an admin token

---

## FAQ

### Q: Can I use it without API keys?

**Yes.** Simulated inference is the default — all features (workspace, chat, preview, batch orders, carbon signals) work fully. AI outputs are placeholder text.

### Q: Can I run local models without a GPU?

**Yes.** The default mode uses simulated inference and does not require Ollama or a GPU. For real local inference, install Ollama and download models; the system can switch automatically.

### Q: What's the difference between simulated and real output?

Simulated output generates placeholder text based on task type, with token counts and latency estimated from model parameters — useful for testing routing logic and UI flows. With real API keys, outputs come from actual models.

### Q: How do I deploy it on a server?

1. Get a cloud server (2 vCPU / 2GB RAM minimum recommended)
2. Set `GREENFLEX_API_HOST=0.0.0.0`
3. Set `GREENFLEX_WEB_ORIGIN` to your domain
4. Build the frontend and serve with Nginx, reverse-proxying the API
5. Mainland China servers require ICP filing; Hong Kong/overseas do not

### Q: Which cloud providers are supported?

OpenAI, Anthropic, DeepSeek, Alibaba Cloud (Qwen), Volcengine (Doubao), and Google AI — 6 providers total.

### Q: What if a port is already in use?

**Backend (default 8000)**: Change via environment variable:
```powershell
$env:GREENFLEX_API_PORT=8001
python -m uvicorn greenflex.api:app --port 8001
```

**Frontend (default 5173)**: Vite automatically picks the next available port (5174, 5175…), or set it manually:
```powershell
$env:VITE_PORT=5180
npx vite
```

The Windows startup script automatically detects port conflicts and prompts you.

### Q: How accurate is the carbon data?

Local model energy is based on public benchmarks (JouleBench, Watt Counts papers); cloud model energy is estimated from architecture analysis. Carbon intensity uses China regional grid baselines. All data includes source and confidence labels. No zero-carbon claims are made.

---

## Development

### Backend Tests

```powershell
cd backend
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

238 test cases covering recommendation, API, task classification, energy estimation, carbon signals, and more.

### Frontend Checks

```powershell
cd apps/web
npx tsc --noEmit       # TypeScript type check
npx vitest run         # Unit tests
```

### Project Structure

```
GreenFlex/
├── backend/
│   ├── src/greenflex/    # Backend source
│   ├── tests/            # Tests
│   ├── migrations/       # Database migrations
│   └── scripts/          # Utility scripts
├── apps/web/
│   └── src/
│       ├── pages/        # Page components
│       ├── components/   # Shared components
│       └── api/          # API client
├── data/                 # Data files (carbon factors, tariffs)
├── docs/                 # Documentation and screenshots
└── .env.example          # Configuration template
```

---

## License

Source code is licensed under Apache-2.0. Model weights, datasets, and third-party components retain their own licenses and are not redistributed by this repository.
