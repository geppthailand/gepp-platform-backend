"""
Investigate Total Waste diff for org old=459 / new=141, year 2024.
Old: 271,699.79  New: 271,714.79  Diff: +15.00
"""

import pymysql
import psycopg2
import psycopg2.extras
from collections import defaultdict

MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "Gepp_new",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

REMOTE_PG_CONFIG = {
    "host": "13.215.109.125",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": "6N0i8SKEVfd19B3",
}

OLD_ORG = 459
NEW_ORG = 141
DATE_FROM = "2024-01-01"
DATE_TO = "2024-12-31 23:59:59"


def main():
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    pg_conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.DictCursor)
    pg_cur = pg_conn.cursor()

    # OLD records
    mysql_cur.execute("""
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status AS rec_status,
               tr.material, tr.`journey_id`,
               m.unit_weight, m.calc_ghg, m.name_en AS mat_name, m.material_category_id,
               t.status AS tx_status, t.`business-unit` AS biz_unit, t.transaction_date
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s
          AND t.transaction_type = 1
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND t.transaction_date >= %s AND t.transaction_date <= %s
    """, (OLD_ORG, DATE_FROM, DATE_TO))
    old_all = mysql_cur.fetchall()

    last_hops = {}
    for r in old_all:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        last_hops[key] = r
    old_records = {r["rec_id"]: r for r in last_hops.values() if r["rec_status"] != "rejected"}

    old_weights = {}
    old_total = 0.0
    by_bu = defaultdict(lambda: {"count": 0, "weight": 0.0})
    for rec_id, r in old_records.items():
        qty = abs(float(r["quantity"] or 0))
        uw = float(r["unit_weight"] or 0)
        w = qty * uw
        old_weights[rec_id] = {"qty": qty, "uw": uw, "weight": w, "mat_name": r["mat_name"],
                               "biz_unit": r["biz_unit"], "tx_date": str(r["transaction_date"])}
        old_total += w
        by_bu[r["biz_unit"]]["count"] += 1
        by_bu[r["biz_unit"]]["weight"] += w

    print(f"OLD: {len(old_all)} raw -> {len(last_hops)} dedup -> {len(old_records)} non-rejected")
    print(f"Old total: {old_total:.2f} kg")
    print(f"\nBiz-unit breakdown:")
    for bu in sorted(by_bu, key=lambda b: -by_bu[b]["weight"]):
        print(f"  {bu}: {by_bu[bu]['count']} recs, {by_bu[bu]['weight']:.2f} kg")

    # NEW records
    pg_cur.execute("""
        SELECT tr.id AS rec_id, tr.migration_id, tr.origin_quantity,
               tr.material_id, tr.status AS rec_status, tr.transaction_date AS rec_tx_date,
               m.unit_weight, m.name_en AS mat_name
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= %s AND tr.transaction_date <= %s
    """, (NEW_ORG, DATE_FROM, DATE_TO))
    new_all = pg_cur.fetchall()

    new_weights = {}
    new_by_mig = {}
    new_no_mig = []
    new_total = 0.0
    for r in new_all:
        qty = float(r["origin_quantity"] or 0)
        uw = float(r["unit_weight"] or 0)
        w = qty * uw
        rid = r["rec_id"]
        mid = r["migration_id"]
        new_weights[rid] = {"qty": qty, "uw": uw, "weight": w, "migration_id": mid,
                            "mat_name": r["mat_name"], "tx_date": str(r["rec_tx_date"])}
        new_total += w
        if mid:
            new_by_mig[mid] = rid
        else:
            new_no_mig.append(rid)

    print(f"\nNEW: {len(new_all)} records, {len(new_no_mig)} without migration_id")
    print(f"New total: {new_total:.2f} kg")
    print(f"\nDIFF: {new_total - old_total:+.2f} kg")

    # COMPARE
    # A. Extra in new
    extra = []
    extra_w = 0.0
    for nid in new_no_mig:
        nw = new_weights[nid]
        extra.append({"new_id": nid, **nw})
        extra_w += nw["weight"]
    for mid, nid in new_by_mig.items():
        if mid not in old_weights:
            nw = new_weights[nid]
            extra.append({"new_id": nid, "old_id": mid, **nw})
            extra_w += nw["weight"]

    # B. Missing in new
    missing = []
    missing_w = 0.0
    for oid, ow in old_weights.items():
        if oid not in new_by_mig:
            missing.append({"old_id": oid, **ow})
            missing_w += ow["weight"]

    # C. Weight diffs
    diffs = []
    diff_w = 0.0
    for oid, ow in old_weights.items():
        if oid in new_by_mig:
            nid = new_by_mig[oid]
            nw = new_weights[nid]
            d = nw["weight"] - ow["weight"]
            if abs(d) > 0.01:
                diffs.append({"old_id": oid, "new_id": nid, "old_w": ow["weight"],
                              "new_w": nw["weight"], "diff": d, "mat": ow["mat_name"],
                              "old_qty": ow["qty"], "new_qty": nw["qty"],
                              "old_uw": ow["uw"], "new_uw": nw["uw"]})
                diff_w += d

    print(f"\n{'='*70}")
    print(f"A. EXTRA IN NEW: {len(extra)} records, {extra_w:.2f} kg")
    for r in sorted(extra, key=lambda x: -x["weight"])[:20]:
        oid = r.get("old_id", "N/A")
        reason = ""
        if oid != "N/A":
            mysql_cur.execute("""
                SELECT t.`business-unit`, t.transaction_date, tr.status, t.transaction_type
                FROM transaction_records tr JOIN transactions t ON tr.transaction_id = t.id
                WHERE tr.id = %s
            """, (oid,))
            c = mysql_cur.fetchone()
            if c:
                reason = f"biz={c['business-unit']}, type={c['transaction_type']}, date={c['transaction_date']}, status={c['status']}"
            else:
                reason = "NOT IN OLD DB"
        print(f"  new={r['new_id']}, old={oid}, w={r['weight']:.2f}, mat={r.get('mat_name','?')}, "
              f"date={r.get('tx_date','?')} | {reason}")

    print(f"\nB. MISSING IN NEW: {len(missing)} records, {missing_w:.2f} kg")
    for r in sorted(missing, key=lambda x: -x["weight"])[:20]:
        print(f"  old={r['old_id']}, w={r['weight']:.2f}, mat={r.get('mat_name','?')}, "
              f"biz={r.get('biz_unit','?')}, date={r.get('tx_date','?')}")

    print(f"\nC. WEIGHT DIFFS: {len(diffs)} records, {diff_w:.2f} kg")
    for d in sorted(diffs, key=lambda x: -abs(x["diff"]))[:20]:
        reasons = []
        if abs(d["old_qty"] - d["new_qty"]) > 0.001:
            reasons.append(f"qty:{d['old_qty']:.4f}->{d['new_qty']:.4f}")
        if abs(d["old_uw"] - d["new_uw"]) > 0.001:
            reasons.append(f"uw:{d['old_uw']:.3f}->{d['new_uw']:.3f}")
        print(f"  old={d['old_id']}, new={d['new_id']}, old_w={d['old_w']:.2f}, new_w={d['new_w']:.2f}, "
              f"diff={d['diff']:+.2f}, {', '.join(reasons) or 'rounding?'}, mat={d['mat']}")

    print(f"\n{'='*70}")
    print(f"SUMMARY:")
    print(f"  Extra:   +{extra_w:.2f} ({len(extra)} recs)")
    print(f"  Missing: -{missing_w:.2f} ({len(missing)} recs)")
    print(f"  Diffs:   {diff_w:+.2f} ({len(diffs)} recs)")
    print(f"  Net:     {extra_w - missing_w + diff_w:+.2f}")
    print(f"  Actual:  {new_total - old_total:+.2f}")

    mysql_cur.close(); mysql_conn.close()
    pg_cur.close(); pg_conn.close()


if __name__ == "__main__":
    main()
