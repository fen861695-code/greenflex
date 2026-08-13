# ADR 0009: C2PA-Compatible Token Passport

## Status

Accepted

## Context

The EU AI Act (Article 50) and emerging regulations require AI-generated content
to be clearly labeled and traceable. The C2PA (Coalition for Content Provenance
and Authenticity) standard provides a vendor-neutral format for content
provenance information.

GreenFlex's existing Token Passport records model usage, energy, and carbon
data, but it is a GreenFlex-specific format. To support interoperability and
regulatory compliance, we need C2PA-compatible manifests.

## Decision

Extend Token Passport with C2PA 1.3-compatible manifest generation and
verification.

### C2PA Manifest Structure

Each passport includes a C2PA manifest with:

1. **Standard C2PA assertions**:
   - `c2pa.actions`: Records `c2pa.ai_generated` action with software agent info
   - `c2pa.creative-work`: Describes the generated content as type "Text"

2. **GreenFlex custom assertions** (vendor namespace):
   - `greenflex.model_usage`: Model ID, token counts, latency, content hashes
   - `greenflex.energy_usage`: Energy, carbon, provenance tier
   - `greenflex.provenance`: Passport metadata, data truth boundary

3. **Signature**: HMAC-SHA256 (simplified for local use)

### Signing Approach

Full C2PA uses COSE signatures with X.509 certificate chains. For GreenFlex's
local-first single-tenant use case:
- HMAC-SHA256 provides equivalent integrity guarantees
- No certificate management required
- Secret key configurable via `GREENFLEX_C2PA_SECRET_KEY`
- Clearly documented as "C2PA-compatible" not "C2PA-certified"

### Content Privacy

C2PA manifests contain **hashes only** (SHA-256), never raw prompt or output
text. This preserves GreenFlex's content-free audit principle.

### API Endpoints

- `GET /api/v1/passports/{passport_id}/c2pa` — Generate C2PA manifest for a passport
- `POST /api/v1/c2pa/verify` — Verify a C2PA manifest

## Consequences

### Positive
- Interoperability with C2PA-compliant tools and viewers
- EU AI Act Article 50 transparency compliance
- Content integrity verification
- Preserves content privacy (hashes only)

### Negative
- HMAC-SHA256 is not full C2PA COSE signature — may need upgrade for
  enterprise/multi-tenant use
- Custom assertions require GreenFlex-aware tools to fully interpret
- Manifest size increases passport storage

### Risks
- C2PA specification evolves — need to track updates
- Key management: if secret key is lost, old passports cannot be verified

## Future Work

- Upgrade to COSE signatures with X.509 certificates for enterprise use
- Embed C2PA manifest directly into output text (metadata)
- Support C2PA manifest chains (ingredients for multi-step workflows)
- Integration with C2PA validator tools
