#!/usr/bin/env python3
"""
Debug Audit Analysis Script
วิเคราะห์ผลการ audit จาก ai_audit_note ใน database

Usage:
    python debug_audit_analysis.py --household-id <household_id>
    python debug_audit_analysis.py --transaction-id <transaction_id>
    python debug_audit_analysis.py --list-opaque
    python debug_audit_analysis.py --list-wrong-prediction
"""

import argparse
import json
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in environment")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

MATERIAL_ID_TO_NAME = {
    94: "general (ขยะทั่วไป)",
    77: "organic (ขยะอินทรีย์)",
    298: "recyclable (ขยะรีไซเคิล)",
    113: "hazardous (ขยะอันตราย)",
    0: "unknown/error"
}


def print_separator():
    print("=" * 80)


def print_json(data, indent=2):
    print(json.dumps(data, indent=indent, ensure_ascii=False))


def analyze_transaction(session, transaction_id):
    """วิเคราะห์ transaction เดียว"""
    print_separator()
    print(f"📋 Transaction ID: {transaction_id}")
    print_separator()

    query = text("""
        SELECT
            t.id,
            t.ext_id_1,
            t.ext_id_2,
            t.ai_audit_status,
            t.ai_audit_note
        FROM transactions t
        WHERE t.id = :transaction_id
          AND t.deleted_date IS NULL
    """)

    result = session.execute(query, {"transaction_id": transaction_id}).fetchone()

    if not result:
        print(f"❌ Transaction {transaction_id} not found")
        return

    txn_id, ext_id_1, ext_id_2, status, audit_note = result

    print(f"📍 Location: ext_id_1={ext_id_1}, household_id={ext_id_2}")
    print(f"✅ Status: {status}")
    print()

    if not audit_note:
        print("⚠️  No audit_note found")
        return

    audit_data = audit_note if isinstance(audit_note, dict) else json.loads(audit_note)

    # Step 1: Coverage check
    print("🔍 STEP 1: Coverage Check")
    print_separator()
    step1 = audit_data.get("step_1", {})
    print(f"  Status: {step1.get('status')}")
    print(f"  Required: {step1.get('required')}")
    print(f"  Present: {step1.get('present')}")
    print(f"  Missing: {step1.get('missing')}")
    print()

    # Step 2: Material audit
    print("🔍 STEP 2: Material Audit")
    print_separator()
    step2 = audit_data.get("step_2", {})

    for material_key, material_data in step2.items():
        print(f"\n📦 Material: {material_key}")
        print("-" * 60)

        claimed_type_id = material_data.get("ct", 0)
        audit_status = material_data.get("as", "r")
        confidence = material_data.get("cs", 0)

        print(f"  Claimed Type: {MATERIAL_ID_TO_NAME.get(claimed_type_id, claimed_type_id)}")
        print(f"  Audit Status: {audit_status} (a=approve, r=reject, p=pending)")
        print(f"  Confidence: {confidence}")

        # Debug info
        debug = material_data.get("_debug", {})
        if debug:
            print("\n  🐛 DEBUG INFO:")
            print(f"    Visibility Status: {debug.get('visibility_status')}")
            print(f"    Visibility Reason: {debug.get('visibility_reason')}")

            if debug.get("visibility_raw"):
                print(f"    Visibility Raw Response: {debug.get('visibility_raw')[:200]}...")

            if not debug.get("step2_skipped"):
                classify_parsed = debug.get("classify_parsed", {})
                print(f"\n    Classification:")
                print(f"      Main Content: {classify_parsed.get('main_content')}")
                print(f"      Contamination: {classify_parsed.get('contamination_pct')}%")
                print(f"      Contamination Items: {classify_parsed.get('contamination_items')}")
                print(f"      Hazardous Detected: {classify_parsed.get('haz_detected')}")

                if debug.get("classify_raw"):
                    print(f"    Classify Raw Response: {debug.get('classify_raw')[:200]}...")

                decision = debug.get("decision", {})
                if decision:
                    print(f"\n    Decision:")
                    print(f"      Code: {decision.get('code')}")
                    print(f"      Status: {decision.get('status')}")
                    print(f"      Detected Type: {MATERIAL_ID_TO_NAME.get(int(decision.get('dt', 0)), decision.get('dt'))}")
                    print(f"      Warning Items: {decision.get('wi')}")

        print()


def list_opaque_predictions(session, limit=20):
    """แสดงรายการภาพที่ถูก predict เป็น opaque"""
    print_separator()
    print(f"🔍 Transactions with OPAQUE visibility (last {limit})")
    print_separator()

    query = text("""
        SELECT
            t.id as transaction_id,
            t.ext_id_2 as household_id,
            material_key,
            material_data->'_debug'->>'visibility_status' as visibility_status,
            material_data->'_debug'->>'visibility_reason' as reason,
            material_data->'_debug'->>'claimed_type' as claimed_type
        FROM transactions t,
        LATERAL jsonb_each(t.ai_audit_note::jsonb->'step_2') AS mat(material_key, material_data)
        WHERE t.organization_id = 8
          AND t.deleted_date IS NULL
          AND t.ai_audit_note IS NOT NULL
          AND material_data->'_debug'->>'visibility_status' = 'opaque'
        ORDER BY t.created_date DESC
        LIMIT :limit
    """)

    results = session.execute(query, {"limit": limit}).fetchall()

    if not results:
        print("✅ No opaque predictions found!")
        return

    for row in results:
        txn_id, household_id, material_key, vis_status, reason, claimed_type = row
        print(f"\n📋 Transaction ID: {txn_id}")
        print(f"   Household ID: {household_id}")
        print(f"   Material: {material_key} ({claimed_type})")
        print(f"   Visibility: {vis_status}")
        print(f"   Reason: {reason}")
        print("-" * 60)


