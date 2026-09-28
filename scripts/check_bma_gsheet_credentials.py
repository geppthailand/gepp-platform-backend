#!/usr/bin/env python3
"""Check a Google service-account key can actually write the BMA sheet.

Runs the five things that can independently be wrong, in the order they fail,
and says which one it is:

    1. the key file parses and has the fields we need
    2. the RSA key loads and signs           (our stdlib signer)
    3. Google accepts the assertion          -> access token
    4. the spreadsheet and the tab are readable
    5. the tab is writable

The last two are where people trip, for two unrelated reasons that both surface
as HTTP 403:

  * the Sheets API is not enabled on the key's project — nothing to do with
    permissions, and the fix is a console URL that Google puts in the response;
  * the sheet was never shared with the key's `client_email` — a service account
    can see nothing until it is invited like any other user.

Both are told apart here from Google's own `error.details[].reason`, not guessed
from the status code.

Usage:
    python3 check_bma_gsheet_credentials.py --key /path/to/key.json
    python3 check_bma_gsheet_credentials.py --key key.json --sheet-id <id> --tab 'All data-GEPP'

Writes nothing: the write test appends a value to a scratch cell far outside the
data area and clears it again.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from GEPPPlatform.libs.google_sa_auth import (  # noqa: E402
    GoogleApiError, SheetsClient, column_letter, get_access_token,
    parse_rsa_private_key, rsa_sign_sha256,
)
from GEPPPlatform.services.integrations.bma.bma_gsheet_service import (  # noqa: E402
    DEFAULT_SHEET_ID, DEFAULT_TAB,
)

OK, BAD = '  OK  ', ' FAIL '


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--key', help='service-account JSON (or set BMA_GSHEET_SA_FILE)')
    ap.add_argument('--sheet-id', default=None)
    ap.add_argument('--tab', default=DEFAULT_TAB)
    ap.add_argument('--skip-write', action='store_true',
                    help='check read access only')
    args = ap.parse_args()

    key_path = args.key or os.environ.get('BMA_GSHEET_SA_FILE')
    sheet_id = args.sheet_id or os.environ.get('BMA_GSHEET_ID') or DEFAULT_SHEET_ID

    # ── 1. the file ──────────────────────────────────────────────────────
    if key_path:
        try:
            with open(key_path, encoding='utf-8') as fh:
                sa = json.load(fh)
        except Exception as e:
            print(f'[{BAD}] 1. read key file: {e}')
            return 1
    elif os.environ.get('BMA_GSHEET_SA_JSON'):
        sa = json.loads(os.environ['BMA_GSHEET_SA_JSON'])
        key_path = '$BMA_GSHEET_SA_JSON'
    else:
        print(f'[{BAD}] 1. no key given — pass --key or set BMA_GSHEET_SA_FILE '
              'or BMA_GSHEET_SA_JSON')
        return 1

    if sa.get('type') != 'service_account':
        print(f'[{BAD}] 1. `type` is {sa.get("type")!r}, expected '
              '"service_account". An OAuth *client* JSON ("installed"/"web") '
              'will not work here — download a service-account key instead.')
        return 1
    missing = [f for f in ('client_email', 'private_key', 'project_id')
               if not sa.get(f)]
    if missing:
        print(f'[{BAD}] 1. key file is missing: {", ".join(missing)}')
        return 1
    print(f'[{OK}] 1. key file      {key_path}')
    print(f'          project      {sa["project_id"]}')
    print(f'          client_email {sa["client_email"]}')

    # ── 2. the RSA key ───────────────────────────────────────────────────
    try:
        n, e, d = parse_rsa_private_key(sa['private_key'])
        rsa_sign_sha256(b'probe', n, d)
    except Exception as ex:
        print(f'[{BAD}] 2. private_key did not load/sign: {ex}')
        return 1
    print(f'[{OK}] 2. RSA key       {n.bit_length()}-bit, signs cleanly')

    # ── 3. the token exchange ────────────────────────────────────────────
    try:
        get_access_token(sa)
    except GoogleApiError as ex:
        print(f'[{BAD}] 3. token exchange rejected: {ex.message}')
        if ex.reason == 'invalid_grant':
            print('          -> the key is not valid for this account. It was '
                  'probably deleted/rotated in the console; download a fresh one.')
        elif ex.reason == 'invalid_scope':
            print(f'          -> enable the Google Sheets API on project '
                  f'{sa["project_id"]}.')
        return 1
    except Exception as ex:
        print(f'[{BAD}] 3. token exchange failed: {ex}')
        return 1
    print(f'[{OK}] 3. token         Google accepted the assertion')

    # ── 4. sheet access ──────────────────────────────────────────────────
    # Two very different failures both come back as 403 here — the API being
    # off, and the file not being shared — so branch on Google's own `reason`
    # rather than on the status code.
    def explain(ex):
        if isinstance(ex, GoogleApiError) and ex.service_disabled:
            url = ex.activation_url or (
                'https://console.developers.google.com/apis/api/'
                f'sheets.googleapis.com/overview?project={sa["project_id"]}')
            print('          -> GOOGLE SHEETS API IS NOT ENABLED on project '
                  f'{sa["project_id"]}.\n'
                  '             This is NOT a sharing problem. Enable it here:\n'
                  f'               {url}\n'
                  '             Then wait ~1 minute and run this again.')
            return
        if isinstance(ex, GoogleApiError) and ex.status_code == 404:
            print(f'          -> no sheet with id {sheet_id}, or no tab named '
                  f'{args.tab!r}. Check both.')
            return
        if isinstance(ex, GoogleApiError) and ex.status_code in (401, 403):
            print('          -> the sheet is probably not shared with this '
                  'service account.\n'
                  '             Open the sheet -> Share -> add\n'
                  f'               {sa["client_email"]}\n'
                  '             as Editor (Viewer is not enough), then rerun.')
            return
        print('          -> unexpected; the full response is above.')

    client = SheetsClient(sa)

    # 4a. read the workbook's structure. This is the read-permission test and it
    #     also gives the grid size — needed because a Sheets grid is finite, so
    #     a "safely far away" scratch cell has to be chosen inside it.
    try:
        grid = client.tab_grid(sheet_id)
    except Exception as ex:
        print(f'[{BAD}] 4. cannot read the spreadsheet:\n'
              f'          {getattr(ex, "message", str(ex))}')
        explain(ex)
        return 1

    if args.tab not in grid:
        print(f'[{BAD}] 4. no tab named {args.tab!r}. Tabs found:')
        for title, (r, c) in grid.items():
            print(f'             {title!r}  ({r} rows x {c} cols)')
        return 1

    rows, cols = grid[args.tab]
    print(f'[{OK}] 4. read access   {args.tab!r} is {rows} rows x {cols} cols')

    if args.skip_write:
        print(f'[{OK}] 5. write        skipped (--skip-write)')
    else:
        # Bottom-right corner of the grid: inside the sheet, but past both the
        # 20 data columns and every plausible data row, so a failed clear cannot
        # damage the report.
        probe = f'{column_letter(cols)}{rows}'
        probe_range = f"'{args.tab}'!{probe}"
        try:
            client.update(sheet_id, probe_range, [['gepp-credential-probe']])
            client.clear(sheet_id, probe_range)
        except Exception as ex:
            print(f'[{BAD}] 5. readable but NOT writable:\n'
                  f'          {getattr(ex, "message", str(ex))}')
            explain(ex)
            return 1
        print(f'[{OK}] 5. write access  confirmed (probed {probe}, then cleared)')

    print(f'\nAll good. Point the cron at this key:\n'
          f'  export BMA_GSHEET_SA_FILE={key_path}\n'
          f'  export BMA_GSHEET_ID={sheet_id}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
