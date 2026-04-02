"""
ESG Export Service - Generate Excel exports of collected data (UC 4.1)
"""

import io
import uuid
from datetime import datetime

import boto3
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from GEPPPlatform.models.esg.data_entries import EsgDataEntry
from GEPPPlatform.models.esg.data_hierarchy import (
    EsgDataCategory as DataCategory,
    EsgDataSubcategory,
)


class EsgExportService:

    def __init__(self, session, s3_bucket: str = None):
        self.session = session
        self.s3_bucket = s3_bucket or 'gepp-esg-exports'
        self.s3_client = boto3.client('s3')

    def export_to_excel(self, organization_id: int) -> dict:
        """
        Query all data entries for the organization, generate an .xlsx file,
        upload to S3, and return a temporary download link.
        """
        entries = (
            self.session.query(EsgDataEntry)
            .filter(
                EsgDataEntry.organization_id == organization_id,
                EsgDataEntry.is_active == True,
            )
            .order_by(EsgDataEntry.entry_date.desc())
            .all()
        )

        wb = self._create_workbook(entries)

        # Write to buffer
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        # Upload to S3
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        file_key = f'exports/org_{organization_id}/esg_data_{timestamp}_{uuid.uuid4().hex[:8]}.xlsx'
        file_name = f'esg_data_{timestamp}.xlsx'

        self.s3_client.put_object(
            Bucket=self.s3_bucket,
            Key=file_key,
            Body=buffer.getvalue(),
            ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        # Generate presigned download URL (expires in 1 hour)
        download_url = self.s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.s3_bucket, 'Key': file_key},
            ExpiresIn=3600,
        )

        return {
            'download_url': download_url,
            'file_name': file_name,
            'expires_in': 3600,
        }

    def _create_workbook(self, entries: list) -> Workbook:
        """Create a formatted Excel workbook from data entries."""
        wb = Workbook()
        ws = wb.active
        ws.title = 'ESG Data'

        # Header style
        header_font = Font(bold=True, color='FFFFFF', size=11)
        header_fill = PatternFill(start_color='76B900', end_color='76B900', fill_type='solid')
        header_alignment = Alignment(horizontal='center', vertical='center')
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin'),
        )

        headers = ['#', 'Category', 'Subcategory', 'Value', 'Unit', 'Date', 'Scope', 'Notes', 'Evidence']
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = thin_border

        # Data rows
        for row_idx, entry in enumerate(entries, 2):
            ws.cell(row=row_idx, column=1, value=row_idx - 1)
            ws.cell(row=row_idx, column=2, value=str(entry.category_id))
            ws.cell(row=row_idx, column=3, value=str(entry.subcategory_id))
            ws.cell(row=row_idx, column=4, value=float(entry.value) if entry.value else 0)
            ws.cell(row=row_idx, column=5, value=entry.unit or '')
            ws.cell(row=row_idx, column=6, value=str(entry.entry_date) if entry.entry_date else '')
            ws.cell(row=row_idx, column=7, value=entry.scope_tag or '')
            ws.cell(row=row_idx, column=8, value=entry.notes or '')
            ws.cell(row=row_idx, column=9, value=entry.file_name or '')

        # Auto-width columns
        for col in ws.columns:
            max_length = max(len(str(cell.value or '')) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_length + 4, 40)

        return wb
