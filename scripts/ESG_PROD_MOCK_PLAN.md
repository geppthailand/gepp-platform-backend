# GEPP-ESG — Prod Mock Data Plan

**Date:** 2026-08-19 · **Status:** Phase 0 done, Phase 1+ not started
**Target:** prod DB (migrations/.env) · demo org = new `GEPP ESG Demo`
**Decisions locked:** `focus_mode = full_esg` (+ backend pillar fix), new org, restore-all worktree

---

## 0. What the survey found

### 0.1 API wiring (root cause of "API ยิงไป dev")

| Base path | API Gateway | Lambda | DB |
|---|---|---|---|
| `https://api.geppdata.com/v1` | `giqr4vzwjh` | `PROD-GEPPPlatform` | prod |
| `https://api.geppdata.com/v1-dev` | `f4ap0okewj` | `DEV-GEPPPlatform` | dev |

`.env.production` had the prod line **commented out** and shipped `v1-dev`. Since `deploy:prod`
runs `vite build --mode production`, the single deployed frontend (S3 `prod-gepp-esg`,
CloudFront `E18T0U21YK570K`) was pointing at the dev backend.

**`/api` must not be in the base URL.** Callers append it themselves
(`authService.ts:38` → `${API_URL}/api/auth/login`; `BaseApiService` uses it as axios `baseURL`
and every call passes `/api/...`). So `https://api.geppdata.com/v1/api/` would produce
`/v1/api//api/auth/login`. Correct value is `https://api.geppdata.com/v1`.

`PROD-GEPPPlatform` code is current (LastModified 2026-08-19, newer than DEV) — all routes in
this repo are deployed on `v1`.

### 0.2 Prod DB state — reference data seeded, transactional data empty

| Layer | Table | Prod rows | Note |
|---|---|---|---|
| ref | `esg_data_category` | 41 | 9 E + 15 E-scope3 + 9 S + 8 G |
| ref | `esg_data_subcategory` | 60 | |
| ref | `esg_datapoint` | 456 | |
| ref | `esg_scope3_categories` | 15 | global, no `organization_id` |
| ref | `esg_condition_rules` | 15 | global |
| ref | `esg_macc_initiatives` | 15 | global templates (`organization_id` NULL, `is_template=t`) |
| ref | `esg_xbrl_tags` | 16 | global |
| ref | `esg_emission_factors` | 10 | TGO 2022 — **thin, see 3.2** |
| config | `esg_organization_settings` | 3 | orgs 35 / 2601 / 2602, all `scope3_only`, no base year, no target |
| config | `esg_organization_setup` | 2 | orgs 10 / 35 |
| **fact** | **`esg_records`** | **0** | the table everything aggregates from |
| fact | `esg_scope3_entries` | 0 | |
| fact | `esg_suppliers` / `_submissions` / `_chasers` / `_magic_links` | 0 | |
| fact | `esg_cbam_products` / `_reports` | 0 | |
| fact | `esg_user_materiality` / `esg_materiality_submissions` | 0 | |
| fact | `esg_xbrl_report_values` | 0 | |
| fact | `esg_documents` | 4 | |
| fact | `esg_organization_data_extraction` | 28 | all org 35 |

Dev DB is **identical** except `esg_materiality_submissions`=1, `esg_user_materiality`=1,
`esg_external_invitation_links`=11.

> **There is nothing to migrate dev → prod.** The task is a pure seed on prod, not a data move.
> This removes the whole class of ID-collision / FK-remap risk a dev→prod copy would carry.

### 0.3 Three gotchas that decide whether the dashboard renders

**(a) Scope 3 categories exist twice in the taxonomy.**

- as **subcategories 6–20** under category 3 `Carbon Emissions Scope 3` — these carry the 456 datapoints
- as **categories 27–41** with `is_scope3=true`, `scope3_category_id=1..15` — these carry **no** subcategories

`esg_dashboard_service._scope3_breakdown()` joins `EsgRecord.category_id = EsgDataCategory.id`
filtered on `is_scope3=true AND scope3_category_id IS NOT NULL`.

→ **A record only appears in the Scope 3 donut if `category_id ∈ 27..41`.** Records written
against `category_id=3` + `subcategory_id ∈ 6..20` aggregate to **zero**. The seed must use 27–41.

**(b) `esg_records.pillar` is `CHAR(1)`.** `esg_data_entry_service` copies it from
`esg_data_category.pillar`, i.e. `'E' | 'S' | 'G'`. But `esg_dashboard_service.get_summary()`
in the `full_esg` branch does:

