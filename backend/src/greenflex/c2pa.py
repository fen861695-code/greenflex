"""C2PA-compatible Token Passport for GreenFlex.

Implements a C2PA (Coalition for Content Provenance and Authenticity)
compatible manifest for AI-generated content provenance.

C2PA specification: https://c2pa.org/specifications/

This implementation follows C2PA 1.3 specification structure:
- Manifest: container for claims and signatures
- Claim: describes what was created and how
- Assertion: specific claims about the content (actions, ingredients, etc.)
- Signature: cryptographic signature of the claim

GreenFlex extensions (C2PA allows custom assertions under vendor namespace):
- greenflex.model_usage: token counts, model info
- greenflex.energy_usage: energy and carbon data
- greenflex.provenance_tier: data confidence level

Note: This is a compatible but simplified implementation. Full C2PA compliance
requires X.509 certificate chains and COSE signatures. GreenFlex uses HMAC-SHA256
for local signing, which is valid for local-first single-tenant use.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class C2PAAssertionType(str, Enum):
    """C2PA standard assertion types."""
    ACTIONS = "c2pa.actions"
    INGREDIENTS = "c2pa.ingredients"
    CREATIVE_WORK = "c2pa.creative-work"
    TRAINING_DATA = "c2pa.training-data"
    # GreenFlex custom assertions (vendor namespace)
    GREENFLEX_MODEL_USAGE = "greenflex.model_usage"
    GREENFLEX_ENERGY_USAGE = "greenflex.energy_usage"
    GREENFLEX_PROVENANCE = "greenflex.provenance"


class C2PAAction(str, Enum):
    """C2PA standard actions."""
    CREATED = "c2pa.created"
    EDITED = "c2pa.edited"
    FORMATTED = "c2pa.formatted"
    PLACED = "c2pa.placed"
    REMOVED = "c2pa.removed"
    ASSEMBLED = "c2pa.assembled"
    # AI-specific actions (C2PA 1.3+)
    AI_GENERATED = "c2pa.ai_generated"
    AI_ASSISTED = "c2pa.ai_assisted"
    AI_TRAINED = "c2pa.ai_trained"


@dataclass
class C2PAAssertion:
    """A single C2PA assertion."""
    type: str
    data: dict[str, Any]
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {"type": self.type, "data": self.data}
        if self.label:
            result["label"] = self.label
        return result


@dataclass
class C2PAClaim:
    """C2PA Claim — describes what was created and how."""
    claim_generator: str = "GreenFlex v0.1.0"
    claim_generator_software: str = "greenflex"
    claim_generator_version: str = "0.1.0"
    assertions: list[C2PAAssertion] = field(default_factory=list)
    claim_id: str = field(default_factory=lambda: f"urn:uuid:{uuid.uuid4()}")
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_generator": self.claim_generator,
            "claim_generator_software": self.claim_generator_software,
            "claim_generator_version": self.claim_generator_version,
            "claim_id": self.claim_id,
            "created_at": self.created_at,
            "assertions": [a.to_dict() for a in self.assertions],
        }


@dataclass
class C2PASignature:
    """C2PA Signature (simplified HMAC-SHA256 for local use).

    Full C2PA uses COSE signatures with X.509 certificates. For local-first
    single-tenant use, HMAC-SHA256 provides equivalent integrity guarantees
    without requiring certificate management.
    """
    algorithm: str = "HS256"  # HMAC-SHA256
    key_id: str = "greenflex-local-key"
    signature: str = ""  # hex-encoded signature

    def sign(self, claim_bytes: bytes, secret_key: str) -> None:
        """Sign claim bytes with HMAC-SHA256."""
        self.signature = hmac.new(
            secret_key.encode("utf-8"),
            claim_bytes,
            hashlib.sha256,
        ).hexdigest()

    def verify(self, claim_bytes: bytes, secret_key: str) -> bool:
        """Verify signature."""
        expected = hmac.new(
            secret_key.encode("utf-8"),
            claim_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, self.signature)

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "signature": self.signature,
        }


@dataclass
class C2PAManifest:
    """C2PA Manifest — top-level container.

    Structure follows C2PA 1.3 specification:
    - manifest: contains claim and signature
    - claim: describes creation
    - signature: cryptographic proof
    """
    manifest_id: str = field(default_factory=lambda: f"urn:uuid:{uuid.uuid4()}")
    claim: C2PAClaim = field(default_factory=C2PAClaim)
    signature: C2PASignature = field(default_factory=C2PASignature)
    format_version: str = "1.3"
    title: str = "GreenFlex Token Passport"

    def sign_manifest(self, secret_key: str) -> None:
        """Sign the claim and create signature."""
        claim_bytes = json.dumps(self.claim.to_dict(), sort_keys=True).encode("utf-8")
        self.signature.sign(claim_bytes, secret_key)

    def verify_manifest(self, secret_key: str) -> bool:
        """Verify the manifest signature."""
        claim_bytes = json.dumps(self.claim.to_dict(), sort_keys=True).encode("utf-8")
        return self.signature.verify(claim_bytes, secret_key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "manifest_id": self.manifest_id,
            "title": self.title,
            "claim": self.claim.to_dict(),
            "signature": self.signature.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "C2PAManifest":
        data = json.loads(json_str)
        claim_data = data["claim"]
        claim = C2PAClaim(
            claim_generator=claim_data["claim_generator"],
            claim_generator_software=claim_data["claim_generator_software"],
            claim_generator_version=claim_data["claim_generator_version"],
            claim_id=claim_data["claim_id"],
            created_at=claim_data["created_at"],
            assertions=[
                C2PAAssertion(type=a["type"], data=a["data"], label=a.get("label"))
                for a in claim_data["assertions"]
            ],
        )
        sig_data = data["signature"]
        signature = C2PASignature(
            algorithm=sig_data["algorithm"],
            key_id=sig_data["key_id"],
            signature=sig_data["signature"],
        )
        return cls(
            manifest_id=data["manifest_id"],
            claim=claim,
            signature=signature,
            format_version=data["format_version"],
            title=data["title"],
        )


@dataclass
class TokenPassportC2PA:
    """GreenFlex Token Passport with C2PA compatibility.

    Extends the existing Token Passport with C2PA manifest generation.
    The passport contains:
    - Content hash (SHA-256 of input/output, not the content itself)
    - Model information
    - Token usage
    - Energy and carbon data
    - Provenance tier
    - C2PA manifest with assertions and signature
    """
    # Content identifiers (hashes only, no raw content)
    input_hash: str = ""
    output_hash: str = ""

    # Model info
    model_id: str = ""
    model_display_name: str = ""
    model_version: str = ""

    # Usage
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0

    # Energy and carbon
    energy_micro_wh: int = 0
    carbon_micro_g: int = 0
    energy_provenance_tier: str = "insufficient_data"
    carbon_provenance: str = "simulated"

    # Metadata
    passport_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    order_id: str | None = None

    # C2PA manifest
    c2pa_manifest: C2PAManifest | None = None

    def generate_c2pa_manifest(self, secret_key: str = "greenflex-local") -> C2PAManifest:
        """Generate a C2PA-compatible manifest for this passport.

        Creates standard C2PA assertions plus GreenFlex custom assertions.
        """
        manifest = C2PAManifest(title=f"GreenFlex Token Passport — {self.model_id}")

        # Standard C2PA actions assertion
        actions_assertion = C2PAAssertion(
            type=C2PAAssertionType.ACTIONS.value,
            data={
                "actions": [
                    {
                        "action": C2PAAction.AI_GENERATED.value,
                        "digital_source_type": "trainedAlgorithmicMedia",
                        "software_agent": {
                            "name": self.model_display_name or self.model_id,
                            "version": self.model_version,
                        },
                    }
                ]
            },
            label="greenflex-generation-action",
        )
        manifest.claim.assertions.append(actions_assertion)

        # Standard creative work assertion
        creative_work_assertion = C2PAAssertion(
            type=C2PAAssertionType.CREATIVE_WORK.value,
            data={
                "creative_work": {
                    "type": "Text",
                    "name": "AI-generated text",
                    "description": f"Generated by {self.model_display_name or self.model_id} via GreenFlex",
                    "identifier": self.passport_id,
                }
            },
            label="greenflex-creative-work",
        )
        manifest.claim.assertions.append(creative_work_assertion)

        # GreenFlex custom: model usage
        model_usage_assertion = C2PAAssertion(
            type=C2PAAssertionType.GREENFLEX_MODEL_USAGE.value,
            data={
                "model_id": self.model_id,
                "model_display_name": self.model_display_name,
                "model_version": self.model_version,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens,
                "latency_ms": self.latency_ms,
                "input_hash_sha256": self.input_hash,
                "output_hash_sha256": self.output_hash,
            },
            label="greenflex-model-usage",
        )
        manifest.claim.assertions.append(model_usage_assertion)

        # GreenFlex custom: energy usage
        energy_usage_assertion = C2PAAssertion(
            type=C2PAAssertionType.GREENFLEX_ENERGY_USAGE.value,
            data={
                "energy_micro_wh": self.energy_micro_wh,
                "energy_wh": self.energy_micro_wh / 1_000_000,
                "carbon_micro_gco2e": self.carbon_micro_g,
                "carbon_gco2e": self.carbon_micro_g / 1_000_000,
                "energy_provenance_tier": self.energy_provenance_tier,
                "carbon_provenance": self.carbon_provenance,
            },
            label="greenflex-energy-usage",
        )
        manifest.claim.assertions.append(energy_usage_assertion)

        # GreenFlex custom: provenance
        provenance_assertion = C2PAAssertion(
            type=C2PAAssertionType.GREENFLEX_PROVENANCE.value,
            data={
                "passport_id": self.passport_id,
                "order_id": self.order_id,
                "created_at": self.created_at,
                "generator": "GreenFlex",
                "generator_version": "0.1.0",
                "data_truth_boundary": {
                    "measured": ["token counts", "latency", "GPU energy when telemetry available"],
                    "estimated": ["facility energy from GPU energy + PUE assumption"],
                    "simulated": ["electricity price", "grid carbon intensity", "service prices"],
                },
            },
            label="greenflex-provenance",
        )
        manifest.claim.assertions.append(provenance_assertion)

        # Sign the manifest
        manifest.sign_manifest(secret_key)
        self.c2pa_manifest = manifest

        return manifest

    def verify_c2pa_manifest(self, secret_key: str = "greenflex-local") -> bool:
        """Verify the C2PA manifest signature."""
        if self.c2pa_manifest is None:
            return False
        return self.c2pa_manifest.verify_manifest(secret_key)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "passport_id": self.passport_id,
            "created_at": self.created_at,
            "order_id": self.order_id,
            "model_id": self.model_id,
            "model_display_name": self.model_display_name,
            "model_version": self.model_version,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "energy_micro_wh": self.energy_micro_wh,
            "carbon_micro_g": self.carbon_micro_g,
            "energy_provenance_tier": self.energy_provenance_tier,
            "carbon_provenance": self.carbon_provenance,
            "input_hash_sha256": self.input_hash,
            "output_hash_sha256": self.output_hash,
        }
        if self.c2pa_manifest:
            result["c2pa_manifest"] = self.c2pa_manifest.to_dict()
        return result

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def export_to_file(self, path: str | Path, secret_key: str = "greenflex-local") -> Path:
        """Export passport with C2PA manifest to JSON file."""
        if self.c2pa_manifest is None:
            self.generate_c2pa_manifest(secret_key)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def from_order_result(cls, order_result: dict[str, Any], secret_key: str = "greenflex-local") -> "TokenPassportC2PA":
        """Create a TokenPassportC2PA from an order execution result."""
        passport = cls(
            model_id=order_result.get("model_id", ""),
            model_display_name=order_result.get("model_display_name", ""),
            model_version=order_result.get("model_version", ""),
            input_tokens=order_result.get("input_tokens", 0),
            output_tokens=order_result.get("output_tokens", 0),
            total_tokens=order_result.get("total_tokens", 0),
            latency_ms=order_result.get("latency_ms", 0),
            energy_micro_wh=order_result.get("energy_micro_wh", 0),
            carbon_micro_g=order_result.get("carbon_micro_g", 0),
            energy_provenance_tier=order_result.get("energy_provenance_tier", "insufficient_data"),
            carbon_provenance=order_result.get("carbon_provenance", "simulated"),
            order_id=order_result.get("order_id"),
        )

        # Compute content hashes (if content provided)
        input_text = order_result.get("input_text", "")
        output_text = order_result.get("output_text", "")
        if input_text:
            passport.input_hash = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
        if output_text:
            passport.output_hash = hashlib.sha256(output_text.encode("utf-8")).hexdigest()

        # Generate C2PA manifest
        passport.generate_c2pa_manifest(secret_key)

        return passport


class C2PAVerifier:
    """Verify C2PA manifests and extract provenance information."""

    def __init__(self, secret_key: str = "greenflex-local"):
        self.secret_key = secret_key

    def verify_file(self, path: str | Path) -> dict[str, Any]:
        """Verify a C2PA manifest from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return self.verify_dict(data)

    def verify_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Verify a C2PA manifest from a dict."""
        if "c2pa_manifest" not in data:
            return {"valid": False, "error": "No C2PA manifest found"}

        manifest_data = data["c2pa_manifest"]
        try:
            manifest = C2PAManifest.from_json(json.dumps(manifest_data))
        except (KeyError, json.JSONDecodeError) as e:
            return {"valid": False, "error": f"Invalid manifest format: {e}"}

        signature_valid = manifest.verify_manifest(self.secret_key)

        # Extract assertions
        assertions = {}
        for a in manifest.claim.assertions:
            assertions[a.type] = a.data

        return {
            "valid": signature_valid,
            "manifest_id": manifest.manifest_id,
            "claim_id": manifest.claim.claim_id,
            "created_at": manifest.claim.created_at,
            "claim_generator": manifest.claim.claim_generator,
            "assertion_types": list(assertions.keys()),
            "model_usage": assertions.get("greenflex.model_usage", {}),
            "energy_usage": assertions.get("greenflex.energy_usage", {}),
            "provenance": assertions.get("greenflex.provenance", {}),
            "actions": assertions.get("c2pa.actions", {}),
        }

    def extract_passport_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        """Extract human-readable passport summary."""
        verification = self.verify_dict(data)
        if not verification["valid"]:
            return {"valid": False, "error": verification["error"]}

        model_usage = verification["model_usage"]
        energy_usage = verification["energy_usage"]

        return {
            "valid": True,
            "passport_id": data.get("passport_id", "unknown"),
            "model": model_usage.get("model_display_name", model_usage.get("model_id", "unknown")),
            "tokens": {
                "input": model_usage.get("input_tokens", 0),
                "output": model_usage.get("output_tokens", 0),
                "total": model_usage.get("total_tokens", 0),
            },
            "energy": {
                "wh": energy_usage.get("energy_wh", 0),
                "carbon_g": energy_usage.get("carbon_gco2e", 0),
                "provenance_tier": energy_usage.get("energy_provenance_tier", "unknown"),
            },
            "created_at": verification["created_at"],
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
