"""
Import File model — bulk data-import batches.

One row per upload (e.g. an .xlsx of waste transactions). `type` routes the
backend processing ('transaction' for the waste-import flow). `preview_payload`
holds the extracted + fuzzy-matched, ready-to-insert transactions shown in the
review step; on confirm the created transactions are tagged with
`transactions.import_file_id` so an entire upload can be reverted (soft-deleted)
as one unit.

See migration 20260715_120000_072_create_import_files.sql.
"""

from sqlalchemy import Column, String, Text, BigInteger, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base, BaseModel


class ImportFile(Base, BaseModel):
    __tablename__ = 'import_files'

    # BaseModel provides: id, is_active, created_date, updated_date, deleted_date.

    organization_id = Column(BigInteger, nullable=False)
    # User (users.id) who uploaded — plain id, mirrors transactions.created_by_id (no FK).
    uploaded_by_id = Column(BigInteger, nullable=False)

    # Import kind, e.g. 'transaction'. Routes backend processing + scopes the history list.
    type = Column(String(50), nullable=False, default='transaction')

    # Uploaded file metadata + S3 location of the raw file.
    original_filename = Column(String(512))
    s3_key = Column(Text)
    s3_bucket = Column(String(255))
    file_size = Column(BigInteger)
    mime_type = Column(String(255))

    # Lifecycle: uploaded → extracting → extracted → confirming → confirmed → reverted; or failed.
    status = Column(String(30), nullable=False, default='uploaded')

    # Extracted + matched, grouped, ready-to-insert transactions for the review step.
    preview_payload = Column(JSONB)
    # Roll-up counts (rows, transactions, records, excluded) for the history list.
    summary = Column(JSONB)
    error = Column(Text)

    confirmed_date = Column(DateTime(timezone=True))
    reverted_date = Column(DateTime(timezone=True))
