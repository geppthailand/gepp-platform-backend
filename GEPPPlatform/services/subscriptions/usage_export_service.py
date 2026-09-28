"""XLSX export for one subscription period: quota set vs quota used.

The deliverable is an invoice worksheet, so the numbers must be checkable by the
person holding it. Every total is a real Excel FORMULA over the month rows rather
than a value computed here — change a month and the totals move, which is what
anyone auditing a bill expects, and it also means the sheet cannot silently
disagree with its own detail.

Same numbers as the detail modal: both read `SubscriptionUsageService`, so there
is one definition of "used".

Two different overage questions get answered separately, because they can
disagree and the difference is money:

  * per-month overage — a month above its own allowance;
  * period overage — total above (allowance x months elapsed).

A period can be within total allowance while a single month was over (5 used
against 2/month over 3 months = 5 of 6 total, but January was 3 over). Reporting
only one of those would understate or overstate the bill depending on which.
"""

import base64
import io
from datetime import date, datetime
from typing import Any, Dict, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .usage_service import SubscriptionUsageService

# House style. Arial throughout — the repo's other export uses it and these two
# land in the same inbox.
FONT = 'Arial'
_HDR_FILL = PatternFill('solid', fgColor='1F4E79')
_HDR_FONT = Font(name=FONT, bold=True, color='FFFFFF')
_LABEL_FONT = Font(name=FONT, bold=True)
_BODY_FONT = Font(name=FONT)
_OVER_FILL = PatternFill('solid', fgColor='FFC7CE')     # month above allowance
_OK_FILL = PatternFill('solid', fgColor='C6EFCE')
_MUTED_FILL = PatternFill('solid', fgColor='F2F2F2')    # month not yet started
_THIN = Side(style='thin', color='D9D9D9')
_BOX = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_INT = '#,##0'
_PCT = '0.0%'
_MB = '#,##0.00'


