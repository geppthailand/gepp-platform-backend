"""
Export report-advice feedback as training / evaluation samples (B5).

One JSON object per line:
  label      {vote: like|dislike, comment}
  rule_id, section
  sample     the rule as it fired: definition (when / priority / text templates), the inputs it
             read with their values, condition_holds, priority, shown, rendered th/en text,
             rules_version and whether it still matches the current rules file
  context    organization, report / compare mode, period, filters, snapshot id
  metrics    every metric the engine computed for that report (comparable across samples)
  evaluated  every rule that matched in that report, its priority and whether it was shown

usage (reads DATABASE settings from .env.local by default):
  python scripts/export_advice_feedback.py out.jsonl [--org 31 --org 2783] [--rules-version v3-...] [--all]
  --all   include comment-only rows (no vote)
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--org', type=int, action='append')
    ap.add_argument('--rules-version')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--env', default='.env.local')
    a = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(a.env)
    from GEPPPlatform.libs.database import get_session
    from GEPPPlatform.services.cores.reports.advice_feedback_service import training_rows

    with get_session() as db:
        rows = training_rows(db, organization_ids=a.org, rules_version=a.rules_version, only_votes=not a.all)
    with open(a.out, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + '\n')
    likes = sum(1 for r in rows if r['label']['vote'] == 'like')
    print(f"{len(rows)} samples ({likes} like / {len(rows) - likes} other) -> {a.out}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
