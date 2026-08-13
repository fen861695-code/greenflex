# ADR 0010: EU AI Act Compliance Reporting

## Status

Accepted

## Context

The EU AI Act (Regulation (EU) 2024/1689) imposes obligations on AI system
providers and deployers. Key relevant articles:

- **Article 50**: Transparency obligations (AI-generated content labeling)
- **Article 53**: General-Purpose AI (GPAI) model obligations
  - (a) Technical documentation (Annex XI)
  - (b) Summary of training data content
  - (c) Copyright law alignment
  - (d) **Energy consumption reporting**
- **Article 10-15**: High-risk system obligations (data governance,
  technical documentation, record-keeping, transparency, human oversight,
  accuracy/robustness/cybersecurity)

GreenFlex is not a GPAI model developer, but it provides infrastructure for
running and comparing models. Users and model providers need tools to
demonstrate compliance.

## Decision

Implement an AI Act compliance report generator that assesses GreenFlex's
compliance posture and provides templates for model-specific compliance.

### Report Structure

The compliance report covers:

1. **Summary**: Overall compliance score, risk level, high-severity issues
2. **Model information**: Model ID, parameters, intended use, risk classification
3. **Platform information**: GreenFlex deployment details
4. **Detailed checks**: Per-article assessment with evidence and recommendations

### Covered Articles

| Article | Requirement | GreenFlex Status |
|---------|-------------|------------------|
| Art. 50 | AI content transparency | Compliant (C2PA Token Passport) |
| Art. 53(1)(a) | Technical documentation | Partial (needs model provider input) |
| Art. 53(1)(b) | Training data summary | Partial (model provider responsibility) |
| Art. 53(1)(c) | Copyright alignment | Partial (model provider responsibility) |
| Art. 53(1)(d) | Energy consumption | Compliant (measured/estimated energy) |
| Art. 10 | Data governance | N/A for limited risk |
| Art. 11 | Technical documentation | Partial |
| Art. 12 | Record-keeping | Compliant (audit logs) |
| Art. 13 | Transparency to deployers | Partial |
| Art. 14 | Human oversight | Compliant (user confirmation) |
| Art. 15 | Accuracy/robustness/security | Partial/Compliant |

### GreenFlex Compliance Strengths

1. **C2PA-compatible Token Passport** — Article 50 transparency
2. **Energy consumption reporting** — Article 53(1)(d), with provenance tiers
3. **Audit logging** — Article 12 record-keeping
4. **Human oversight** — Article 14, user confirms all orders
5. **Local-first security** — Article 15, API bound to 127.0.0.1
6. **Content purge** — Data minimization

### Output Formats

- JSON (machine-readable)
- Markdown (human-readable, downloadable)

### API Endpoints

- `GET /api/v1/compliance/ai-act` — Platform compliance report
- `GET /api/v1/compliance/ai-act/{model_id}` — Model-specific report
- `GET /api/v1/compliance/ai-act/markdown` — Download Markdown report

## Consequences

### Positive
- Helps users demonstrate AI Act compliance
- Identifies gaps and provides actionable recommendations
- Highlights GreenFlex's unique strengths (energy reporting, C2PA)
- Supports both platform-level and model-level assessment

### Negative
- Compliance assessment is advisory, not legal certification
- Some obligations require model provider input (training data, copyright)
- Report must be updated as AI Act implementing acts are published

### Risks
- AI Act specification is evolving — implementing acts may change requirements
- Compliance score may give false sense of security — clearly labeled as advisory
- Legal liability: report is a tool, not legal advice

## Future Work

- Annex IV / Annex XI template completion
- Automated evidence collection from order history
- Multi-language report generation
- Integration with model provider documentation
- Periodic compliance re-assessment
- Gap remediation tracking