```python
for scope_tag in ['Scope 1', 'Scope 2', 'Scope 3']:
    val = base.filter(EsgRecord.pillar == scope_tag)...
```

`CHAR(1)` can never equal `'Scope 1'` → **the entire `scope_breakdown` returns 0.0 in `full_esg`
mode.** This is a live bug, not a data problem. Fix is in scope (§4.1).

**(c) `focus_mode` is gated in two independent places.** Both must say `full_esg`:

- backend: `esg_organization_settings.focus_mode` (per org) — drives dashboard + extraction filtering
- frontend: `VITE_FOCUS_MODE` — **build-time**, drives `FocusGate` (Social/Governance routes) and
  which Scope 3 categories render. Default when unset is `scope3_only`.

### 0.4 Scope reality check — what mock data can and cannot fix

| Page | Data source | Seedable? |
|---|---|---|
| Dashboard | `liff/summary` + `liff/charts` + `liff/report` | ✅ `esg_records` |
| Data Warehouse | `data-warehouse/hierarchy`, `.../datapoint/{id}` | ✅ `esg_records` |
| History | `extractions` | ✅ `esg_organization_data_extraction` |
| Data Entry | `categories` / `subcategories` / `datapoints` / `data-entries` | ✅ already seeded refs |
| Ideas | `ideas` | ✅ derived from records |
| Report | `scope3-export` | ✅ `esg_records` |
| Supply Chain | `supply-chain/suppliers|chasers|scope3|submissions` | ✅ supplier tables |
| CBAM | `supply-chain/cbam` | ✅ `esg_cbam_products` |
| Settings | `org-setup`, `platform-bindings`, `invitations`, `line-members` | ✅ config tables |
| **Social** | **hardcoded array in `src/pages/Social/index.tsx`** | ❌ **frontend work** |
| **Governance** | **hardcoded array in `src/pages/Governance/index.tsx`** | ❌ **frontend work** |
| **Standards** | `GET /api/esg/standards/{key}` — **route does not exist in backend** | ❌ **backend work** |

Also dead: `constants/index.ts` declares `CONDITION_RULES`, `XBRL`, `DASHBOARD_CONFIG` and 10
`LIFF.*` smart-insight endpoints (`ALERTS`, `QUICK_WINS`, `MACC`, `SBTI_PATHWAY`, `CARBON_BUDGET`,
`SCOPE3_PARETO`, `SOURCE_FLOW`, `ENHANCED_SCOPE`, `RISK_OPPORTUNITY`, `OPPORTUNITIES`).
None exist in the backend **and none are called from any page** — unused constants, no action needed.

So "ครบถ้วนในทุกมิติ" splits into: seed (this plan), 2 static pages, 1 missing route. Called out in §4.

---

## Phase 0 — API switch ✅ DONE

`.env.production` now:

```
VITE_API_BASE_URL=https://api.geppdata.com/v1
VITE_FOCUS_MODE=full_esg
```

Verified: `yarn build:prod` succeeds; `dist/assets/index-*.js` contains
`https://api.geppdata.com/v1` (single match, no `v1-dev`) and `full_esg`.

**Not deployed.** `yarn deploy:prod` (S3 sync + CloudFront invalidation) is a separate, explicit call.

> ⚠️ Deploying Phase 0 alone flips the live app to a prod DB with **zero ESG records** — it will
> look emptier than today. Either deploy after Phase 3, or accept a temporary blank dashboard.

---

## Phase 1 — Tenant foundation

Creates the account you log in with. Smallest possible slice that is independently testable.

1. `organizations` — `GEPP ESG Demo`. Required non-defaulted NOT NULL: **`public_form_key`**.
2. `user_locations` — the login row:
   - `is_user=true`, `is_active=true`, `email`, `username`, `display_name`
   - `password` = **bcrypt** (`auth_handlers.hash_password`, `bcrypt.gensalt()`); login accepts
     `email` OR `username`, case-insensitive
   - `platform` = `GEPP_BUSINESS_WEB` (enum `platform_enum` has **no `ESG` value**; login does not
     filter on platform, so this is cosmetic — matches how orgs 35 users are stored)
   - `organization_role_id` — optional; `login()` only decorates the response with it
   - defaults cover `country_id=212`, `currency_id=12`
