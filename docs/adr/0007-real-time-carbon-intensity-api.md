# ADR 0007: Real-Time Grid Carbon Intensity API

## Status

Accepted

## Context

GreenFlex estimates carbon emissions from GPU energy consumption using a
fixed grid carbon intensity factor (550 gCO2/kWh, East China grid average).
This has several limitations:

1. **No temporal variation** — carbon intensity varies significantly by time
   of day (solar midday vs. coal evening peak), by up to 40%.
2. **No regional variation** — China has 6 regional grids with very different
   carbon intensities: Yunnan (hydro, ~350 g/kWh) vs. Shanxi (coal, ~880 g/kWh).
3. **No renewable signal** — cannot detect "green windows" when renewable
   share is high, which is the whole point of flexible scheduling.
4. **Provenance unclear** — synthetic data is labeled SIMULATED, but users
   want real data when available.

## Decision

Implement a multi-backend carbon intensity service with graceful degradation:

### Provider Chain (Priority Order)

1. **Electricity Maps API** — global real-time carbon intensity, free tier
   available. Primary provider for international users.
   - Endpoint: `GET /v3/carbon-intensity/latest?zone={zone}`
   - Auth: `auth-token` header
   - Free tier: limited requests/hour (cache required)

2. **DynLCA China Regional Data** — open-source dataset based on CEPD
   (China Electricity Planning & Design Institute) public data. Primary
   provider for China users when Electricity Maps zone data is unavailable.
   - 31 provincial baseline carbon intensities
   - Time-of-day variation (evening peak +10%, midday solar -15%)
   - China industrial TOU pricing
   - No API key required

3. **Synthetic Fallback** — original synthetic signal, clearly labeled
   SIMULATED. Always available.

### Caching Strategy

- 15-minute TTL cache in `carbon_intensity_cache` table
- Cache key: (region_code, 15-minute interval slot)
- Stale cache used when all providers fail (better than nothing)
- All cache records include provenance and data source version

### Degradation Behavior

```
Request → DB cache (fresh)? → return cached
         → no → Electricity Maps (key configured)? → cache + return
                   → fail → DynLCA (China)? → cache + return
                             → fail → stale DB cache? → return
                                       → fail → synthetic fallback
```

Every degradation is logged with the reason. The response always includes
`provenance` so the UI can show "real-time API" vs. "simulated".

### Database Schema

New table `carbon_intensity_cache`:
- `region_code` — e.g., "CN-HN" (Hunan)
- `zone` — Electricity Maps zone, e.g., "CN-CS"
- `interval_start` — 15-minute slot
- `carbon_g_per_kwh` — carbon intensity
- `renewable_share_bps` — renewable percentage
- `power_mix_json` — optional power breakdown
- `data_source` — provider name
- `data_source_version` — provider version string
- `provenance` — estimated/simulated
- `fetched_at`, `expires_at` — cache management

### Configuration

New environment variables:
- `GREENFLEX_ELECTRICITY_MAPS_API_KEY` — API key (optional)
- `GREENFLEX_CARBON_INTENSITY_REGION` — default "CN-HN" (Hunan/Changsha)
- `GREENFLEX_ELECTRICITY_MAPS_ZONE` — default "CN-CS" (Central-South China)
- `GREENFLEX_CARBON_INTENSITY_CACHE_TTL_MINUTES` — default 15
- `GREENFLEX_CARBON_PROVIDER_CHAIN` — default "electricity_maps,dynlca,fallback"

## Consequences

### Positive
- Real-time carbon intensity enables true "green window" scheduling
- Regional accuracy: Changsha (620 g/kWh) vs. Kunming (350 g/kWh)
- Time-of-day variation: midday solar reduces carbon by 15%
- Graceful degradation ensures service always available
- Clear provenance labeling builds user trust
- China-specific data via DynLCA (Electricity Maps China coverage is limited)

### Negative
- API key management for Electricity Maps (free tier has rate limits)
- More complex service with multiple backends
- Cache invalidation logic adds complexity
- DynLCA data is static (2023 baseline), not truly real-time

### Risks
- Electricity Maps free tier rate limiting
  - Mitigation: 15-minute cache, stale cache fallback
- DynLCA baseline data becomes outdated
  - Mitigation: versioned data, annual update process
- China regional grid data accuracy
  - Mitigation: clearly labeled as ESTIMATED, not MEASURED

## API Endpoints

- `GET /api/v1/carbon-intensity/current` — current signal with provenance
- `GET /api/v1/carbon-intensity/status` — provider chain status
- `GET /api/v1/carbon-intensity/history?start=&end=` — historical signals

## References

- Electricity Maps: https://www.electricitymaps.com/
  - Methodology: https://www.electricitymaps.com/data/methodology
  - API Docs: https://static.electricitymaps.com/api/docs/index.html
- WattTime: https://watttime.org/ (alternative provider, US/EU focus)
- DynLCA: https://github.com/guangcansu/dynlca (China grid data)
- CEPD: China Electricity Planning & Design Institute annual reports
