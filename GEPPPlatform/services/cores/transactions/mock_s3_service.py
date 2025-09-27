"""
Mock S3 Service for Development/Testing
Use this when AWS credentials are not available
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class MockS3Service:
    """
    Mock S3 service that simulates file uploads for development
    Returns mock S3 URLs without actually uploading files
    """

    def __init__(self):
        self.bucket_name = "mock-dev-bucket"
        self.base_url = "https://mock-s3.example.com"
        logger.info("Using Mock S3 Service - files will not be actually uploaded")

    def get_transaction_file_upload_presigned_urls(
        self,
        file_names: List[str],
        organization_id: int,
        user_id: int,
        expiration_seconds: int = 3600
    ) -> Dict[str, Any]:
        """
        Generate mock presigned URLs for development
        """
        try:
            logger.info(f"Mock S3: Generating mock URLs for {len(file_names)} files")

            presigned_data = []
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            for file_name in file_names:
                # Generate mock data
                file_extension = self._get_file_extension(file_name)
                unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}_{self._sanitize_filename(file_name)}"

                current_date = datetime.now()
                s3_key = f"org/{organization_id}/transactions/{current_date.year}/{current_date.month:02d}/{unique_filename}"

                # Mock upload URL (just returns success immediately)
                mock_upload_url = f"{self.base_url}/mock-upload"

                # Final mock S3 URL
                final_url = f"{self.base_url}/{s3_key}"

                logger.info(f"Mock S3: Generated mock URL for {file_name} -> {final_url}")

                presigned_data.append({
                    'original_filename': file_name,
                    'unique_filename': unique_filename,
                    's3_key': s3_key,
                    'upload_url': mock_upload_url,
                    'upload_fields': {
                        'key': s3_key,
                        'Content-Type': self._get_content_type(file_extension),
                        'mock': 'true'
                    },
                    'final_s3_url': final_url,
                    'content_type': self._get_content_type(file_extension),
                    'expires_at': (datetime.now() + timedelta(seconds=expiration_seconds)).isoformat()
                })

            return {
                'success': True,
                'message': f'Generated {len(presigned_data)} mock presigned URLs',
                'presigned_urls': presigned_data,
                'expires_in_seconds': expiration_seconds,
                'mock_mode': True
            }

        except Exception as e:
            logger.error(f"Error in mock S3 service: {str(e)}")
            return {
                'success': False,
                'message': f'Mock S3 error: {str(e)}',
                'mock_mode': True
            }

    def _get_file_extension(self, filename: str) -> str:
        """Extract file extension"""
        if '.' in filename:
            return filename.rsplit('.', 1)[1].lower()
        return ''

    def _get_content_type(self, file_extension: str) -> str:
        """Get MIME type for file extension"""
        content_types = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'txt': 'text/plain'
        }
        return content_types.get(file_extension, 'application/octet-stream')

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename"""
        import re
        sanitized = re.sub(r'[^\w\-_\.]', '_', filename)
        sanitized = re.sub(r'_+', '_', sanitized)
        if len(sanitized) > 200:
            name_part, ext_part = sanitized.rsplit('.', 1) if '.' in sanitized else (sanitized, '')
            sanitized = f"{name_part[:190]}.{ext_part}" if ext_part else name_part[:200]
        return sanitized

    def get_transaction_file_view_presigned_urls(
        self,
        file_urls: list,
        organization_id: int,
        user_id: int,
        expiration_seconds: int = 3600
    ):
        """
        Mock implementation for generating view presigned URLs
        """
        from datetime import datetime, timedelta

        print(f"🎭 Mock S3 View Service - Generating view presigned URLs for {len(file_urls)} files")

        presigned_data = []

        for file_url in file_urls:
            # Generate mock view URL (in real implementation this would be a presigned URL)
            mock_view_url = f"https://mock-s3-view.example.com/view/{file_url.split('/')[-1]}?expires={expiration_seconds}&org={organization_id}"

            presigned_data.append({
                'original_url': file_url,
                's3_key': f"org/{organization_id}/transactions/mock/{file_url.split('/')[-1]}",
                'view_url': mock_view_url,
                'expires_at': (datetime.now() + timedelta(seconds=expiration_seconds)).isoformat()
            })

            print(f"🎭 Mock view URL generated for: {file_url}")

        return {
            'success': True,
            'message': f'Generated {len(presigned_data)} mock view presigned URLs',
            'presigned_urls': presigned_data,
            'expires_in_seconds': expiration_seconds
        }