3. **No subscription needed.** The ESG frontend's `ProtectedRoute` checks `isAuthenticated` only;
   `AuthContextProvider` hardcodes `permissions: []`. `login()` tolerates no active subscription.
4. `esg_organization_settings` — `reporting_year=2026`, `methodology='ghg_protocol'`,
   `organizational_boundary`, **`base_year=2023`**, **`reduction_target_percent=30`**,
   **`reduction_target_year=2030`**, **`focus_mode='full_esg'`**,
   `enabled_scope3_categories='[1,...,15]'`.
   > Base year + target are what make the trajectory / SBTi / praise rules produce output at all.
5. `esg_organization_setup` — `industry_sector`, `employee_count=420`, `annual_revenue`,
   `revenue_currency='THB'`, `reporting_framework='gri'`, `fiscal_year_start=1`.

**Test gate:** `POST https://api.geppdata.com/v1/api/auth/login` returns a token; the web app
signs in and lands on an empty-but-not-erroring dashboard.

---

## Phase 2 — Company narrative (the numbers to hit)

Fix the story **before** writing rows, so every downstream table stays consistent.

Thai mid-size manufacturer, 420 employees, FY Jan–Dec. Base year **2023**, target **−30% by 2030**
(≈4.3%/yr → 1.5 °C-aligned, so the SBTi condition rule passes rather than warns).

| Year | Scope 1 | Scope 2 | Scope 3 | Total tCO₂e | YoY |
|---|---|---|---|---|---|
| 2023 (base) | 2,050 | 4,900 | 14,100 | 21,050 | — |
| 2024 | 1,960 | 4,560 | 13,600 | 20,120 | −4.4% |
| 2025 | 1,880 | 4,180 | 13,050 | 19,110 | −5.0% |
| 2026 (YTD Aug) | 1,180 | 2,530 | 8,240 | 11,950 | on track |

Why these shapes:
- **3 consecutive reduction years** → fires "Sustained Reducer" praise + 3-year trend lines.
- Scope 3 ≈ 68% of total → fires the *Supply Chain Engagement* rule (>70% threshold is close but
  not crossed; §5.1 of the research doc) while Scope 2 stays large enough to justify the renewable
  recommendation. Tune to taste — this is the one knob that changes which insights appear.
- Scope 2 falls fastest (−15% over 3y) → tells a credible "we bought RECs / rooftop solar" story.
- 2026 partial-year so "reporting deadline in N days" / data-gap rules have something to say.

Scope 3 mix (2025, tCO₂e) — deliberately Pareto-shaped so the treemap/waterfall look real:

| Cat | Name | tCO₂e | % |
|---|---|---|---|
| 1 | Purchased goods and services | 6,100 | 47% |
| 4 | Upstream transport & distribution | 1,850 | 14% |
| 5 | Waste generated in operations | 1,240 | 9.5% |
| 9 | Downstream transport & distribution | 1,090 | 8.4% |
| 3 | Fuel- and energy-related activities | 880 | 6.7% |
| 6 | Business travel | 620 | 4.8% |
| 7 | Employee commuting | 540 | 4.1% |
| 2 | Capital goods | 410 | 3.1% |
| 12 | End-of-life treatment | 180 | 1.4% |
| 11 | Use of sold products | 90 | 0.7% |
| 8, 10, 13, 14, 15 | (assessed, not material) | 50 | 0.4% |

All 15 present — the donut has no holes — but weighted so top-3 dominates.

---

## Phase 3 — `esg_records` (the core fact table) ⭐

Everything on the Dashboard, Data Warehouse, Report and Ideas pages reduces to this table.
Do this as **one script, three passes**, verifying totals after each.

**Row shape:**

| Column | Value |
|---|---|
| `organization_id` | demo org |
| `category_id` | **Scope 1 → 1, Scope 2 → 2, Scope 3 → 27..41** (see §0.3a) |
| `subcategory_id` | Scope 1/2 → 1..5; Scope 3 → NULL (cats 27–41 have no subcategories) |
| `scope3_category_id` | 1..15 for Scope 3, NULL otherwise — mirror of the category row |
| `pillar` | `'E'` / `'S'` / `'G'` — **CHAR(1)**, copied from `esg_data_category.pillar` |
| `record_label` | human string, NOT NULL — e.g. `ค่าไฟฟ้า ก.ค. 2569 — อาคาร A` |
| `entry_date` | spread across the month, not all on the 1st |
| `datapoints` | JSONB array, **canonical keys** (§3.1) |
| `kgco2e` | **kg, not tonnes** — dashboard divides by 1000 |
| `ghg_status` | `'calculated'` mostly; leave ~8% as missing-EF to make data-quality rules fire |
| `ghg_method` / `ghg_ef_value` / `ghg_ef_unit` / `ghg_source_name` / `ghg_source_url` | populate for calculated rows |
| `ghg_missing_fields` | `'[]'` NOT NULL |
| `status` | `'VERIFIED'` (~85%) / `'PENDING_VERIFY'` (~15%) — drives the KPI cards |
| `entry_source` | mix of `'line'`, `'manual'`, `'import'` |

