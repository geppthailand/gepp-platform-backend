"""
Organization Setup Import model — back-office "Import Organization Setup" batches.

One row per uploaded 5-tab xlsx (Users, Tags, Tenants, Origins, Destinations). The
import creates entities for a target organization and tags this batch with the ids it
created so the whole import can be reverted:
  - users / tags / tenants → INSERT (appended); reverted = soft-delete by id.
  - origins / destinations → REPLACE (a new organization_setup version whose tree holds
    only the imported nodes; the previous tree's nodes stay active → become recycle-bin
    orphans). Reverted = soft-delete the imported user_locations + strip their nodeIds
    from root_nodes/hub_node (a further new version).

See migration 20260716_130000_074_create_organization_setup_imports.sql.
"""

from sqlalchemy import Column, String, Text, BigInteger, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base, BaseModel


class OrganizationSetupImport(Base, BaseModel):
    __tablename__ = 'organization_setup_imports'

    # BaseModel provides: id, is_active, created_date, updated_date, deleted_date.

    organization_id = Column(BigInteger, nullable=False)
    # Back-office admin (user_locations.id) who ran the import — plain id, no FK.
    uploaded_by_id = Column(BigInteger)

    # Lifecycle: uploaded → extracting → extracted → confirming → confirmed → reverted; or failed.
    status = Column(String(30), nullable=False, default='uploaded')

    # Uploaded file metadata + S3 location of the raw xlsx.
    original_filename = Column(String(512))
    s3_key = Column(Text)
    s3_bucket = Column(String(255))
    file_size = Column(BigInteger)
    mime_type = Column(String(255))

    # Extracted + validated (possibly admin-edited) preview for the review step.
    preview_payload = Column(JSONB)
    # Roll-up counts per section for the version list.
    summary = Column(JSONB)
    error = Column(Text)

    # Ids created by this import (for revert). Arrays of user_locations.id /
    # user_location_tags.id / user_tenants.id. created_location_ids covers origins + hubs.
    created_user_ids = Column(JSONB, default=list)
    created_tag_ids = Column(JSONB, default=list)
    created_tenant_ids = Column(JSONB, default=list)
    created_location_ids = Column(JSONB, default=list)
    # organization_setup version this import created (origins/destinations replace).
    created_setup_version_id = Column(BigInteger)

    confirmed_date = Column(DateTime(timezone=True))
    reverted_date = Column(DateTime(timezone=True))