class SubscriptionUsageExportService:
    """Reads only."""

    def __init__(self, db):
        self.db = db

    def export(self, subscription_id: int,
               query_params: Optional[dict] = None) -> Dict[str, Any]:
        as_of = _parse_as_of((query_params or {}).get('asOf'))
        usage = SubscriptionUsageService(self.db).period_usage(
            subscription_id, as_of=as_of)
        if not usage.get('success'):
            raise ValueError(usage.get('message', 'Subscription not found'))

        wb = Workbook()
        self._summary_sheet(wb.active, usage)
        self._monthly_sheet(wb.create_sheet('Monthly detail'), usage)
        self._location_sheet(wb.create_sheet('By location'), usage)

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        label = (usage.get('period_label') or
                 f"{usage.get('period_start') or 'start'}_{usage.get('period_end') or 'open'}")
        safe = ''.join(c if (c.isalnum() or c in ' -_') else '_' for c in str(label))[:60]
        ts = datetime.now().strftime('%Y-%m-%d %H_%M_%S')

        return {
            'filename': f'Subscription_Usage_{usage["organization_id"]}_{safe}_{ts}.xlsx',
            'contentType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'base64': base64.b64encode(buf.read()).decode('utf-8'),
            'rowCount': len(usage.get('months') or []),
        }

    # ── sheet 1: what was agreed, what it came to ─────────────────────

    def _summary_sheet(self, ws, u: Dict[str, Any]) -> None:
        ws.title = 'Summary'
        n_months = len(u['months'])
        # Monthly detail rows start at 2 (row 1 is its header).
        first, last = 2, 1 + max(n_months, 1)
        used_range = f"'Monthly detail'!D{first}:D{last}"
        over_range = f"'Monthly detail'!E{first}:E{last}"
        past_flag = f"'Monthly detail'!F{first}:F{last}"

        rows = [
            ('SUBSCRIPTION PERIOD USAGE', None, None),
            (None, None, None),
            ('Organization ID', u['organization_id'], None),
            ('Subscription (period) ID', u['subscription_id'], None),
            ('Plan', u.get('plan_name') or u.get('plan_id'), None),
            ('Period label', u.get('period_label') or '—', None),
            ('Status', u.get('status'), None),
            ('Period start', u.get('period_start') or '—', None),
            ('Period end',
             u.get('period_end') or 'open-ended',
             'An open-ended period is reported up to the "as of" date.'),
            ('Reported as of', u['as_of'], None),
            (None, None, None),
            ('AGREED', None, None),
            ('Transactions allowed per month', u['transactions_per_month'],
             'ADVISORY — creation is never blocked. Recorded for billing.'),
            ('Max file size (MB)', u['max_file_size_mb'],
             'ENFORCED — an upload above this is refused.'),
            ('Transactions limit source', u['limit_sources']['transactions'],
             'period = from this row · organization = org default · system = built-in'),
            ('File size limit source', u['limit_sources']['file_size'], None),
            (None, None, None),
            ('ALLOWANCE', None, None),
            ('Months in period', u['months_in_period'],
             'Calendar months touched, both ends inclusive.'),
            ('Months elapsed', u['months_elapsed'],
             'Months that have begun as of the report date.'),
            ('Total allowance (whole period)', '=B19*B13',
             'Months in period x allowance per month.'),
            ('Allowance to date', '=B20*B13',
             'Months elapsed x allowance per month — the fair mid-contract comparison.'),
            (None, None, None),
            ('USED', None, None),
            ('Transactions used', f'=SUM({used_range})',
             'Counted from transactions by transaction_date, not by created_date.'),
            ('Over allowance to date', '=MAX(0,B25-B22)',
             'Period-level overage: used minus allowance to date.'),
            ('Utilisation of allowance to date', '=IF(B22=0,"",B25/B22)', None),
            ('Months that went over', f'=SUMPRODUCT(({over_range}>0)*({past_flag}="Yes"))',
             'A period can be within total allowance while one month was over.'),
            ('Sum of per-month overage', f'=SUMPRODUCT({over_range}*({past_flag}="Yes"))',
             'Bill on this if the contract is month-by-month rather than pooled.'),
        ]

        for label, value, note in rows:
            ws.append([label, value, note])

        ws['A1'].font = Font(name=FONT, bold=True, size=14)
        for row in ws.iter_rows(min_row=2):
            label_cell, value_cell, note_cell = row[0], row[1], row[2]
            is_section = (label_cell.value in
                          ('AGREED', 'ALLOWANCE', 'USED'))
            label_cell.font = _LABEL_FONT if is_section else _BODY_FONT
            if is_section:
                label_cell.fill = _MUTED_FILL
                value_cell.fill = _MUTED_FILL
                note_cell.fill = _MUTED_FILL
            value_cell.font = _BODY_FONT
            note_cell.font = Font(name=FONT, size=9, italic=True, color='808080')
            note_cell.alignment = Alignment(wrap_text=True, vertical='top')

        for addr in ('B13', 'B19', 'B20', 'B21', 'B22', 'B25', 'B26', 'B28', 'B29'):
            ws[addr].number_format = _INT
        ws['B14'].number_format = _MB
        ws['B27'].number_format = _PCT
        ws['B26'].fill = _OVER_FILL if (u['over_allowance'] or 0) > 0 else _OK_FILL

        ws.column_dimensions['A'].width = 34
        ws.column_dimensions['B'].width = 20
        ws.column_dimensions['C'].width = 62

    # ── sheet 2: the month rows every total points at ─────────────────

    def _monthly_sheet(self, ws, u: Dict[str, Any]) -> None:
        ws.append(['Month', 'Allowance', 'Used (formula)', 'Used', 'Over', 'Month started?'])
        for c in ws[1]:
            c.font, c.fill = _HDR_FONT, _HDR_FILL
            c.alignment = Alignment(horizontal='center')

        for i, m in enumerate(u['months'], start=2):
            ws.append([
                m['month'],
                m['allowance'],
                # Column C exists so the sheet shows the subtraction being made;
                # D is the raw count the formulas aggregate.
                f'=D{i}',
                m['used'],
                f'=MAX(0,D{i}-B{i})',
                'Yes' if m['in_past'] else 'No',
            ])

        for i, m in enumerate(u['months'], start=2):
            for cell in ws[i]:
                cell.font = _BODY_FONT
                cell.border = _BOX
            for col in ('B', 'C', 'D', 'E'):
                ws[f'{col}{i}'].number_format = _INT
            if not m['in_past']:
                # A month that has not started is not an underspend — grey it so
                # nobody reads the 0 as a shortfall.
                for cell in ws[i]:
                    cell.fill = _MUTED_FILL
            elif m['over'] > 0:
                ws[f'E{i}'].fill = _OVER_FILL

        total_row = len(u['months']) + 2
        ws.append(['TOTAL',
                   f'=SUM(B2:B{total_row - 1})',
                   f'=SUM(C2:C{total_row - 1})',
                   f'=SUM(D2:D{total_row - 1})',
                   f'=SUM(E2:E{total_row - 1})',
                   ''])
        for cell in ws[total_row]:
            cell.font = _LABEL_FONT
            cell.fill = _MUTED_FILL
            cell.border = _BOX
        for col in ('B', 'C', 'D', 'E'):
            ws[f'{col}{total_row}'].number_format = _INT

        ws.freeze_panes = 'A2'
        for col, width in zip('ABCDEF', (12, 12, 16, 12, 12, 16)):
            ws.column_dimensions[col].width = width

    # ── sheet 3: which site drove the volume ──────────────────────────

    def _location_sheet(self, ws, u: Dict[str, Any]) -> None:
        ws.append(['Location ID', 'Location', 'Transactions', '% of period'])
        for c in ws[1]:
            c.font, c.fill = _HDR_FONT, _HDR_FILL

        locations = u.get('locations') or []
        last = len(locations) + 1
        for i, loc in enumerate(locations, start=2):
            ws.append([
                loc['location_id'],
                loc['location_name'] or '(unassigned)',
                loc['used'],
                # Guarded: an empty period would divide by zero.
                f'=IF($C${last + 1}=0,"",C{i}/$C${last + 1})',
            ])

        for i in range(2, last + 1):
            for cell in ws[i]:
                cell.font = _BODY_FONT
                cell.border = _BOX
            ws[f'C{i}'].number_format = _INT
            ws[f'D{i}'].number_format = _PCT

        total_row = last + 1
        ws.append(['', 'TOTAL', f'=SUM(C2:C{last})' if locations else 0, ''])
        for cell in ws[total_row]:
            cell.font = _LABEL_FONT
            cell.fill = _MUTED_FILL
        ws[f'C{total_row}'].number_format = _INT

        ws.append([])
        ws.append(['', 'The contractual limit is org-wide — this sheet is only '
                       'to show which site the volume came from.'])
        ws[f'B{total_row + 2}'].font = Font(name=FONT, size=9, italic=True, color='808080')

        ws.freeze_panes = 'A2'
        for col, width in zip('ABCD', (14, 46, 14, 14)):
            ws.column_dimensions[col].width = width


def _parse_as_of(raw) -> Optional[date]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)[:10]).date()
    except ValueError:
        raise ValueError(f'Invalid asOf {raw!r}: expected YYYY-MM-DD')