**Pass A — Scope 1 & 2** (`category_id` 1, 2): 12 months × 4 years × ~4 sources ≈ 190 rows.
**Pass B — Scope 3** (`category_id` 27..41): monthly for cats 1/4/5/9, quarterly for 3/6/7/2,
annual for the long tail ≈ 320 rows.
**Pass C — S & G pillars** (`category_id` 9..26): annual disclosures ≈ 140 rows.

≈ **650 rows total.** Enough for smooth 36-point trend lines without making the Data Warehouse
tree unusable. Scale by changing the per-category cadence, not the year count.

> Pass C is worth doing **even though the Social/Governance pages are static** — it populates the
> Data Warehouse tree, `/completeness`, and the GRI export. Without it the E pillar sits at ~95%
> completeness and S/G at 0%, which looks broken in the hierarchy view.

### 3.1 `datapoints` JSONB contract

Post-migration-065 the keys are **canonical**, from
`GEPPPlatform/services/esg/datapoint_registry.py`:

- numeric: `distance_km`, `weight_kg`, `volume_litres`, `energy_kwh`, `nights`, `headcount`, `amount`
- categorical (closed vocabularies): `currency` (`THB`…), `transport_mode`
  (`taxi|car|motorbike|flight|train|bus|ship|truck|van|bicycle|walk|other`), `flight_class`,
  `fuel_type` (`diesel|petrol|lpg|cng|…`), `disposal_method`
  (`landfill|recycle|incinerate|compost|…`), `material_type`, `waste_type`, `refrigerant_type`, …
- the verbatim source string is preserved in a `raw_<canonical>` sibling

Use only vocabulary values from the registry — the extraction/normalisation path and the
data-warehouse datapoint drill-down both key off them.

### 3.2 Emission factors

Only 10 rows (TGO 2022), and none for Scope 3 cats 2/8/10/11/13/14/15. Two options:

- **(chosen)** write `kgco2e` directly on each record and set `ghg_ef_value` / `ghg_ef_unit` /
  `ghg_source_name` from the intended factor. The dashboard reads `kgco2e`; it never recomputes.
- extend `esg_emission_factors` to ~40 rows first. Cleaner, but it mutates a **global** reference
  table shared with orgs 35/2601/2602 — out of scope for a demo seed.

---

## Phase 4 — Known gaps that mock data cannot close

These are the "ทุกมิติ" items that need code, not rows. Sequence them **after** Phase 3 so the
core demo is testable first.

**4.1 `esg_dashboard_service` pillar bug (blocking for `full_esg`) — must ship**

`get_summary()`, `full_esg` branch: replace the `pillar == 'Scope 1'` filter with a scope derived
from `category_id` (1 → Scope 1, 2 → Scope 2, `is_scope3` or category 3 → Scope 3). Also return
`scope3_breakdown` in `full_esg` mode instead of `[]`, so the 15-category donut survives the
switch. Then `bash update_function.sh PROD GEPPPlatform "--profile gepp"`.

**4.2 Social / Governance pages** — hardcoded `features` arrays. To make them real, add
`GET /api/esg/social` + `/api/esg/governance` reading Pass-C records, or (cheaper) keep them
static and drop them from the "all dimensions" claim.

**4.3 `GET /api/esg/standards/{key}`** — called from `src/pages/Standards/index.tsx:50`, absent
from the backend → 404 → empty state. `esg_xbrl_tags` (16 rows) and `esg_condition_rules`
(15 rows) are already seeded and unused; a thin handler over them would light this page up.

---

## Phase 5 — Supply chain, CBAM, LIFF, documents

Only after Phase 3 is verified green.

1. **`esg_suppliers`** ~24 rows: tier 1/2/3, `data_collection_level`, `annual_spend` (THB),
   `primary_scope3_category` weighted to cat 1, `data_quality_score` 0.4–0.95, mixed `status`.
