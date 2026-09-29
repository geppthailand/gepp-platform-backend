# Report recommendation rules

`report_rules.json` drives the **Risks / Opportunities / Quick wins** cards on the web Compare tab and on the PDF advice page. `GEPPPlatform/services/cores/reports/report_insights.py` evaluates it over the report scope's **own data**: the selected range compared with the same range a year earlier (`compare_mode = yearly`) or a month earlier (`monthly`). Both ranges are clamped to today, so they always cover the same days.

The rules file is generated. Edit the rule definitions in the builder script, regenerate the JSON, then run `pytest tests/test_report_insights.py`. The tests render every rule in every mode, so a typo fails CI instead of silently hiding a rule.

## Report modes

The report mode (per-user preference `report_preferences.mode`) decides whose point of view the advice takes:

| Mode | Reader | Tone | Id prefix |
|---|---|---|---|
| `location` | Building owner / facility team | Operate bins, contracts and signage for the whole site | `L-` |
| `tenant` | A tenant's own staff | Things the tenant can do at its desks and pantry; for bins and collection, "ask building management to…" | `T-` |
| `tag` | Event / activity organiser | Situation-level advice for the event (stations, volunteers, vendors, next event) | `E-` |

A rule lists the modes it applies to in `modes`. Some neutral rules are shared (for example `L-Q07` e-waste applies to all three modes).

## How a rule is picked

1. Only rules whose `modes` include the report mode are considered.
2. `when` is evaluated. Only rules whose condition is true are candidates. Unmatched rules are never shown.
3. `priority` (an expression) ranks the candidates within their section.
4. Only the highest-priority rule per `group` survives, so two signage tips never appear together.
5. Each section shows up to `max_items_per_section` (2).
6. If nothing matched, the section shows `fallback.<mode>.<section>`. If the scope has no data, every section shows `fallback.no_data`.

## Rule fields

| Field | Meaning |
|---|---|
| `id` | Stable id: prefix by mode, then R = risk, O = opportunity, Q = quick win. |
| `section` | `risk`, `opportunity` or `quickwin`. |
| `modes` | Subset of `location`, `tenant`, `tag`. |
| `group` | Mutual-exclusion key within a section. |
| `title` / `bullets` / `reason` | `{th, en}` text. `reason` appears under the card ("ทำไมถึงแนะนำ"). It explains the logic with the scope's own numbers and does not quote the threshold figures. |
| `when` | Condition, e.g. `has_prev and prev_kg >= 5 and change_pct >= 15`. |
| `priority` | Number or expression, e.g. `60 + min(change_pct, 100) * 0.3`. |

Expressions allow `and or not`, comparisons, `+ - * /`, and `min max abs round`. An unknown metric name raises an error.

Templates use `{metric}` or `{metric:fmt}`, where `fmt` is:

- `kg`: 1,234.56 กก.
- `pct`: 18.0%; a non-zero share below 0.05% renders as `<0.1%`.
- `pct_signed`: +18.0%
- `pts`: +5.2 จุด
- `int` or `num`

## Metrics

| Metric | Meaning |
|---|---|
| `total_kg`, `record_count`, `tx_count`, `has_data`, `active_days` | Current-period totals. |
| `{general,recyclable,organic,hazardous,bio_hazardous,electronic,construction,wte,rubber,other}_kg` / `_pct` | Per material category (share of `total_kg`). |
| `diversion_kg`, `diversion_pct` | Recyclable + organic. |
| `{paper,plastic,contaminated_plastic,glass,metal,unspecified,unspecified_recyclable,mixed_paper,cardboard}_kg` / `_pct` | Per material stream. |
| `glass_metal_kg/_pct`, `unspecified_recyclable_share`, `contaminated_plastic_share`, `mixed_paper_share` | Derived shares. |
| `{general,organic,paper,plastic,glass,metal,hazardous,electronic,construction,wte}_rank` | Stream rank by kg (1 = largest, 99 = absent). |
| `prev_kg`, `has_prev`, `change_kg`, `change_pct`, `change_pct_abs` | Current vs previous period (same days, one year or one month earlier). |
| `{general,recyclable,organic,hazardous}_{cur_kg,prev_kg,has_prev,change_pct}` | The same comparison per category. |
| `diversion_pct_prev`, `diversion_change_pts` | Sorted share in the previous period, and its change in percentage points. |
| `months_with_data`, `consecutive_increase_months`, `gap_months` | Monthly shape of the current period (kg/day, streak step +5%). |
| `days_since_last_record` | Days between the last record and min(today, period end). |
| `group_count`, `top_group_kg`, `top_group_share`, `unassigned_kg`, `unassigned_share` | Tag / tenant groups in the current period. Records whose tag id isn't a real tag count as unassigned. |

