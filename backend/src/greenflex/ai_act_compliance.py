"""EU AI Act Compliance Report Generator for GreenFlex.

Implements compliance assessment and report generation aligned with the
EU AI Act (Regulation (EU) 2024/1689), focusing on:
- General-Purpose AI (GPAI) model obligations (Article 53)
- Transparency obligations (Article 50)
- Technical documentation (Annex IV)
- Record-keeping (Article 12)
- Human oversight (Article 14)
- Accuracy, robustness, cybersecurity (Article 15)
- Energy consumption reporting (Article 53(1)(d))

GreenFlex is a local-first inference platform, not a GPAI model developer.
However, it provides tooling to help users and model providers demonstrate
compliance with AI Act obligations.

Risk classification:
- GreenFlex itself: minimal risk (transparency tool)
- Models deployed via GreenFlex: depends on use case
  - General purpose: limited risk (transparency obligations)
  - High-risk use cases: full compliance required
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class AIRiskLevel(str, Enum):
    """AI Act risk levels."""
    MINIMAL = "minimal"  # No obligations
    LIMITED = "limited"  # Transparency obligations
    HIGH = "high"  # Full compliance
    UNACCEPTABLE = "unacceptable"  # Prohibited


class AIActArticle(str, Enum):
    """Relevant AI Act articles."""
    ARTICLE_5_TRANSPARENCY = "article_5"  # Prohibited practices
    ARTICLE_10_DATA_GOVERNANCE = "article_10"  # Data and data governance
    ARTICLE_11_TECHNICAL_DOC = "article_11"  # Technical documentation
    ARTICLE_12_RECORD_KEEPING = "article_12"  # Record-keeping
    ARTICLE_13_TRANSPARENCY = "article_13"  # Transparency and provision of information
    ARTICLE_14_HUMAN_OVERSIGHT = "article_14"  # Human oversight
    ARTICLE_15_ACCURACY = "article_15"  # Accuracy, robustness, cybersecurity
    ARTICLE_50_TRANSPARENCY = "article_50"  # Transparency obligations for certain AI systems
    ARTICLE_53_GPAI = "article_53"  # Obligations for providers of GPAI models
    ARTICLE_55_GPAI_CODE = "article_55"  # GPAI codes of practice


@dataclass
class ComplianceCheck:
    """Single compliance check result."""
    article: str
    requirement: str
    status: str  # "compliant", "partial", "not_applicable", "non_compliant"
    evidence: str = ""
    recommendation: str = ""
    severity: str = "low"  # "low", "medium", "high", "critical"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelComplianceInfo:
    """Model information needed for AI Act compliance assessment."""
    model_id: str
    model_name: str
    model_version: str = ""
    provider: str = ""
    parameter_count_b: float | None = None
    training_data_summary: str = ""
    intended_use: str = "general purpose text generation"
    risk_level: AIRiskLevel = AIRiskLevel.LIMITED
    # Technical capabilities
    context_window: int = 0
    supported_languages: list[str] = field(default_factory=list)
    # Performance metrics
    accuracy_notes: str = ""
    robustness_notes: str = ""
    # Known limitations
    known_biases: list[str] = field(default_factory=list)
    known_limitations: list[str] = field(default_factory=list)
    # Safety
    content_filter_enabled: bool = False
    jailbreak_defense: bool = False
    # Energy
    energy_provenance_tier: str = "insufficient_data"
    typical_energy_wh_per_1k_output: float = 0.0


@dataclass
class GreenFlexComplianceInfo:
    """GreenFlex platform compliance information."""
    version: str = "0.1.0"
    deployment_type: str = "local-first single-tenant"
    api_bound: str = "127.0.0.1 only"
    user_authentication: bool = False
    audit_logging: bool = True
    content_purge: bool = True
    c2pa_support: bool = True
    energy_reporting: bool = True
    carbon_reporting: bool = True
    human_oversight: bool = True  # User confirms all orders
    data_residency: str = "local only (no cloud transmission)"


@dataclass
class AIActComplianceReport:
    """EU AI Act Compliance Report.

    Generates a structured compliance assessment covering all relevant
    AI Act obligations for GPAI models and AI systems.
    """
    report_id: str = field(default_factory=lambda: f"ai-act-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}")
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    regulation: str = "Regulation (EU) 2024/1689 (AI Act)"
    report_version: str = "1.0"

    model_info: ModelComplianceInfo | None = None
    platform_info: GreenFlexComplianceInfo = field(default_factory=GreenFlexComplianceInfo)

    checks: list[ComplianceCheck] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def assess(self, model_info: ModelComplianceInfo | None = None) -> "AIActComplianceReport":
        """Run full compliance assessment."""
        if model_info:
            self.model_info = model_info

        self.checks = []

        # Article 50: Transparency obligations
        self._check_article_50_transparency()

        # Article 53: GPAI obligations
        self._check_article_53_gpai()

        # Article 10: Data governance (for high-risk)
        self._check_article_10_data_governance()

        # Article 11: Technical documentation
        self._check_article_11_technical_doc()

        # Article 12: Record-keeping
        self._check_article_12_record_keeping()

        # Article 13: Transparency and information
        self._check_article_13_transparency()

        # Article 14: Human oversight
        self._check_article_14_human_oversight()

        # Article 15: Accuracy, robustness, cybersecurity
        self._check_article_15_accuracy()

        # Generate summary
        self._generate_summary()

        return self

    def _check_article_50_transparency(self) -> None:
        """Article 50: Transparency obligations for certain AI systems.

        (1) AI systems that generate or manipulate content must disclose
            that content is AI-generated.
        (2) Deepfake disclosure requirements.
        (3) AI-generated text in public information must be labeled.
        """
        # GreenFlex provides C2PA-compatible Token Passport
        self.checks.append(ComplianceCheck(
            article="Article 50(1)",
            requirement="Disclose AI-generated content",
            status="compliant" if self.platform_info.c2pa_support else "partial",
            evidence="GreenFlex generates C2PA-compatible Token Passports with content hashes and model attribution",
            recommendation="Ensure Token Passport is attached to all generated content outputs",
            severity="high",
        ))

        self.checks.append(ComplianceCheck(
            article="Article 50(2)",
            requirement="Deepfake disclosure",
            status="not_applicable",
            evidence="GreenFlex is text-only, no image/audio/video generation",
            severity="low",
        ))

    def _check_article_53_gpai(self) -> None:
        """Article 53: Obligations for providers of GPAI models.

        (1)(a) Technical documentation (Annex XI)
        (1)(b) Summary of training data content
        (1)(c) Alignment with copyright law
        (1)(d) Energy consumption reporting
        """
        # (a) Technical documentation
        self.checks.append(ComplianceCheck(
            article="Article 53(1)(a)",
            requirement="Maintain technical documentation (Annex XI)",
            status="partial",
            evidence="GreenFlex stores model metadata, performance metrics, and energy data. Full Annex XI documentation requires model provider input.",
            recommendation="Work with model providers to complete Annex XI technical documentation",
            severity="high",
        ))

        # (b) Training data summary
        has_training_data = bool(self.model_info and self.model_info.training_data_summary)
        self.checks.append(ComplianceCheck(
            article="Article 53(1)(b)",
            requirement="Publish summary of training data content",
            status="compliant" if has_training_data else "partial",
            evidence=self.model_info.training_data_summary if has_training_data else "Training data summary not provided by model provider",
            recommendation="Request training data summary from model provider (required for GPAI models)",
            severity="high",
        ))

        # (c) Copyright alignment
        self.checks.append(ComplianceCheck(
            article="Article 53(1)(c)",
            requirement="Respect copyright law (opt-out policy)",
            status="partial",
            evidence="GreenFlex does not train models, only runs inference. Copyright compliance is model provider's responsibility.",
            recommendation="Verify model provider has copyright compliance policy and opt-out mechanism",
            severity="high",
        ))

        # (d) Energy consumption reporting — GreenFlex strength
        has_energy_data = self.model_info and self.model_info.energy_provenance_tier != "insufficient_data"
        self.checks.append(ComplianceCheck(
            article="Article 53(1)(d)",
            requirement="Report energy consumption of GPAI model",
            status="compliant" if has_energy_data else "partial",
            evidence=(
                f"GreenFlex measures/reports energy consumption. "
                f"Current tier: {self.model_info.energy_provenance_tier if self.model_info else 'unknown'}. "
                f"Typical: {self.model_info.typical_energy_wh_per_1k_output if self.model_info else 0:.4f} Wh/1k output tokens"
            ),
            recommendation="Import more benchmark data to improve energy data provenance tier",
            severity="medium",
        ))

    def _check_article_10_data_governance(self) -> None:
        """Article 10: Data and data governance (high-risk systems)."""
        if self.model_info and self.model_info.risk_level != AIRiskLevel.HIGH:
            self.checks.append(ComplianceCheck(
                article="Article 10",
                requirement="Data governance for high-risk systems",
                status="not_applicable",
                evidence=f"Model risk level is {self.model_info.risk_level.value}, not high-risk",
                severity="low",
            ))
            return

        self.checks.append(ComplianceCheck(
            article="Article 10",
            requirement="Data governance for high-risk systems",
            status="partial",
            evidence="GreenFlex provides input/output hashing and audit logs. Full data governance requires organizational policies.",
            recommendation="Implement data governance policy for high-risk use cases",
            severity="high",
        ))

    def _check_article_11_technical_doc(self) -> None:
        """Article 11: Technical documentation (Annex IV for high-risk)."""
        self.checks.append(ComplianceCheck(
            article="Article 11",
            requirement="Maintain technical documentation",
            status="partial",
            evidence="GreenFlex maintains system documentation, model catalog, and energy data. Full Annex IV requires additional details.",
            recommendation="Complete Annex IV technical documentation template",
            severity="medium",
        ))

    def _check_article_12_record_keeping(self) -> None:
        """Article 12: Record-keeping (logs)."""
        self.checks.append(ComplianceCheck(
            article="Article 12",
            requirement="Automatic event logging",
            status="compliant" if self.platform_info.audit_logging else "non_compliant",
            evidence="GreenFlex logs all orders, recommendations, and system events with timestamps",
            recommendation="Ensure logs are retained for required period (typically 6 months for high-risk)",
            severity="medium",
        ))

    def _check_article_13_transparency(self) -> None:
        """Article 13: Transparency and provision of information to deployers."""
        self.checks.append(ComplianceCheck(
            article="Article 13",
            requirement="Provide instructions for use",
            status="compliant",
            evidence="GreenFlex provides model descriptions, capability tiers, and usage guidance in the model catalog",
            recommendation="Add AI Act-specific use case guidance to model descriptions",
            severity="medium",
        ))

        self.checks.append(ComplianceCheck(
            article="Article 13",
            requirement="Disclose intended purpose and limitations",
            status="partial",
            evidence="GreenFlex shows model capabilities but limitations are not standardized",
            recommendation="Add standardized 'known limitations' field to model catalog",
            severity="medium",
        ))

    def _check_article_14_human_oversight(self) -> None:
        """Article 14: Human oversight."""
        self.checks.append(ComplianceCheck(
            article="Article 14",
            requirement="Human oversight measures",
            status="compliant" if self.platform_info.human_oversight else "non_compliant",
            evidence="GreenFlex requires user confirmation for all orders. Shadow mode for RL router prevents autonomous execution.",
            recommendation="For high-risk use cases, implement mandatory human review of outputs",
            severity="high",
        ))

    def _check_article_15_accuracy(self) -> None:
        """Article 15: Accuracy, robustness, cybersecurity."""
        # Accuracy
        self.checks.append(ComplianceCheck(
            article="Article 15(1)",
            requirement="Achieve appropriate level of accuracy",
            status="partial",
            evidence=self.model_info.accuracy_notes if self.model_info and self.model_info.accuracy_notes else "Accuracy metrics not standardized across models",
            recommendation="Add standardized accuracy benchmarks to model catalog",
            severity="medium",
        ))

        # Robustness
        self.checks.append(ComplianceCheck(
            article="Article 15(2)",
            requirement="Robustness and resilience",
            status="partial",
            evidence=self.model_info.robustness_notes if self.model_info and self.model_info.robustness_notes else "Robustness testing not standardized",
            recommendation="Add adversarial testing results for high-risk use cases",
            severity="medium",
        ))

        # Cybersecurity
        self.checks.append(ComplianceCheck(
            article="Article 15(3)",
            requirement="Cybersecurity",
            status="compliant",
            evidence="GreenFlex API binds to 127.0.0.1 only, no external exposure. Content can be purged. No user authentication needed for local single-tenant.",
            recommendation="For multi-tenant deployment, implement authentication and authorization",
            severity="high",
        ))

    def _generate_summary(self) -> None:
        """Generate compliance summary."""
        total = len(self.checks)
        compliant = sum(1 for c in self.checks if c.status == "compliant")
        partial = sum(1 for c in self.checks if c.status == "partial")
        non_compliant = sum(1 for c in self.checks if c.status == "non_compliant")
        not_applicable = sum(1 for c in self.checks if c.status == "not_applicable")

        applicable = total - not_applicable
        compliance_score = (compliant + 0.5 * partial) / max(applicable, 1) * 100

        high_severity_issues = [
            c for c in self.checks
            if c.severity in ("high", "critical") and c.status in ("partial", "non_compliant")
        ]

        self.summary = {
            "total_checks": total,
            "compliant": compliant,
            "partial": partial,
            "non_compliant": non_compliant,
            "not_applicable": not_applicable,
            "applicable_checks": applicable,
            "compliance_score_percent": round(compliance_score, 1),
            "risk_level": self.model_info.risk_level.value if self.model_info else "unknown",
            "high_severity_issues_count": len(high_severity_issues),
            "high_severity_issues": [
                {"article": c.article, "requirement": c.requirement, "status": c.status}
                for c in high_severity_issues
            ],
            "overall_status": (
                "compliant" if non_compliant == 0 and partial == 0
                else "partial" if non_compliant == 0
                else "non_compliant"
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "regulation": self.regulation,
            "report_version": self.report_version,
            "summary": self.summary,
            "model_info": asdict(self.model_info) if self.model_info else None,
            "platform_info": asdict(self.platform_info),
            "checks": [c.to_dict() for c in self.checks],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Generate human-readable Markdown report."""
        lines = []
        lines.append(f"# EU AI Act Compliance Report")
        lines.append("")
        lines.append(f"**Report ID:** {self.report_id}")
        lines.append(f"**Generated:** {self.generated_at}")
        lines.append(f"**Regulation:** {self.regulation}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        s = self.summary
        lines.append(f"- **Overall Status:** {s.get('overall_status', 'unknown').upper()}")
        lines.append(f"- **Compliance Score:** {s.get('compliance_score_percent', 0)}%")
        lines.append(f"- **Risk Level:** {s.get('risk_level', 'unknown')}")
        lines.append(f"- **Checks:** {s.get('compliant', 0)} compliant, {s.get('partial', 0)} partial, {s.get('non_compliant', 0)} non-compliant, {s.get('not_applicable', 0)} N/A")
        lines.append("")

        if s.get("high_severity_issues"):
            lines.append("### High Severity Issues")
            lines.append("")
            for issue in s["high_severity_issues"]:
                lines.append(f"- **{issue['article']}** — {issue['requirement']} ({issue['status']})")
            lines.append("")

        # Model info
        if self.model_info:
            lines.append("## Model Information")
            lines.append("")
            lines.append(f"- **Model:** {self.model_info.model_name} ({self.model_info.model_id})")
            lines.append(f"- **Version:** {self.model_info.model_version}")
            lines.append(f"- **Provider:** {self.model_info.provider}")
            lines.append(f"- **Parameters:** {self.model_info.parameter_count_b}B" if self.model_info.parameter_count_b else "- **Parameters:** Unknown")
            lines.append(f"- **Intended Use:** {self.model_info.intended_use}")
            lines.append("")

        # Detailed checks
        lines.append("## Detailed Compliance Checks")
        lines.append("")
        for check in self.checks:
            status_icon = {
                "compliant": "✅",
                "partial": "⚠️",
                "non_compliant": "❌",
                "not_applicable": "➖",
            }.get(check.status, "❓")
            lines.append(f"### {status_icon} {check.article}: {check.requirement}")
            lines.append("")
            lines.append(f"- **Status:** {check.status}")
            lines.append(f"- **Severity:** {check.severity}")
            if check.evidence:
                lines.append(f"- **Evidence:** {check.evidence}")
            if check.recommendation:
                lines.append(f"- **Recommendation:** {check.recommendation}")
            lines.append("")

        # GreenFlex strengths
        lines.append("## GreenFlex Compliance Strengths")
        lines.append("")
        lines.append("1. **C2PA-compatible Token Passport** — AI-generated content disclosure (Article 50)")
        lines.append("2. **Energy consumption reporting** — Measured/estimated energy and carbon (Article 53(1)(d))")
        lines.append("3. **Audit logging** — All orders and recommendations logged (Article 12)")
        lines.append("4. **Human oversight** — User confirmation required for all actions (Article 14)")
        lines.append("5. **Local-first security** — API bound to 127.0.0.1, no external exposure (Article 15)")
        lines.append("6. **Content purge** — Prompts and outputs can be deleted (data minimization)")
        lines.append("")

        lines.append("---")
        lines.append(f"*Generated by GreenFlex v{self.platform_info.version}*")

        return "\n".join(lines)

    def export_to_file(self, path: str | Path, format: str = "json") -> Path:
        """Export report to file (json or markdown)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if format == "markdown":
            path.write_text(self.to_markdown(), encoding="utf-8")
        else:
            path.write_text(self.to_json(), encoding="utf-8")
        return path


def generate_compliance_report(model_info: ModelComplianceInfo | None = None,
                               platform_info: GreenFlexComplianceInfo | None = None) -> AIActComplianceReport:
    """Convenience function to generate a compliance report."""
    report = AIActComplianceReport()
    if platform_info:
        report.platform_info = platform_info
    return report.assess(model_info)