2. **`esg_supplier_submissions`** ~40: `submission_status` spread over
   pending/submitted/verified, `data_tier`, `raw_data` JSONB, a few `anomaly_flags` so the
   anomaly-detection panel is non-empty.
3. **`esg_supplier_chasers`** ~15 + **`esg_supplier_magic_links`** 3 (one unexpired, for
   `/supplier/:token`).
4. **`esg_scope3_entries`** ~120: one per (category, year, method) with
   `calculation_method` spanning spend-based / activity-based / supplier-specific and
   `data_quality_indicator` varied — this is what makes the Scope 3 method-mix chart interesting.
   Link `record_id` / `supplier_id` where sensible.
5. **`esg_cbam_products`** 4–6 CN codes (steel/aluminium) + **`esg_cbam_reports`** 2 quarters.
6. **`esg_documents`** ~30 + **`esg_organization_data_extraction`** ~40 for the History page.
   `file_url` / `file_key` must be S3 keys the presign endpoint can sign, or the row renders but
   the download 404s. Prefer re-pointing at existing prod objects over inventing keys.
7. **LIFF**: `esg_users` (3–4 `platform='line'` rows bound to the demo org),
   `esg_external_platform_binding`, `esg_external_invitation_links`,
   `esg_line_messages`, `esg_user_materiality` + `esg_materiality_submissions` (completed, so
   the materiality wizard shows results rather than restarting).
   Some `esg_records` should carry `line_user_id` — but note `_base_query` treats a user **with**
   a LINE binding as user-scoped. Keep the desktop login **without** a LINE binding so it gets the
   org-wide aggregate.
8. **`esg_xbrl_report_values`** ~16, one per existing tag, once 4.3 lands.

---

## Idempotency, safety, rollback

Follow the existing house pattern (`scripts/seed_gri306_mock.sql`, `seed_rewards_mock_v3.sql`):

- one registry table `esg_mock_seed_ids (organization_id, entity, entity_id)`; every insert
  records its id
- script **deletes its own prior rows children-first** before re-inserting → safe to re-run
- paired `scripts/unseed_esg_mock.sql` (cf. `unseed_rewards_mock_v3.sql`) for a clean removal
- `\set target_org` + `\set ON_ERROR_STOP on`, wrapped in a single `BEGIN; … COMMIT;`
- **customer-ready**: no `TEST`/`MOCK` strings in any user-visible field
- Thai + English on every label (`record_label`, `supplier_name`, `product_name_th`) — the app is
  bilingual and a Thai-only demo breaks the EN view

**Prod-safety rules for this work:**
- every write scoped to the new demo org; never touch orgs 35 / 2601 / 2602
- do not mutate the global reference tables (`esg_data_category`, `esg_datapoint`,
  `esg_scope3_categories`, `esg_condition_rules`, `esg_xbrl_tags`, `esg_emission_factors`)
- run against dev DB (`migrations/.env.development`) first — schemas are identical, so a dev
  dry-run catches every constraint violation at zero prod risk
- `pg_dump` the demo org's tables before each re-run once the data is non-trivial

---

## Verification checklist (per phase)

```
Phase 1  login 200 on /v1/api/auth/login; app reaches /dashboard
Phase 3  summary.total_tco2e ≈ 19,110 for 2025
         summary.scope_breakdown has 3 non-zero rows      ← proves 4.1 shipped
         summary.scope3_breakdown has 15 rows, none null  ← proves category_id 27..41
         charts monthly trend has 12 points per year
         /data-warehouse tree expands E, S and G
         /completeness > 90% for E
Phase 5  /supply-chain lists 24 suppliers, anomaly panel non-empty
         /cbam lists products, quarterly report exports
         /supplier/<token> resolves
         /report exports a Thai PDF (THSarabunNew font)
Both themes (light + dark) and both languages (th + en) on every page.
```

---

## Open items for you

1. **Demo credentials** — email/username + password for the login row (Phase 1). Needed before
   any SQL is written.
2. **Org identity** — legal-ish name, industry sector, revenue figure. Affects intensity metrics
   (tCO₂e/revenue) shown on the dashboard.
3. **Deploy timing for Phase 0** — deploy the API switch now (dashboard temporarily empty) or hold
   until Phase 3 lands? Recommend holding.
4. **Scope of §4.2** — build real Social/Governance endpoints, or accept them as static showcase
   pages for this demo?
