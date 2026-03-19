"""
ESG Document Service — Upload to S3, trigger AI classification
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import logging
import os

from ...models.esg.documents import EsgDocument
from ...models.esg.waste_records import EsgWasteRecord

logger = logging.getLogger(__name__)


class EsgDocumentService:
    """Handles document upload, S3 storage, and AI classification orchestration"""

    def __init__(self, db: Session):
        self.db = db

    def upload_and_classify(self, organization_id: int, file_data: Dict[str, Any], uploaded_by_id: int = None) -> Dict[str, Any]:
        """
        Upload document to S3 and trigger AI classification.
        file_data should contain: file_name, file_url (already uploaded to S3 via presigned URL)
        """
        # Create document record
        doc = EsgDocument(
            organization_id=organization_id,
            file_name=file_data['file_name'],
            file_url=file_data['file_url'],
            file_type=file_data.get('file_type'),
            file_size_bytes=file_data.get('file_size_bytes'),
            source=file_data.get('source', 'upload'),
            uploaded_by_id=uploaded_by_id,
            ai_classification_status='pending',
        )
        self.db.add(doc)
        self.db.flush()

        # Trigger async classification (in production, this would be a background task)
        try:
            classification_result = self._classify_document(doc)
            if classification_result:
                doc.ai_classification_status = 'completed'
                doc.ai_classification_result = classification_result
                doc.ai_confidence = classification_result.get('confidence', 0)
                doc.ai_classified_at = datetime.utcnow()
                doc.esg_category = classification_result.get('esg_category')
                doc.esg_subcategory = classification_result.get('esg_subcategory')
                doc.document_type = classification_result.get('document_type')
                doc.document_date = classification_result.get('document_date')
                doc.vendor_name = classification_result.get('vendor_name')
                doc.summary = classification_result.get('summary')
                doc.tags = classification_result.get('tags', [])
                self.db.flush()

                # Step 2: If waste document, extract waste data
                if doc.esg_category == 'environment' and doc.esg_subcategory == 'scope3_waste':
                    self._extract_waste_data(doc, classification_result)
        except Exception as e:
            logger.error(f"Classification failed for document {doc.id}: {str(e)}")
            doc.ai_classification_status = 'failed'
            self.db.flush()

        return {'success': True, 'document': doc.to_dict()}

    def classify_document(self, document_id: int, organization_id: int) -> Dict[str, Any]:
        """Manually trigger classification for a document"""
        doc = self.db.query(EsgDocument).filter(
            EsgDocument.id == document_id,
            EsgDocument.organization_id == organization_id,
            EsgDocument.is_active == True
        ).first()

        if not doc:
            return {'success': False, 'message': 'Document not found'}

        doc.ai_classification_status = 'processing'
        self.db.flush()

        try:
            classification_result = self._classify_document(doc)
            if classification_result:
                doc.ai_classification_status = 'completed'
                doc.ai_classification_result = classification_result
                doc.ai_confidence = classification_result.get('confidence', 0)
                doc.ai_classified_at = datetime.utcnow()
                doc.esg_category = classification_result.get('esg_category')
                doc.esg_subcategory = classification_result.get('esg_subcategory')
                doc.document_type = classification_result.get('document_type')
                doc.document_date = classification_result.get('document_date')
                doc.vendor_name = classification_result.get('vendor_name')
                doc.summary = classification_result.get('summary')
                doc.tags = classification_result.get('tags', [])
                self.db.flush()

                # Step 2: If waste document, extract waste data
                if doc.esg_category == 'environment' and doc.esg_subcategory == 'scope3_waste':
                    self._extract_waste_data(doc, classification_result)

                return {'success': True, 'message': 'Classification completed', 'document': doc.to_dict()}
            else:
                doc.ai_classification_status = 'failed'
                self.db.flush()
                return {'success': False, 'message': 'Classification returned no results'}

        except Exception as e:
            logger.error(f"Classification error: {str(e)}")
            doc.ai_classification_status = 'failed'
            self.db.flush()
            return {'success': False, 'message': f'Classification failed: {str(e)}'}

    def _classify_document(self, doc: EsgDocument) -> Optional[Dict[str, Any]]:
        """
        Step 1: Classify ESG document using AI
        Returns classification result dict
        """
        try:
            from ...prompts.esg_classify.clients.llm_client import classify_esg_document
            result = classify_esg_document(doc.file_url, doc.file_name)
            return result
        except ImportError:
            logger.warning("ESG classify module not available, skipping AI classification")
            return None
        except Exception as e:
            logger.error(f"AI classification error: {str(e)}")
            raise

    def _extract_waste_data(self, doc: EsgDocument, classification_result: Dict[str, Any]):
        """
        Step 2: Extract waste data from waste-related documents
        Creates EsgWasteRecord entries
        """
        try:
            from ...prompts.esg_classify.clients.llm_client import extract_waste_data
            from .esg_service import EsgService

            waste_result = extract_waste_data(doc.file_url, doc.file_name)
            if waste_result and waste_result.get('waste_items'):
                esg_service = EsgService(self.db)
                for item in waste_result['waste_items']:
                    item['document_id'] = doc.id
                    item['source'] = 'ai'
                    if not item.get('record_date'):
                        item['record_date'] = doc.document_date or datetime.utcnow().date()
                    esg_service.create_waste_record(
                        organization_id=doc.organization_id,
                        data=item,
                        created_by_id=doc.uploaded_by_id
                    )
        except ImportError:
            logger.warning("ESG classify module not available for waste extraction")
        except Exception as e:
            logger.error(f"Waste data extraction error: {str(e)}")
