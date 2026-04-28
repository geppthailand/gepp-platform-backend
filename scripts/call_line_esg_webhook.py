#!/usr/bin/env python3
"""
GEPP ESG — LINE Webhook Simulator / Debugger

Usage:
    # Text message
    python scripts/call_line_esg_webhook.py -e local -m "ค่าไฟ 45000 บาท"

    # Image (local file)
    python scripts/call_line_esg_webhook.py -e local -i /path/to/invoice.jpg --org-id 35

    # Extract only, no DB save
    python scripts/call_line_esg_webhook.py -e local -i /path/to/img.jpg --org-id 35 --no-save

    # Run from YAML spec
    python scripts/call_line_esg_webhook.py run debugs/v3/backend/esg/webhook/runs/000001.yaml

    # Compare two run logs
    python scripts/call_line_esg_webhook.py compare 000001 000003
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

# ──────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────

PLATFORMS_ROOT = Path(__file__).resolve().parents[3]  # .../platforms
DEBUGS_DIR = PLATFORMS_ROOT / 'debugs' / 'v3' / 'backend' / 'esg' / 'webhook'
LOGS_DIR = DEBUGS_DIR / 'logs'
RUNS_DIR = DEBUGS_DIR / 'runs'

ENVS = {
    'local': {'url': 'http://localhost:9000', 'name': 'Local'},
    'dev':   {'url': 'https://api.geppdata.com/v1-dev', 'name': 'Development'},
    'prod':  {'url': 'https://api.geppdata.com/v1', 'name': 'Production'},
}

WEBHOOK_PATH = '/api/esg/line/webhook'
DEFAULT_USER_ID = 'U_simulator_debug_user'
DEFAULT_REPLY_TOKEN = '00000000000000000000000000000000'
DEFAULT_DESTINATION = 'U_simulator_destination'

# ──────────────────────────────────────────────────────
# ANSI helpers
# ──────────────────────────────────────────────────────

_C = {
    'g': '\033[92m', 'y': '\033[93m', 'r': '\033[91m', 'b': '\033[94m',
    'c': '\033[96m', 'gr': '\033[90m', 'B': '\033[1m', '0': '\033[0m',
}

def c(text, color):
    return f"{_C.get(color, '')}{text}{_C['0']}"

def pr(label, value, indent=6):
    print(f"{' '*indent}{c(label+':', 'gr')} {value}")

# ──────────────────────────────────────────────────────
# Run ID management
# ──────────────────────────────────────────────────────

def next_run_id() -> str:
    """Get next sequential run ID (000001, 000002, ...)."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted([d.name for d in LOGS_DIR.iterdir() if d.is_dir() and d.name.startswith('run_')])
    if existing:
        last_num = int(existing[-1].replace('run_', ''))
        return f"{last_num + 1:06d}"
    return '000001'


