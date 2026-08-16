#!/usr/bin/env python3
"""Standalone verification of RL Router, C2PA, and AI Act Compliance.

This script does NOT depend on the full GreenFlex project. It imports the
new modules directly and verifies their core functionality.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add backend src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend" / "src"))


def test_rl_router():
    """Test RL Router core functionality."""
    print("\n" + "=" * 70)
    print("Test 1: RL Router (PPO)")
    print("=" * 70)

    from greenflex.rl_router import (
        RLRouter, RLMode, RLPolicy, RLPolicyConfig, RLState, RLAction,
    )

    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name} — {detail}")
            failed += 1

    # Test policy config
    config = RLPolicyConfig()
    issues = config.validate()
    check("Policy config validates", len(issues) == 0, f"issues: {issues}")

    # Test policy initialization
    policy = RLPolicy(config=config)
    policy.initialize(state_dim=10, action_dim=5)
    check("Policy initialized", policy.is_initialized())

    # Test action selection
    state = RLState(input_tokens=100, output_tokens_est=200, task_type="general")
    candidates = ["model-a", "model-b", "model-c", "model-d", "model-e"]
    action = policy.select_action(state, candidates)
    check("Action selection returns valid model", action.model_id in candidates)
    check("Action confidence in [0,1]", 0 <= action.confidence <= 1)
    check("Action log_prob is negative", action.log_prob <= 0)

    # Test reward computation
    result = {
        "quality_score": 0.8,
        "price_normalized": 0.3,
        "energy_normalized": 0.4,
        "carbon_normalized": 0.5,
        "latency_normalized": 0.2,
        "wait_normalized": 0.1,
        "renewable_share": 0.6,
        "deadline_met": True,
        "quality_met": True,
    }
    reward = policy.compute_reward(result)
    check("Reward in [-1, 1]", -1 <= reward <= 1, f"reward={reward}")
    check("Reward is positive for good result", reward > 0, f"reward={reward}")

    # Test RL Router
    router = RLRouter(policy=policy, mode=RLMode.SHADOW)
    router.candidate_model_ids = candidates
    check("Router created in shadow mode", router.mode == RLMode.SHADOW)

    # Test recommendation
    rec = router.recommend(state, rule_based_model_id="model-a")
    check("Recommendation returns dict", isinstance(rec, dict))
    check("Recommendation has rl_model_id", "rl_model_id" in rec)
    check("Shadow mode uses rule-based", rec["effective_model_id"] == "model-a")

    # Test mode switching
    router.set_mode(RLMode.ADVISORY)
    check("Can switch to advisory mode", router.mode == RLMode.ADVISORY)

    # Test stats
    stats = router.get_stats()
    check("Stats returns dict", isinstance(stats, dict))
    check("Stats has policy_version", "policy_version" in stats)

    # Test policy save/load
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        policy.save(f.name)
        loaded = RLPolicy.load(f.name)
        check("Policy save/load preserves version", loaded.version == policy.version)
        check("Policy save/load preserves updates", loaded.total_updates == policy.total_updates)
        Path(f.name).unlink()

    print(f"\n  RL Router: {passed} passed, {failed} failed")
    return failed == 0


def test_c2pa():
    """Test C2PA Token Passport."""
    print("\n" + "=" * 70)
    print("Test 2: C2PA Token Passport")
    print("=" * 70)

    from greenflex.c2pa import (
        TokenPassportC2PA, C2PAManifest, C2PAVerifier, C2PAAssertionType,
    )

    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name} — {detail}")
            failed += 1

    # Test passport creation
    passport = TokenPassportC2PA(
        model_id="qwen2.5-7b",
        model_display_name="Qwen2.5 7B",
        input_tokens=100,
        output_tokens=200,
        total_tokens=300,
        latency_ms=5000,
        energy_micro_wh=50000,
        carbon_micro_g=30000,
        energy_provenance_tier="l3_cross_gpu_normalized",
    )
    check("Passport created", passport.model_id == "qwen2.5-7b")

    # Test C2PA manifest generation
    secret = "test-secret-key"
    manifest = passport.generate_c2pa_manifest(secret_key=secret)
    check("Manifest generated", manifest is not None)
    check("Manifest has claim", manifest.claim is not None)
    check("Manifest has signature", manifest.signature.signature != "")

    # Test assertions
    assertion_types = [a.type for a in manifest.claim.assertions]
    check("Has c2pa.actions assertion", C2PAAssertionType.ACTIONS.value in assertion_types)
    check("Has greenflex.model_usage assertion", C2PAAssertionType.GREENFLEX_MODEL_USAGE.value in assertion_types)
    check("Has greenflex.energy_usage assertion", C2PAAssertionType.GREENFLEX_ENERGY_USAGE.value in assertion_types)
    check("Has greenflex.provenance assertion", C2PAAssertionType.GREENFLEX_PROVENANCE.value in assertion_types)

    # Test signature verification
    check("Valid signature verifies", passport.verify_c2pa_manifest(secret_key=secret))
    check("Invalid key fails verification", not passport.verify_c2pa_manifest(secret_key="wrong-key"))

    # Test JSON serialization
    json_str = passport.to_json()
    check("JSON serialization works", isinstance(json_str, str))
    check("JSON contains manifest", "c2pa_manifest" in json_str)

    # Test manifest from JSON
    manifest_json = manifest.to_json()
    loaded_manifest = C2PAManifest.from_json(manifest_json)
    check("Manifest from JSON preserves ID", loaded_manifest.manifest_id == manifest.manifest_id)

    # Test verifier
    verifier = C2PAVerifier(secret_key=secret)
    passport_dict = passport.to_dict()
    verification = verifier.verify_dict(passport_dict)
    check("Verifier returns valid=True", verification["valid"] == True)
    check("Verifier extracts model_usage", "model_usage" in verification)

    # Test summary extraction
    summary = verifier.extract_passport_summary(passport_dict)
    check("Summary extraction works", summary["valid"] == True)
    check("Summary has model name", summary["model"] == "Qwen2.5 7B")

    # Test from_order_result
    order_result = {
        "model_id": "llama3-8b",
        "model_display_name": "Llama 3 8B",
        "input_tokens": 50,
        "output_tokens": 100,
        "total_tokens": 150,
        "latency_ms": 3000,
        "energy_micro_wh": 30000,
        "carbon_micro_g": 20000,
        "input_text": "Hello world",
        "output_text": "Hi there",
    }
    passport2 = TokenPassportC2PA.from_order_result(order_result, secret_key=secret)
    check("From order result works", passport2.model_id == "llama3-8b")
    check("Input hash computed", passport2.input_hash != "")
    check("Output hash computed", passport2.output_hash != "")

    print(f"\n  C2PA: {passed} passed, {failed} failed")
    return failed == 0


def test_ai_act():
    """Test AI Act Compliance Report."""
    print("\n" + "=" * 70)
    print("Test 3: AI Act Compliance Report")
    print("=" * 70)

    from greenflex.ai_act_compliance import (
        AIActComplianceReport, ModelComplianceInfo, GreenFlexComplianceInfo,
        AIRiskLevel, generate_compliance_report,
    )

    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name} — {detail}")
            failed += 1

    # Test platform info
    platform = GreenFlexComplianceInfo(
        version="0.1.0",
        c2pa_support=True,
        energy_reporting=True,
    )
    check("Platform info created", platform.version == "0.1.0")

    # Test model info
    model = ModelComplianceInfo(
        model_id="qwen2.5-7b",
        model_name="Qwen2.5 7B",
        parameter_count_b=7.0,
        risk_level=AIRiskLevel.LIMITED,
        energy_provenance_tier="l3_cross_gpu_normalized",
        typical_energy_wh_per_1k_output=0.05,
    )
    check("Model info created", model.model_id == "qwen2.5-7b")

    # Test report generation
    report = generate_compliance_report(model_info=model, platform_info=platform)
    check("Report generated", report is not None)
    check("Report has checks", len(report.checks) > 0)
    check("Report has summary", "compliance_score_percent" in report.summary)

    # Test specific articles
    articles_covered = {c.article for c in report.checks}
    check("Covers Article 50", any("50" in a for a in articles_covered))
    check("Covers Article 53", any("53" in a for a in articles_covered))
    check("Covers Article 12", any("12" in a for a in articles_covered))
    check("Covers Article 14", any("14" in a for a in articles_covered))
    check("Covers Article 15", any("15" in a for a in articles_covered))

    # Test energy reporting (GreenFlex strength)
    energy_checks = [c for c in report.checks if "energy" in c.requirement.lower() or "53(1)(d)" in c.article]
    check("Has energy reporting check", len(energy_checks) > 0)
    if energy_checks:
        check("Energy reporting is compliant/partial",
              energy_checks[0].status in ("compliant", "partial"))

    # Test C2PA compliance (GreenFlex strength)
    c2pa_checks = [c for c in report.checks if "c2pa" in c.evidence.lower() or "token passport" in c.evidence.lower()]
    check("Has C2PA-related check", len(c2pa_checks) > 0)

    # Test JSON output
    json_str = report.to_json()
    check("JSON serialization works", isinstance(json_str, str))
    check("JSON has summary", "summary" in json_str)

    # Test Markdown output
    md = report.to_markdown()
    check("Markdown generation works", isinstance(md, str))
    check("Markdown has title", "# EU AI Act Compliance Report" in md)
    check("Markdown has summary section", "## Summary" in md)
    check("Markdown has detailed checks", "## Detailed Compliance Checks" in md)

    # Test compliance score
    score = report.summary.get("compliance_score_percent", 0)
    check("Compliance score is reasonable", 0 <= score <= 100, f"score={score}")

    # Test high-risk model
    high_risk_model = ModelComplianceInfo(
        model_id="medical-ai",
        model_name="Medical AI",
        risk_level=AIRiskLevel.HIGH,
    )
    high_risk_report = generate_compliance_report(model_info=high_risk_model)
    check("High-risk model triggers Article 10",
          any("10" in c.article for c in high_risk_report.checks))

    print(f"\n  AI Act: {passed} passed, {failed} failed")
    return failed == 0


def main():
    print("=" * 70)
    print("GreenFlex v2 Feature Verification")
    print("RL Router + C2PA + AI Act Compliance")
    print("=" * 70)

    results = []
    try:
        results.append(("RL Router", test_rl_router()))
    except Exception as e:
        print(f"\n  [ERROR] RL Router test failed: {e}")
        import traceback
        traceback.print_exc()
        results.append(("RL Router", False))

    try:
        results.append(("C2PA", test_c2pa()))
    except Exception as e:
        print(f"\n  [ERROR] C2PA test failed: {e}")
        import traceback
        traceback.print_exc()
        results.append(("C2PA", False))

    try:
        results.append(("AI Act", test_ai_act()))
    except Exception as e:
        print(f"\n  [ERROR] AI Act test failed: {e}")
        import traceback
        traceback.print_exc()
        results.append(("AI Act", False))

    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("All features verified successfully!")
    else:
        print("Some features failed verification.")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