Text placeholders (localised): `cur_label`, `prev_label`, `compare_word`, `gap_month_labels`, `last_record_date`, `trend_note`, `top_stream_label`, `top3_labels`, `top_group_label`.

## Rules at a glance

| Id | Modes | Title (en) | Fires when |
|---|---|---|---|
| L-R01 | location | Waste is up on {compare_word} | `has_prev and prev_kg >= 5 and change_pct >= 15` |
| T-R01 | tenant | Your waste is up on {compare_word} | `has_prev and prev_kg >= 5 and change_pct >= 15` |
| E-R01 | tag | Waste from these events/areas is up on {compare_word} | `has_prev and prev_kg >= 5 and change_pct >= 15` |
| L-R02 | location | Waste has risen several months in a row | `consecutive_increase_months >= 3` |
| T-R02 | tenant | Your waste has risen several months in a row | `consecutive_increase_months >= 3` |
| L-R03 | location | General (landfill) waste is rising | `general_has_prev and general_prev_kg >= 3 and general_change_pct >= 20` |
| T-R03 | tenant | Your general waste is rising | `general_has_prev and general_prev_kg >= 3 and general_change_pct >= 20` |
| L-R04 | location | The building's sorting is slipping | `has_prev and prev_kg >= 5 and total_kg >= 5 and diversion_change_pts <= -10` |
| T-R04 | tenant | Your sorting is slipping | `has_prev and prev_kg >= 5 and total_kg >= 5 and diversion_change_pts <= -10` |
| E-R04 | tag | Sorting at these events/areas is slipping | `has_prev and prev_kg >= 5 and total_kg >= 5 and diversion_change_pts <= -10` |
| L-R05 | location | General waste is over half of the building's total | `total_kg >= 10 and general_pct >= 50` |
| T-R05 | tenant | General waste is over half of your total | `total_kg >= 10 and general_pct >= 50` |
| E-R05 | tag | Most event waste is general waste | `total_kg >= 10 and general_pct >= 50` |
| L-R07 | location | Hazardous waste needs special handling | `hazardous_kg > 0` |
| T-R07 | tenant | Hazardous waste must be kept separate | `hazardous_kg > 0` |
| E-R07 | tag | Hazardous waste at these events/areas | `hazardous_kg > 0` |
| L-R08 | location, tenant | Hazardous waste is rising | `hazardous_has_prev and hazardous_prev_kg > 0 and hazardous_change_pct >= 20` |
| L-R09 | location, tenant, tag | Infectious waste found | `bio_hazardous_kg > 0` |
| L-R10 | location, tenant, tag | Contaminated plastic can't be recycled | `contaminated_plastic_kg >= 1 and contaminated_plastic_share >= 10` |
| L-R11 | location | Waste data has stopped coming in | `has_data and days_since_last_record >= 14` |
| T-R11 | tenant | Your waste data has stopped coming in | `has_data and days_since_last_record >= 14` |
| L-R12 | location, tenant | Some months have no data | `gap_months >= 1` |
| L-R13 | location, tenant | Unusually sharp drop in waste | `has_prev and prev_kg >= 10 and change_pct <= -60` |
| E-R14 | tag | Waste is concentrated at {top_group_label} | `group_count >= 2 and top_group_share >= 60` |
| L-O01 | location | Set up organic-waste handling for the building | `organic_rank <= 3 and organic_pct >= 5` |
| T-O02 | tenant | Separate food waste in the pantry | `organic_rank <= 3 and organic_pct >= 5` |
| E-O01 | tag | Handle food waste from events | `organic_rank <= 3 and organic_pct >= 5` |
| L-O03 | location | Run a building-wide paper collection | `paper_rank <= 3 and paper_pct >= 5` |
| T-O01 | tenant | Cut paper use in the office | `paper_rank <= 3 and paper_pct >= 5` |
| E-O03 | tag | Cut printed material at events | `paper_rank <= 3 and paper_pct >= 5` |
| L-O04 | location | Cut single-use plastic in the building | `plastic_rank <= 3 and plastic_pct >= 5` |
| T-O03 | tenant | Cut single-use plastic in the office | `plastic_rank <= 3 and plastic_pct >= 5` |
| E-O02 | tag | Cut single-use plastic at events | `plastic_rank <= 3 and plastic_pct >= 5` |
| L-O05 | location | Separate bottles and cans from food outlets | `(glass_rank <= 3 or metal_rank <= 3) and glass_metal_pct >= 5` |
| T-O04 | tenant | Separate bottles and cans in the pantry | `(glass_rank <= 3 or metal_rank <= 3) and glass_metal_pct >= 5` |
| E-O04 | tag | Separate bottles and cans at drink points | `(glass_rank <= 3 or metal_rank <= 3) and glass_metal_pct >= 5` |
| L-O06 | location | Handle construction and renovation waste separately | `construction_kg >= 50 and construction_pct >= 5` |
| L-O07 | location | Send combustible general waste to RDF | `total_kg >= 50 and general_pct >= 40 and wte_kg == 0` |
| L-O08 | location | Sell recyclables sorted by type | `recyclable_kg >= 20 and recyclable_pct >= 15` |
| T-O10 | tenant | Feed recyclables into the building's programme | `recyclable_kg >= 20 and recyclable_pct >= 15` |
| E-O05 | tag | Collect recyclables after events | `recyclable_kg >= 20 and recyclable_pct >= 15` |
| T-O05 | tenant | Sort waste at the desk | `general_rank == 1 and general_pct >= 40 and total_kg >= 10` |
| L-O11 | location | Run a sorting campaign with occupants | `total_kg >= 50 and general_pct >= 40` |
| T-O08 | tenant | Cut waste at office procurement | `total_kg >= 50 and general_pct >= 40` |
| E-O06 | tag | Start with {top_group_label} | `group_count >= 2 and top_group_share >= 40` |
| L-O09 | location | Build on the drop in waste | `has_prev and prev_kg >= 5 and change_pct <= -10 and change_pct > -60` |
| T-O06 | tenant | Build on the drop in waste | `has_prev and prev_kg >= 5 and change_pct <= -10 and change_pct > -60` |
| E-O07 | tag | Build on the drop in waste | `has_prev and prev_kg >= 5 and change_pct <= -10 and change_pct > -60` |
| L-O10 | location, tenant | Sorting is improving | `has_prev and prev_kg >= 5 and total_kg >= 5 and diversion_change_pts >= 5` |
| L-O12 | location, tenant, tag | Move toward Zero Waste | `total_kg >= 10 and diversion_pct >= 60` |
| L-Q01 | location | Simple signage fix | `total_kg >= 5 and general_pct >= 50` |
| T-Q01 | tenant | Put sorting signs on office bins | `total_kg >= 5 and general_pct >= 50` |
| E-Q01 | tag | Picture signs at every bin station | `total_kg >= 5 and general_pct >= 50` |
| L-Q02 | location, tenant, tag | Simple signage fix | `total_kg >= 5 and unspecified_pct >= 15` |
| L-Q03 | location | Bin placement optimisation | `total_kg >= 5 and general_pct >= 40 and general_kg > diversion_kg` |
| T-Q03 | tenant | Pair recycling and general bins in the office | `total_kg >= 5 and general_pct >= 40 and general_kg > diversion_kg` |
| E-Q02 | tag | Staff the bin stations at peak times | `total_kg >= 5 and general_pct >= 40 and general_kg > diversion_kg` |
| L-Q04 | location, tenant, tag | Record recyclables by type | `unspecified_recyclable_kg >= 1 and unspecified_recyclable_share >= 10` |
| L-Q05 | location | Set up a cardboard flattening point | `cardboard_kg >= 3` |
| L-Q06 | location, tenant | Pull white paper out of mixed paper | `mixed_paper_kg >= 2 and mixed_paper_share >= 30` |
| T-Q02 | tenant | Make double-sided printing the default | `paper_pct >= 10 and paper_kg >= 3` |
| T-Q04 | tenant | Replace personal desk bins | `total_kg >= 20 and general_pct >= 55` |
| T-Q05 | tenant | Empty and rinse packaging before binning | `organic_kg >= 5 and plastic_kg >= 2` |
| E-Q05 | tag | An emptying point before the recycling bins | `organic_kg >= 5 and plastic_kg >= 2` |
| E-Q04 | tag | Brief vendors and organisers in advance | `organic_pct >= 5 or plastic_pct >= 5` |
| L-Q07 | location, tenant, tag | Set up an e-waste drop point | `electronic_kg > 0` |
| L-Q08 | location, tenant | Set up a battery and lamp collection point | `hazardous_kg > 0` |
| L-Q09 | location | Refresh housekeeping on sorting | `has_prev and prev_kg >= 5 and diversion_change_pts <= -5` |
| T-Q07 | tenant | Refresh sorting know-how with staff | `has_prev and prev_kg >= 5 and diversion_change_pts <= -5` |
| L-Q10 | location | Weigh and record on a fixed schedule | `has_data and days_since_last_record >= 7 and days_since_last_record < 14` |
| T-Q09 | tenant | Check with the building that your waste is weighed | `has_data and days_since_last_record >= 7 and days_since_last_record < 14` |
| T-Q10 | tenant | Tag the tenant on every weighing | `unassigned_share >= 20 and group_count >= 1` |
| E-Q07 | tag | Tag every record | `unassigned_share >= 20 and group_count >= 1` |
| E-Q06 | tag | A hazardous-waste container at events | `hazardous_kg > 0` |
