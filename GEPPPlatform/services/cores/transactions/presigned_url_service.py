"""
Presigned URL Service for Transaction File Uploads
Generates S3 presigned URLs for direct file uploads
"""

import boto3
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)


class TransactionPresignedUrlService:
    """Service for generating S3 presigned URLs for transaction file uploads"""

    def __init__(self):
        # Initialize S3 client with explicit credentials
        # aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        # aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region = os.getenv('AWS_REGION', 'ap-southeast-1')  # Default to us-east-1 if not set

        # Try default credential chain
        try:
            self.s3_client = boto3.client('s3', region_name=aws_region)
            # Test if credentials work
            self.s3_client.list_buckets()
            logger.info("Using AWS default credential chain")
        except Exception as e:
            logger.error(f"No valid AWS credentials found: {str(e)}")
            logger.info("Falling back to Mock S3 Service for development")
            self.use_mock = True
            return

        # Initialize variables
        self.use_mock = False

        # Set bucket name - use a bucket you have access to
        self.bucket_name = os.getenv('S3_BUCKET_NAME', 'prod-gepp-platform-assets')

    def get_transaction_file_upload_presigned_urls(
        self,
        file_names: List[str],
        organization_id: int,
        user_id: int,
        expiration_seconds: int = 3600
    ) -> Dict[str, Any]:
        """
        Generate presigned URLs for transaction file uploads

        Args:
            file_names: List of original file names
            organization_id: Organization ID for path structure
            user_id: User ID for audit trail
            expiration_seconds: URL expiration time (default: 1 hour)

        Returns:
            Dict with presigned URLs and metadata
        """
        try:
            # Check if using mock service
            if hasattr(self, 'use_mock') and self.use_mock:
                from .mock_s3_service import MockS3Service
                mock_service = MockS3Service()
                return mock_service.get_transaction_file_upload_presigned_urls(
                    file_names, organization_id, user_id, expiration_seconds
                )

            # Log configuration for debugging
            logger.info(f"Generating presigned URLs for bucket: {self.bucket_name}")
            logger.info(f"File names: {file_names}")

            presigned_data = []
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            for file_name in file_names:
                # Generate unique filename
                file_extension = self._get_file_extension(file_name)
                unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}_{self._sanitize_filename(file_name)}"

                # S3 key structure
                current_date = datetime.now()
                s3_key = f"org/{organization_id}/transactions/{current_date.year}/{current_date.month:02d}/{unique_filename}"

                # Generate presigned URL
                content_type = self._get_content_type(file_extension)

                logger.info(f"Generating presigned URL for key: {s3_key}")

                try:
                    # Test bucket access first
                    try:
                        self.s3_client.head_bucket(Bucket=self.bucket_name)
                        logger.info(f"Successfully accessed bucket: {self.bucket_name}")
                    except ClientError as e:
                        logger.error(f"Cannot access bucket {self.bucket_name}: {str(e)}")
                        return {
                            'success': False,
                            'message': f'Cannot access S3 bucket {self.bucket_name}: {str(e)}'
                        }

                    response = self.s3_client.generate_presigned_post(
                        Bucket=self.bucket_name,
                        Key=s3_key,
                        Fields={
                            'Content-Type': content_type,
                        },
                        Conditions=[
                            {"bucket": self.bucket_name},
                            ["starts-with", "$key", s3_key],
                            {"Content-Type": content_type},
                            ["content-length-range", 1, 50 * 1024 * 1024]  # 1 byte to 50MB
                        ],
                        ExpiresIn=expiration_seconds
                    )

                    # Final S3 URL after upload (use correct region)
                    aws_region = os.getenv('AWS_REGION', 'us-east-1')
                    if aws_region == 'us-east-1':
                        final_url = f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}"
                    else:
                        final_url = f"https://{self.bucket_name}.s3.{aws_region}.amazonaws.com/{s3_key}"

                    logger.info(f"Generated presigned URL successfully for {file_name}")

                    presigned_data.append({
                        'original_filename': file_name,
                        'unique_filename': unique_filename,
                        's3_key': s3_key,
                        'upload_url': response['url'],
                        'upload_fields': response['fields'],
                        'final_s3_url': final_url,
                        'content_type': content_type,
                        'expires_at': (datetime.now() + timedelta(seconds=expiration_seconds)).isoformat()
                    })

                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    logger.error(f"AWS ClientError for {file_name} - Code: {error_code}, Message: {str(e)}")
                    return {
                        'success': False,
                        'message': f'AWS Error ({error_code}): {str(e)}'
                    }

            if not presigned_data:
                return {
                    'success': False,
                    'message': 'Failed to generate any presigned URLs'
                }

            logger.info(f"Successfully generated {len(presigned_data)} presigned URLs")
            return {
                'success': True,
                'message': f'Generated {len(presigned_data)} presigned URLs',
                'presigned_urls': presigned_data,
                'expires_in_seconds': expiration_seconds
            }

        except Exception as e:
            logger.error(f"Unexpected error in get_transaction_file_upload_presigned_urls: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to generate presigned URLs: {str(e)}'
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
            'xls': 'application/vnd.ms-excel',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'csv': 'text/csv',
            'txt': 'text/plain'
        }
        return content_types.get(file_extension, 'application/octet-stream')

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for S3 compatibility"""
        import re
        # Remove problematic characters
        sanitized = re.sub(r'[^\w\-_\.]', '_', filename)
        # Remove multiple underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        # Limit length
        if len(sanitized) > 200:
            name_part, ext_part = sanitized.rsplit('.', 1) if '.' in sanitized else (sanitized, '')
            sanitized = f"{name_part[:190]}.{ext_part}" if ext_part else name_part[:200]
        return sanitized

    def get_transaction_file_view_presigned_urls(
        self,
        file_urls: List[str],
        organization_id: int,
        user_id: int,
        expiration_seconds: int = 3600
    ) -> Dict[str, Any]:
        """
        Generate presigned URLs for viewing transaction files

        Args:
            file_urls: List of S3 file URLs to generate view URLs for
            organization_id: Organization ID for access control
            user_id: User ID for audit trail
            expiration_seconds: URL expiration time (default: 1 hour)

        Returns:
            Dict with presigned view URLs and metadata
        """
        try:
            # Check if using mock service
            if hasattr(self, 'use_mock') and self.use_mock:
                from .mock_s3_service import MockS3Service
                mock_service = MockS3Service()
                return mock_service.get_transaction_file_view_presigned_urls(
                    file_urls, organization_id, user_id, expiration_seconds
                )

            # Log configuration for debugging
            logger.info(f"Generating view presigned URLs for bucket: {self.bucket_name}")
            logger.info(f"File URLs: {file_urls}")

            presigned_data = []

            for file_url in file_urls:
                try:
                    # Extract S3 key from the URL
                    s3_key = self._extract_s3_key_from_url(file_url)
                    if not s3_key:
                        logger.warning(f"Could not extract S3 key from URL: {file_url}")
                        continue

                    # Verify the file belongs to the organization (basic security check)
                    if not s3_key.startswith(f"org/{organization_id}/"):
                        logger.warning(f"File does not belong to organization {organization_id}: {s3_key}")
                        continue

                    logger.info(f"Generating view presigned URL for key: {s3_key}")

                    # Generate presigned URL for GET operation
                    presigned_url = self.s3_client.generate_presigned_url(
                        'get_object',
                        Params={
                            'Bucket': self.bucket_name,
                            'Key': s3_key
                        },
                        ExpiresIn=expiration_seconds
                    )

                    logger.info(f"Generated view presigned URL successfully for {file_url}")

                    presigned_data.append({
                        'original_url': file_url,
                        's3_key': s3_key,
                        'view_url': presigned_url,
                        'expires_at': (datetime.now() + timedelta(seconds=expiration_seconds)).isoformat()
                    })

                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    logger.error(f"AWS ClientError for {file_url} - Code: {error_code}, Message: {str(e)}")
                    continue
                except Exception as e:
                    logger.error(f"Error processing {file_url}: {str(e)}")
                    continue

            if not presigned_data:
                return {
                    'success': False,
                    'message': 'Failed to generate any view presigned URLs'
                }

            logger.info(f"Successfully generated {len(presigned_data)} view presigned URLs")
            return {
                'success': True,
                'message': f'Generated {len(presigned_data)} view presigned URLs',
                'presigned_urls': presigned_data,
                'expires_in_seconds': expiration_seconds
            }

        except Exception as e:
            logger.error(f"Unexpected error in get_transaction_file_view_presigned_urls: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to generate view presigned URLs: {str(e)}'
            }

    def _extract_s3_key_from_url(self, file_url: str) -> str:
        """Extract S3 key from S3 URL"""
        try:
            # Handle different S3 URL formats
            # Format 1: https://bucket.s3.amazonaws.com/key
            # Format 2: https://bucket.s3.region.amazonaws.com/key
            # Format 3: https://s3.amazonaws.com/bucket/key
            # Format 4: https://s3.region.amazonaws.com/bucket/key

            if self.bucket_name in file_url:
                if f"{self.bucket_name}.s3" in file_url:
                    # Format 1 & 2: https://bucket.s3[.region].amazonaws.com/key
                    parts = file_url.split(f"{self.bucket_name}.s3")
                    if len(parts) > 1:
                        key_part = parts[1]
                        # Remove .region.amazonaws.com/ or .amazonaws.com/
                        key_start = key_part.find('.amazonaws.com/')
                        if key_start != -1:
                            return key_part[key_start + len('.amazonaws.com/'):].strip('/')
                elif f"s3.amazonaws.com/{self.bucket_name}/" in file_url:
                    # Format 3: https://s3.amazonaws.com/bucket/key
                    return file_url.split(f"s3.amazonaws.com/{self.bucket_name}/", 1)[1]
                elif f"s3." in file_url and f".amazonaws.com/{self.bucket_name}/" in file_url:
                    # Format 4: https://s3.region.amazonaws.com/bucket/key
                    bucket_path = f".amazonaws.com/{self.bucket_name}/"
                    return file_url.split(bucket_path, 1)[1]

            return ""
        except Exception as e:
            logger.error(f"Error extracting S3 key from URL {file_url}: {str(e)}")
            return ""