class RunLogger:
    """Logs each step of a webhook run to a sequential file."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.run_dir = LOGS_DIR / f'run_{run_id}'
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.seq = 0
        self.entries = []  # For summary

    def log(self, label: str, data):
        self.seq += 1
        fname = f"{self.seq:06d}_{label}.json"
        fpath = self.run_dir / fname
        content = data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False, default=str)
        fpath.write_text(content, encoding='utf-8')
        self.entries.append({'seq': self.seq, 'label': label, 'file': fname})

    def log_text(self, label: str, text: str):
        self.seq += 1
        fname = f"{self.seq:06d}_{label}.txt"
        fpath = self.run_dir / fname
        fpath.write_text(text, encoding='utf-8')
        self.entries.append({'seq': self.seq, 'label': label, 'file': fname})

    def save_summary(self, summary: dict):
        fpath = self.run_dir / 'summary.json'
        summary['run_id'] = self.run_id
        summary['files'] = self.entries
        summary['timestamp'] = datetime.now().isoformat()
        fpath.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding='utf-8')


# ──────────────────────────────────────────────────────
# Event builders
# ──────────────────────────────────────────────────────

def build_text_event(user_id, text, reply_token=DEFAULT_REPLY_TOKEN):
    return {
        'type': 'message', 'replyToken': reply_token,
        'source': {'type': 'user', 'userId': user_id},
        'timestamp': int(time.time() * 1000),
        'message': {'type': 'text', 'id': str(uuid.uuid4().int)[:18], 'text': text},
    }

def build_image_event(user_id, reply_token=DEFAULT_REPLY_TOKEN, msg_id=None):
    return {
        'type': 'message', 'replyToken': reply_token,
        'source': {'type': 'user', 'userId': user_id},
        'timestamp': int(time.time() * 1000),
        'message': {'type': 'image', 'id': msg_id or str(uuid.uuid4().int)[:18], 'contentProvider': {'type': 'line'}},
    }

def read_image(path_str: str):
    if path_str.startswith('http://') or path_str.startswith('https://'):
        resp = requests.get(path_str, timeout=30)
        resp.raise_for_status()
        return resp.content
    p = Path(path_str)
    if not p.exists():
        print(c(f'  ERROR: File not found: {path_str}', 'r'))
        sys.exit(1)
    return p.read_bytes()


# ──────────────────────────────────────────────────────
# Main send function
# ──────────────────────────────────────────────────────

def send_webhook(env, message=None, image_path=None, file_path=None,
                 user_id=DEFAULT_USER_ID, org_id=None, no_save=False,
                 dry_run=False, verbose=False, run_logger=None):

    env_config = ENVS.get(env)
    if not env_config:
        print(c(f'ERROR: Unknown env: {env}', 'r'))
        sys.exit(1)

    base_url = env_config['url']
    full_url = f"{base_url}{WEBHOOK_PATH}"
    run_id = run_logger.run_id if run_logger else '—'

    print()
    print(c('═' * 64, 'c'))
    print(c(f'  GEPP ESG — LINE Webhook Simulator   run_id={run_id}', 'B'))
    print(c(f'  {env_config["name"]}: {full_url}', 'c'))
    if no_save:
        print(c(f'  MODE: extract-only (no DB save)', 'y'))
    print(c('═' * 64, 'c'))
    print()

    # ── Build event ──
    events = []
    input_type = None

    if message:
        input_type = 'text'
        print(f"  {c('[1]','b')} TEXT: \"{message[:80]}\"")
        events.append(build_text_event(user_id, message))

    elif image_path:
        input_type = 'image'
        print(f"  {c('[1]','b')} IMAGE: {image_path[:80]}")
        raw = read_image(image_path)
        b64 = base64.b64encode(raw).decode('utf-8')
        print(f"      {c('Size:','gr')} {len(raw):,} bytes → {len(b64):,} base64 chars")
        evt = build_image_event(user_id)
        evt['_simulator'] = {'image_base64': b64, 'image_size': len(raw), 'source_path': str(image_path)}
        events.append(evt)

    elif file_path:
        input_type = 'file'
        p = Path(file_path)
        if not p.exists():
            print(c(f'ERROR: {file_path} not found', 'r')); sys.exit(1)
        print(f"  {c('[1]','b')} FILE: {p.name} ({p.stat().st_size:,} bytes)")
        events.append({
            'type': 'message', 'replyToken': DEFAULT_REPLY_TOKEN,
            'source': {'type': 'user', 'userId': user_id},
            'timestamp': int(time.time() * 1000),
            'message': {'type': 'file', 'id': str(uuid.uuid4().int)[:18], 'fileName': p.name, 'fileSize': p.stat().st_size},
        })
    else:
        print(c('ERROR: -m, -i, or -f required', 'r')); sys.exit(1)

    payload = {'destination': DEFAULT_DESTINATION, 'events': events}
    body_str = json.dumps(payload, ensure_ascii=False)

    headers = {
        'Content-Type': 'application/json',
        'x-line-signature': 'simulator-no-signature',
        'x-simulator': 'true',
        'x-simulator-user-id': user_id,
    }
    if org_id:
        headers['x-simulator-org-id'] = str(org_id)
    if no_save:
        headers['x-simulator-dry-run'] = 'true'

    pr('User', user_id)
    pr('Org', org_id or '(auto)')
    pr('Payload', f'{len(body_str):,} bytes')

    # Log request
    if run_logger:
        run_logger.log('request_meta', {
            'env': env, 'url': full_url, 'input_type': input_type,
            'user_id': user_id, 'org_id': org_id, 'no_save': no_save,
            'message': message, 'image_path': str(image_path) if image_path else None,
            'timestamp': datetime.now().isoformat(),
        })

    if dry_run:
        print(c('\n  DRY RUN — not sending\n', 'y'))
        return None

    # ── Send ──
    print(f"\n  {c('[2]','b')} Sending...")
    t0 = time.time()
    try:
        resp = requests.post(full_url, data=body_str, headers=headers, timeout=180)
    except requests.exceptions.ConnectionError:
        print(c(f'\n  CONNECTION ERROR: {full_url}', 'r'))
        print(c(f'  Is backend running? ./run_local.sh', 'y'))
        return None
    except requests.exceptions.Timeout:
        print(c('\n  TIMEOUT (>180s)', 'r'))
        return None

    elapsed = time.time() - t0
    print(f"      {c('Status:','gr')} {c(str(resp.status_code), 'g' if resp.status_code==200 else 'r')}  {c(f'{elapsed:.1f}s','gr')}")

    try:
        data = resp.json()
    except json.JSONDecodeError:
        print(c(f'  Non-JSON: {resp.text[:300]}', 'y'))
        return None

    if run_logger:
        run_logger.log('response_raw', data)

    # ── Parse & display results ──
    results = (data.get('data') or {}).get('results', [])
    if not results:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str)[:500])
        return data

    for i, r in enumerate(results):
        status = r.get('status', '?')
        sc = 'g' if status == 'success' else 'y' if status in ('skipped','needs_org') else 'r'

        print(f"\n  {c(f'══ Result: {status.upper()} ══', sc)}")
        if r.get('type'):     pr('Type', r['type'])
        if r.get('dry_run'):  pr('Mode', c('DRY-RUN (no DB save)', 'y'))
        if r.get('extraction_id'): pr('Extraction', r['extraction_id'])
        if r.get('entry_count'):   pr('Entries', r['entry_count'])
        if r.get('entry_id'):      pr('Entry ID', r['entry_id'])
        if r.get('reason'):        pr('Reason', r['reason'])
        if r.get('error'):         pr('Error', c(r['error'], 'r'))

        # ── Debug block ──
        debug = r.get('debug', {})
        if debug:
            if run_logger:
                run_logger.log('debug_full', debug)

            # Document info
            print(f"\n  {c('── Document ──', 'c')}")
            if debug.get('document_summary'):
                pr('Summary', debug['document_summary'])
            refs = debug.get('refs', {})
            for k, v in refs.items():
                if v: pr(k, v)
            if debug.get('llm_model'):
                pr('Model', debug['llm_model'])
            tok = debug.get('llm_tokens', {})
            if tok:
                pr('Tokens', f"in={tok.get('input_tokens','?')} out={tok.get('output_tokens','?')}")

            # Records
            records = debug.get('records', [])
            if records:
                print(f"\n  {c(f'── Records ({len(records)}) ──', 'c')}")
                for ri, rec in enumerate(records):
                    label = rec.get('record_label', '(unnamed)')
                    cat_name = rec.get('category_name', '?')
                    sub_name = rec.get('subcategory_name', '')
                    cat_id = rec.get('category_id', '?')
                    sub_id = rec.get('subcategory_id', '?')
                    print(f"\n    {c(f'[{ri+1}]','B')} {c(label,'g')}")
                    print(f"        Cat: {cat_name} ({cat_id}) → Sub: {sub_name} ({sub_id})")
                    for f in rec.get('fields', []):
                        dp = f.get('datapoint_name', '?')
                        dp_id = f.get('datapoint_id', '?')
                        val = f.get('value', '?')
                        unit = f.get('unit', '')
                        conf = f.get('confidence', '?')
                        tags = f.get('tags', [])
                        cc = 'g' if isinstance(conf,(int,float)) and conf>=0.8 else 'y' if isinstance(conf,(int,float)) and conf>=0.5 else 'r'
                        tstr = f" {c(str(tags),'gr')}" if tags else ''
                        print(f"        {c('•','b')} {dp} (dp={dp_id}): {c(str(val),'B')} {unit}  conf={c(str(conf),cc)}{tstr}")

            # Entries table
            entries = debug.get('entries', [])
            if entries:
                print(f"\n  {c(f'── Entries ({len(entries)}) ──', 'c')}")
                print(f"    {'#':>3} {'Category':<25} {'Value':>12} {'Unit':<8} {'tCO2e':>12} {'Scope':<9} {'Conf':>5}  Label")
                print(f"    {'─'*3} {'─'*25} {'─'*12} {'─'*8} {'─'*12} {'─'*9} {'─'*5}  {'─'*20}")
                for ei, e in enumerate(entries):
                    cat = (e.get('category') or '?')[:25]
                    val = e.get('value')
                    vs = f"{val:,.2f}" if isinstance(val,(int,float)) else str(val or '—')
                    unit = (e.get('unit') or '')[:8]
                    t2 = e.get('calculated_tco2e')
                    ts = f"{t2:,.6f}" if isinstance(t2,(int,float)) and t2 else '—'
                    scope = (e.get('scope_tag') or '—')[:9]
                    conf = e.get('confidence')
                    cs = f"{conf:.2f}" if isinstance(conf,(int,float)) else '—'
                    lb = (e.get('record_label') or '')[:20]
                    print(f"    {ei+1:>3} {cat:<25} {vs:>12} {unit:<8} {ts:>12} {scope:<9} {cs:>5}  {lb}")

                if run_logger:
                    run_logger.log('entries_extracted', entries)
        elif status == 'success' and not debug:
            print(c('\n  (No debug data — is x-simulator header reaching the backend?)', 'y'))

    # Save summary
    if run_logger:
        run_logger.save_summary({
            'env': env, 'input_type': input_type, 'status': results[0].get('status') if results else '?',
            'entry_count': results[0].get('entry_count', 0) if results else 0,
            'elapsed_s': round(elapsed, 2), 'no_save': no_save,
            'user_id': user_id, 'org_id': org_id,
            'message': message, 'image_path': str(image_path) if image_path else None,
        })
        print(f"\n  {c('Logs saved:', 'c')} {run_logger.run_dir}")

    print(f"\n{c('═' * 64, 'c')}\n")
    return data


# ──────────────────────────────────────────────────────
# Datapoint-level comparison
# ──────────────────────────────────────────────────────

def _match_entry(exp, actual_entries):
    """Find the best matching actual entry for an expected entry."""
    exp_cat = (exp.get('category') or '').lower().strip()
    exp_dp = (exp.get('datapoint_name') or '').lower().strip()
    exp_val = exp.get('value')
    exp_unit = (exp.get('unit') or '').lower().strip()

    best = None
    best_score = -1

    for ae in actual_entries:
        score = 0
        a_cat = (ae.get('category') or '').lower().strip()
        a_dp = (ae.get('datapoint_name') or ae.get('record_label') or '').lower().strip()
        a_val = ae.get('value')
        a_unit = (ae.get('unit') or '').lower().strip()

        # Category match (fuzzy contains)
        if exp_cat and a_cat and (exp_cat in a_cat or a_cat in exp_cat):
            score += 3
        elif exp_cat == a_cat:
            score += 3

        # Datapoint name match (fuzzy)
        if exp_dp and a_dp:
            if exp_dp == a_dp:
                score += 5
            elif exp_dp in a_dp or a_dp in exp_dp:
                score += 3

        # Unit match
        if exp_unit and a_unit and exp_unit == a_unit:
            score += 2

        # Value match
        if exp_val is not None and a_val is not None:
            try:
                if abs(float(exp_val) - float(a_val)) < 0.01:
                    score += 4
                elif abs(float(exp_val) - float(a_val)) / max(abs(float(exp_val)), 1) < 0.05:
                    score += 2  # within 5%
            except (ValueError, TypeError):
                pass

        if score > best_score:
            best_score = score
            best = ae

    return best, best_score


def _compare_expected(expected, actual_top, actual_entries):
    """Compare expected spec against actual extraction results."""
    results = {'all_pass': True, 'checks': [], 'entry_checks': []}

    # Top-level checks
    for key in ('status', 'entry_count'):
        if key in expected:
            act_val = actual_top.get(key)
            exp_val = expected[key]
            match = str(act_val) == str(exp_val)
            results['checks'].append({'field': key, 'expected': exp_val, 'actual': act_val, 'match': match})
            if not match:
                results['all_pass'] = False

    # Category presence check
    cats_present = expected.get('categories_present', [])
    if cats_present:
        actual_cats = set((e.get('category') or '').lower() for e in actual_entries)
        for exp_cat in cats_present:
            found = any(exp_cat.lower() in ac for ac in actual_cats)
            results['checks'].append({'field': f'category_present:{exp_cat}', 'expected': True, 'actual': found, 'match': found})
            if not found:
                results['all_pass'] = False

    # Refs check
    exp_refs = expected.get('refs', {})
    actual_debug = actual_top.get('debug', {})
    actual_refs = actual_debug.get('refs', {})
    for ref_key, ref_val in exp_refs.items():
        if ref_val is not None:  # null = skip check
            act = actual_refs.get(ref_key)
            match = str(act) == str(ref_val)
            results['checks'].append({'field': f'ref:{ref_key}', 'expected': ref_val, 'actual': act, 'match': match})
            if not match:
                results['all_pass'] = False

    # Entry-level datapoint checks
    exp_entries = expected.get('entries', [])
    for ei, exp_e in enumerate(exp_entries):
        matched_actual, score = _match_entry(exp_e, actual_entries)

        check = {
            'index': ei + 1,
            'expected_category': exp_e.get('category', '?'),
            'expected_datapoint': exp_e.get('datapoint_name', '?'),
            'expected_value': exp_e.get('value'),
            'expected_unit': exp_e.get('unit', ''),
            'match_score': score,
        }

        if matched_actual and score >= 5:
            check['actual_category'] = matched_actual.get('category', '')
            check['actual_datapoint'] = matched_actual.get('record_label', '') or matched_actual.get('datapoint_name', '')
            check['actual_value'] = matched_actual.get('value')
            check['actual_unit'] = matched_actual.get('unit', '')
            check['actual_tco2e'] = matched_actual.get('calculated_tco2e')
            check['actual_confidence'] = matched_actual.get('confidence')

            # Value match
            val_match = False
            try:
                if exp_e.get('value') is not None and matched_actual.get('value') is not None:
                    val_match = abs(float(exp_e['value']) - float(matched_actual['value'])) < 0.01
            except (ValueError, TypeError):
                pass
            check['value_match'] = val_match

            # Unit match
            eu = (exp_e.get('unit') or '').lower()
            au = (matched_actual.get('unit') or '').lower()
            check['unit_match'] = eu == au if eu else True

            check['pass'] = val_match and check['unit_match']
        else:
            check['actual_category'] = None
            check['actual_value'] = None
            check['pass'] = False

        if not check['pass']:
            results['all_pass'] = False
        results['entry_checks'].append(check)

    return results


def _print_comparison(comp):
    """Print comparison results to terminal."""
    print(f"\n  {c('── Expected vs Actual ──', 'y')}")

    # Top-level checks
    for chk in comp.get('checks', []):
        icon = c('✓','g') if chk['match'] else c('✗','r')
        print(f"    {icon} {chk['field']}: expected={chk['expected']}  actual={chk['actual']}")

    # Entry-level checks
    entry_checks = comp.get('entry_checks', [])
    if entry_checks:
        print(f"\n  {c('── Datapoint Comparison ──', 'y')}")
        print(f"    {'#':>3} {'Expected Datapoint':<30} {'Exp Value':>10} {'Act Value':>10} {'Unit':>6} {'tCO2e':>10} {'Conf':>5} {'Result'}")
        print(f"    {'─'*3} {'─'*30} {'─'*10} {'─'*10} {'─'*6} {'─'*10} {'─'*5} {'─'*6}")

        passed = 0
        failed = 0
        for ec in entry_checks:
            idx = ec['index']
            dp = (ec.get('expected_datapoint') or '?')[:30]
            ev = ec.get('expected_value')
            ev_s = f"{ev:,.2f}" if isinstance(ev,(int,float)) else str(ev or '?')
            av = ec.get('actual_value')
            av_s = f"{av:,.2f}" if isinstance(av,(int,float)) else str(av or '—')
            au = (ec.get('actual_unit') or '—')[:6]
            at = ec.get('actual_tco2e')
            at_s = f"{at:,.4f}" if isinstance(at,(int,float)) and at else '—'
            ac = ec.get('actual_confidence')
            ac_s = f"{ac:.2f}" if isinstance(ac,(int,float)) else '—'
            ok = ec.get('pass', False)
            icon = c('PASS','g') if ok else c('FAIL','r')
            if ok: passed += 1
            else: failed += 1
            print(f"    {idx:>3} {dp:<30} {ev_s:>10} {av_s:>10} {au:>6} {at_s:>10} {ac_s:>5} {icon}")

        print(f"\n    {c(f'Passed: {passed}','g')}  {c(f'Failed: {failed}','r' if failed else 'g')}  Total: {len(entry_checks)}")

    overall = comp.get('all_pass', False)
    icon = c('ALL PASSED ✓','g') if overall else c('SOME FAILED ✗','r')
    print(f"\n  {icon}")


# ──────────────────────────────────────────────────────
# YAML run spec
# ──────────────────────────────────────────────────────

def run_from_yaml(yaml_path: str):
    """Execute a run defined in a YAML spec file."""
    try:
        import yaml
    except ImportError:
        print(c('ERROR: pip install pyyaml', 'r'))
        sys.exit(1)

    p = Path(yaml_path)
    if not p.exists():
        print(c(f'ERROR: {yaml_path} not found', 'r'))
        sys.exit(1)

    spec = yaml.safe_load(p.read_text(encoding='utf-8'))
    run_id = next_run_id()
    logger = RunLogger(run_id)

    # Save the spec itself
    logger.log('run_spec', spec)

    print(c(f'\n  Running YAML spec: {p.name}  (run_id={run_id})', 'B'))

    steps = spec.get('steps', [])
    all_results = []

    for si, step in enumerate(steps):
        step_name = step.get('name', f'step_{si+1}')
        print(c(f'\n  ─── Step {si+1}: {step_name} ───', 'c'))

        result = send_webhook(
            env=step.get('env', spec.get('env', 'local')),
            message=step.get('message'),
            image_path=step.get('image'),
            file_path=step.get('file'),
            user_id=step.get('user_id', spec.get('user_id', DEFAULT_USER_ID)),
            org_id=step.get('org_id', spec.get('org_id')),
            no_save=step.get('no_save', spec.get('no_save', False)),
            run_logger=logger,
        )

        # Check expected output
        expected = step.get('expected', {})
        actual_results = (result or {}).get('data', {}).get('results', [{}])
        actual = actual_results[0] if actual_results else {}
        debug = actual.get('debug', {})
        actual_entries = debug.get('entries', [])

        if expected:
            comparison = _compare_expected(expected, actual, actual_entries)
            _print_comparison(comparison)
            all_results.append({'step': step_name, 'passed': comparison['all_pass'], 'detail': comparison})
            logger.log(f'step_{si+1}_comparison', comparison)
        else:
            all_results.append({'step': step_name, 'passed': None})

    # Summary
    print(c(f'\n  ══ Run Summary (run_id={run_id}) ══', 'B'))
    for sr in all_results:
        if sr['passed'] is None:
            print(f"    {c('○','gr')} {sr['step']} (no expected defined)")
        elif sr['passed']:
            print(f"    {c('✓','g')} {sr['step']} PASSED")
        else:
            print(f"    {c('✗','r')} {sr['step']} FAILED")

    logger.save_summary({'steps': all_results})
    print(f"\n  Logs: {logger.run_dir}")

    # Also save as a run YAML
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_yaml_path = RUNS_DIR / f'{run_id}.yaml'
    import shutil
    shutil.copy2(str(p), str(run_yaml_path))
    print(f"  Spec: {run_yaml_path}\n")


# ──────────────────────────────────────────────────────
# Compare runs
# ──────────────────────────────────────────────────────

def compare_runs(run_a: str, run_b: str):
    """Compare extraction results between two runs at datapoint level."""
    dir_a = LOGS_DIR / f'run_{run_a}'
    dir_b = LOGS_DIR / f'run_{run_b}'

    if not dir_a.exists():
        print(c(f'ERROR: run_{run_a} not found in {LOGS_DIR}', 'r')); sys.exit(1)
    if not dir_b.exists():
        print(c(f'ERROR: run_{run_b} not found in {LOGS_DIR}', 'r')); sys.exit(1)

    def load_entries(d):
        for f in sorted(d.glob('*entries_extracted*')):
            return json.loads(f.read_text(encoding='utf-8'))
        return []

    def load_debug(d):
        for f in sorted(d.glob('*debug_full*')):
            return json.loads(f.read_text(encoding='utf-8'))
        return {}

    def load_summary(d):
        f = d / 'summary.json'
        return json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}

    ea = load_entries(dir_a)
    eb = load_entries(dir_b)
    da = load_debug(dir_a)
    db_ = load_debug(dir_b)
    sa = load_summary(dir_a)
    sb = load_summary(dir_b)

    print(c(f'\n  ══ Compare: run_{run_a} vs run_{run_b} ══', 'B'))
    print(f"    A: {sa.get('timestamp','?')}  entries={len(ea)}  model={da.get('llm_model','?')}")
    print(f"    B: {sb.get('timestamp','?')}  entries={len(eb)}  model={db_.get('llm_model','?')}")

    if len(ea) != len(eb):
        print(c(f'    Entry count: {len(ea)} → {len(eb)} ({len(eb)-len(ea):+d})', 'y'))
    print()

    # Build lookup by (category, record_label, unit) — fuzzy-tolerant
    def entry_key(e):
        return (
            (e.get('category') or '').lower().strip(),
            (e.get('record_label') or e.get('datapoint_name') or '').lower().strip(),
            (e.get('unit') or '').lower().strip(),
        )

    map_a = {}
    for e in ea:
        k = entry_key(e)
        map_a[k] = e
    map_b = {}
    for e in eb:
        k = entry_key(e)
        map_b[k] = e

    all_keys = sorted(set(list(map_a.keys()) + list(map_b.keys())))

    # Header
    print(f"  {'Category':<22} {'Datapoint/Label':<20} {'Unit':<6} {'Val A':>10} {'Val B':>10} {'Diff':>8} {'tCO2e A':>9} {'tCO2e B':>9} {'St'}")
    print(f"  {'─'*22} {'─'*20} {'─'*6} {'─'*10} {'─'*10} {'─'*8} {'─'*9} {'─'*9} {'─'*4}")

    match_count = 0
    diff_count = 0
    only_a = 0
    only_b = 0

    for k in all_keys:
        a = map_a.get(k, {})
        b = map_b.get(k, {})
        cat = (k[0] or '?')[:22]
        lbl = (k[1] or '')[:20]
        unit = (k[2] or '')[:6]

        va = a.get('value')
        vb = b.get('value')
        va_s = f"{va:,.2f}" if isinstance(va,(int,float)) else '—'
        vb_s = f"{vb:,.2f}" if isinstance(vb,(int,float)) else '—'

        diff = ''
        if isinstance(va,(int,float)) and isinstance(vb,(int,float)):
            d = vb - va
            diff = f"{d:+,.2f}" if abs(d) > 0.001 else '='
        elif va is not None and vb is None:
            diff = '-DEL'
        elif va is None and vb is not None:
            diff = '+NEW'

        ta = a.get('calculated_tco2e')
        tb = b.get('calculated_tco2e')
        ta_s = f"{ta:,.4f}" if isinstance(ta,(int,float)) and ta else '—'
        tb_s = f"{tb:,.4f}" if isinstance(tb,(int,float)) and tb else '—'

        if not a:
            st = c('+B','b')
            only_b += 1
        elif not b:
            st = c('-A','r')
            only_a += 1
        elif va == vb:
            st = c('= ','g')
            match_count += 1
        else:
            st = c('~ ','y')
            diff_count += 1

        print(f"  {cat:<22} {lbl:<20} {unit:<6} {va_s:>10} {vb_s:>10} {diff:>8} {ta_s:>9} {tb_s:>9} {st}")

    print()
    print(f"  {c(f'Identical: {match_count}','g')}  {c(f'Changed: {diff_count}','y' if diff_count else 'g')}  {c(f'Only in A: {only_a}','r' if only_a else 'gr')}  {c(f'Only in B: {only_b}','b' if only_b else 'gr')}")
    print(f"  {c('Use this to tune LLM prompts — re-run after prompt changes and compare again.', 'gr')}")
    print()


# ──────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='GEPP ESG — LINE Webhook Simulator & Debugger',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  (default)  Send a single webhook call
  run        Execute a YAML run spec
  compare    Compare two run logs

Examples:
  python scripts/call_line_esg_webhook.py -e local -m "ค่าไฟ 45000 บาท"
  python scripts/call_line_esg_webhook.py -e local -i invoice.jpg --org-id 35 --no-save
  python scripts/call_line_esg_webhook.py run debugs/v3/backend/esg/webhook/runs/000001.yaml
  python scripts/call_line_esg_webhook.py compare 000001 000003
        """,
    )

    sub = parser.add_subparsers(dest='command')

    # ── run command ──
    run_p = sub.add_parser('run', help='Execute a YAML run spec')
    run_p.add_argument('yaml_file', help='Path to YAML run spec')

    # ── compare command ──
    cmp_p = sub.add_parser('compare', help='Compare two run logs')
    cmp_p.add_argument('run_a', help='Run ID A (e.g. 000001)')
    cmp_p.add_argument('run_b', help='Run ID B (e.g. 000003)')

    # ── default (send) args ──
    parser.add_argument('-e', '--env', choices=['local', 'dev', 'prod'], default='local',
                        help='Environment (default: local)')
    parser.add_argument('-m', '--message', type=str, help='Text message')
    parser.add_argument('-i', '--image', type=str, help='Image path or URL')
    parser.add_argument('-f', '--file', type=str, help='File path')
    parser.add_argument('--user-id', type=str, default=DEFAULT_USER_ID, help='LINE user ID')
    parser.add_argument('--org-id', type=int, default=None, help='Organization ID')
    parser.add_argument('--no-save', action='store_true', help='Extract only, no DB save')
    parser.add_argument('--dry-run', action='store_true', help='Show payload only')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.command == 'run':
        run_from_yaml(args.yaml_file)
        return

    if args.command == 'compare':
        compare_runs(args.run_a, args.run_b)
        return

    # Default: send single webhook
    inputs = sum([bool(args.message), bool(args.image), bool(args.file)])
    if inputs == 0:
        parser.error('Need -m, -i, or -f (or use "run" / "compare" subcommand)')
    if inputs > 1:
        parser.error('Only one of -m, -i, -f')

    if args.env == 'prod' and not args.dry_run:
        if input(c('\n  WARNING: PRODUCTION. Continue? (y/N): ', 'r')).lower() != 'y':
            return

    run_id = next_run_id()
    logger = RunLogger(run_id)

    send_webhook(
        env=args.env, message=args.message, image_path=args.image,
        file_path=args.file, user_id=args.user_id, org_id=args.org_id,
        no_save=args.no_save, dry_run=args.dry_run, verbose=args.verbose,
        run_logger=logger,
    )


if __name__ == '__main__':
    main()