def list_wrong_predictions(session, limit=20):
    """แสดงรายการภาพที่ predict ผิดประเภท"""
    print_separator()
    print(f"🔍 Transactions with WRONG TYPE prediction (last {limit})")
    print_separator()

    query = text("""
        SELECT
            t.id as transaction_id,
            t.ext_id_2 as household_id,
            material_key,
            (material_data->>'ct')::int as claimed_type_id,
            (material_data->'_debug'->'decision'->>'dt')::text as detected_type,
            material_data->'_debug'->'decision'->>'code' as decision_code,
            material_data->'_debug'->>'visibility_status' as visibility,
            material_data->'_debug'->'classify_parsed'->>'main_content' as ai_main_content
        FROM transactions t,
        LATERAL jsonb_each(t.ai_audit_note::jsonb->'step_2') AS mat(material_key, material_data)
        WHERE t.organization_id = 8
          AND t.deleted_date IS NULL
          AND t.ai_audit_note IS NOT NULL
          AND material_data->'_debug'->'decision' IS NOT NULL
          AND (material_data->>'ct')::text != (material_data->'_debug'->'decision'->>'dt')::text
          AND (material_data->'_debug'->'decision'->>'dt') != '0'
        ORDER BY t.created_date DESC
        LIMIT :limit
    """)

    results = session.execute(query, {"limit": limit}).fetchall()

    if not results:
        print("✅ No wrong predictions found!")
        return

    for row in results:
        txn_id, household_id, material_key, claimed_id, detected_type, code, vis, main_content = row
        claimed_name = MATERIAL_ID_TO_NAME.get(claimed_id, claimed_id)
        try:
            detected_name = MATERIAL_ID_TO_NAME.get(int(detected_type), detected_type)
        except:
            detected_name = detected_type

        print(f"\n📋 Transaction ID: {txn_id}")
        print(f"   Household ID: {household_id}")
        print(f"   Material: {material_key}")
        print(f"   ❌ MISMATCH:")
        print(f"      Claimed: {claimed_name}")
        print(f"      Detected: {detected_name}")
        print(f"   Decision Code: {code}")
        print(f"   Visibility: {vis}")
        print(f"   AI Main Content: {main_content}")
        print("-" * 60)


def find_by_household(session, household_id):
    """ค้นหา transaction จาก household_id"""
    print_separator()
    print(f"🔍 Searching for household_id: {household_id}")
    print_separator()

    query = text("""
        SELECT
            t.id,
            t.ext_id_1,
            t.ext_id_2,
            t.ai_audit_status,
            t.created_date
        FROM transactions t
        WHERE t.organization_id = 8
          AND t.deleted_date IS NULL
          AND t.ext_id_2 = :household_id
        ORDER BY t.created_date DESC
    """)

    results = session.execute(query, {"household_id": household_id}).fetchall()

    if not results:
        print(f"❌ No transactions found for household_id: {household_id}")
        return

    print(f"Found {len(results)} transaction(s):\n")
    for row in results:
        txn_id, ext_id_1, ext_id_2, status, created = row
        print(f"  Transaction ID: {txn_id}")
        print(f"  Status: {status}")
        print(f"  Created: {created}")
        print(f"  ext_id_1: {ext_id_1}")
        print("-" * 60)

    if results:
        print(f"\nℹ️  To see details, run:")
        print(f"    python {sys.argv[0]} --transaction-id {results[0][0]}")


def main():
    parser = argparse.ArgumentParser(description="Debug AI Audit Analysis")
    parser.add_argument("--transaction-id", type=int, help="Analyze specific transaction ID")
    parser.add_argument("--household-id", type=str, help="Find transactions by household ID")
    parser.add_argument("--list-opaque", action="store_true", help="List transactions with opaque visibility")
    parser.add_argument("--list-wrong-prediction", action="store_true", help="List transactions with wrong type prediction")
    parser.add_argument("--limit", type=int, default=20, help="Limit number of results (default: 20)")

    args = parser.parse_args()

    session = Session()

    try:
        if args.transaction_id:
            analyze_transaction(session, args.transaction_id)
        elif args.household_id:
            find_by_household(session, args.household_id)
        elif args.list_opaque:
            list_opaque_predictions(session, args.limit)
        elif args.list_wrong_prediction:
            list_wrong_predictions(session, args.limit)
        else:
            parser.print_help()
    finally:
        session.close()


if __name__ == "__main__":
    main()
