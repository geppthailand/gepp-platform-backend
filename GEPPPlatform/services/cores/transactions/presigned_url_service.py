"""
Presigned URL Service for Transaction File Uploads
Generates S3 presigned URLs for direct file uploads
Creates file records in database for tracking
"""

import boto3
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session
import logging

from ....models.cores.files import File, FileType, FileStatus, FileSource

logger = logging.getLogger(__name__)


class TransactionPresignedUrlService:
    """Service for generating S3 presigned URLs for transaction file uploads"""

    def __init__(self):
        # Initialize S3 client with explicit credentials
        # aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        # aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region = os.getenv('AWS_REGION', 'ap-southeast-1')  # Default to us-east-1 if not set

        # Set bucket name - use a bucket you have access to
        self.bucket_name = os.getenv('S3_BUCKET_NAME', 'prod-gepp-platform-assets')

        # Try default credential chain
        try:
            # Use path-style addressing if bucket name contains dots to avoid SSL certificate issues
            s3_config = boto3.session.Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'} if '.' in self.bucket_name else {}
            )
            self.s3_client = boto3.client('s3', region_name=aws_region, config=s3_config)
            # Test if credentials work
            self.s3_client.list_buckets()
            logger.info(f"Using AWS default credential chain with {'path-style' if '.' in self.bucket_name else 'virtual-hosted-style'} addressing")
        except Exception as e:
            logger.error(f"No valid AWS credentials found: {str(e)}")
            logger.info("Falling back to Mock S3 Service for development")
            self.use_mock = True
            return

        # Initialize variables
        self.use_mock = False

    def get_transaction_file_upload_presigned_urls(
        self,
        file_names: List[str],
        organization_id: int,
        user_id: int,
        db: Session = None,
        file_type: str = 'transaction_image',
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[int] = None,
        expiration_seconds: int = 3600
    ) -> Dict[str, Any]:
        """
        Generate presigned URLs for transaction file uploads and create file records

        Args:
            file_names: List of original file names
            organization_id: Organization ID for path structure
            user_id: User ID for audit trail
            db: Database session for creating file records
            file_type: Type of file (default: 'transaction_image')
            related_entity_type: Optional entity type this file relates to
            related_entity_id: Optional entity ID this file relates to
            expiration_seconds: URL expiration time (default: 1 hour)

        Returns:
            Dict with presigned URLs, file IDs, and metadata
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
                    # Use path-style URLs if bucket name contains dots to avoid SSL certificate issues
                    aws_region = os.getenv('AWS_REGION', 'us-east-1')
                    if '.' in self.bucket_name:
                        # Path-style URL for buckets with dots
                        if aws_region == 'us-east-1':
                            final_url = f"https://s3.amazonaws.com/{self.bucket_name}/{s3_key}"
                        else:
                            final_url = f"https://s3.{aws_region}.amazonaws.com/{self.bucket_name}/{s3_key}"
                    else:
                        # Virtual-hosted-style URL for buckets without dots
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

            # Create file records in database if db session provided
            file_records_data = []
            if db:
                try:
                    # Convert file_type string to FileType enum
                    file_type_enum = FileType[file_type] if isinstance(file_type, str) else file_type

                    for presigned_item in presigned_data:
                        file_record = File(
                            file_type=file_type_enum,
                            status=FileStatus.pending,
                            url=presigned_item['final_s3_url'],
                            s3_key=presigned_item['s3_key'],
                            s3_bucket=self.bucket_name,
                            original_filename=presigned_item['original_filename'],
                            mime_type=presigned_item['content_type'],
                            organization_id=organization_id,
                            uploader_id=user_id,
                            related_entity_type=related_entity_type,
                            related_entity_id=related_entity_id,
                            file_metadata={
                                'presigned_created_at': datetime.now().isoformat(),
                                'expiration_seconds': expiration_seconds
                            }
                        )
                        db.add(file_record)
                        db.flush()  # Get the ID

                        # Add file_id to presigned data
                        presigned_item['file_id'] = file_record.id
                        file_records_data.append({
                            'file_id': file_record.id,
                            'original_filename': presigned_item['original_filename'],
                            's3_key': presigned_item['s3_key']
                        })

                    db.commit()
                    logger.info(f"Created {len(file_records_data)} file records in database")
                except Exception as db_error:
                    logger.error(f"Error creating file records: {str(db_error)}")
                    if db:
                        db.rollback()
                    # Continue without failing - files can still be uploaded

            logger.info(f"Successfully generated {len(presigned_data)} presigned URLs")
            return {
                'success': True,
                'message': f'Generated {len(presigned_data)} presigned URLs',
                'presigned_urls': presigned_data,
                'file_records': file_records_data,
                'expires_in_seconds': expiration_seconds
            }

        except Exception as e:
            logger.error(f"Unexpected error in get_transaction_file_upload_presigned_urls: {str(e)}")
            if db:
                db.rollback()
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

    def get_transaction_file_view_presigned_urls_by_ids(
        self,
        file_ids: List[int],
        db: Session,
        organization_id: int,
        user_id: int,
        expiration_seconds: int = 3600
    ) -> Dict[str, Any]:
        """
        Generate presigned URLs for viewing files by their database IDs

        For files with source='ext', returns the URL directly without generating presigned URL
        For files with source='s3', generates presigned URLs for secure access

        Args:
            file_ids: List of file IDs from files table
            db: Database session
            organization_id: Organization ID for access control
            user_id: User ID for audit trail
            expiration_seconds: URL expiration time (default: 1 hour)

        Returns:
            Dict with presigned view URLs mapped by file ID
        """
        try:
            if not file_ids:
                return {
                    'success': True,
                    'message': 'No file IDs provided',
                    'presigned_urls': {},
                    'expires_in_seconds': expiration_seconds
                }

            # Fetch file records from database
            file_records = db.query(File).filter(
                File.id.in_(file_ids),
                File.organization_id == organization_id,
                File.is_active == True
            ).all()

            # print("--==--==", file_records)

            if not file_records:
                return {
                    'success': False,
                    'message': 'No files found with provided IDs',
                    'presigned_urls': {}
                }

            # Separate files by source type
            ext_files = []  # External URLs - use directly
            s3_files = []   # S3 files - need presigned URLs
            presigned_by_id = {}
            errors = []

            for file_record in file_records:
                try:
                    # Check file source
                    if file_record.source == FileSource.ext:
                        # External URL - return directly without generating presigned URL
                        presigned_by_id[file_record.id] = {
                            'file_id': file_record.id,
                            'view_url': file_record.url,
                            'source': 'ext',
                            'expires_at': None  # External URLs don't expire
                        }
                        # print("ext_files", file_record.url)
                        ext_files.append(file_record.id)
                        logger.info(f"File {file_record.id} is external, using URL directly: {file_record.url}")

                    elif file_record.source == FileSource.s3:
                        # S3 file - will need presigned URL
                        s3_files.append(file_record)
                        logger.info(f"File {file_record.id} is S3-hosted, will generate presigned URL")

                    else:
                        # Unknown source type
                        error_msg = f"Unknown file source type: {file_record.source}"
                        logger.warning(error_msg)
                        errors.append({'file_id': file_record.id, 'error': error_msg})

                except Exception as e:
                    error_msg = f"Error processing file {file_record.id}: {str(e)}"
                    logger.error(error_msg)
                    errors.append({'file_id': file_record.id, 'error': str(e)})

            # Generate presigned URLs for S3 files only
            if s3_files:
                file_urls = [file_record.url for file_record in s3_files]
                file_id_to_url = {file_record.id: file_record.url for file_record in s3_files}

                # Generate presigned URLs using existing method
                result = self.get_transaction_file_view_presigned_urls(
                    file_urls=file_urls,
                    organization_id=organization_id,
                    user_id=user_id,
                    expiration_seconds=expiration_seconds,
                    db=db  # Pass db session for file source checking
                )

                if result.get('success'):
                    # Map presigned URLs back to file IDs
                    url_to_presigned = {
                        item['original_url']: item
                        for item in result.get('presigned_urls', [])
                    }

                    for file_id, original_url in file_id_to_url.items():
                        if original_url in url_to_presigned:
                            presigned_info = url_to_presigned[original_url]
                            presigned_by_id[file_id] = {
                                'file_id': file_id,
                                'view_url': presigned_info['view_url'],
                                'source': 's3',
                                'expires_at': presigned_info.get('expires_at')
                            }

                    # Collect any errors from S3 presigned URL generation
                    if result.get('errors'):
                        errors.extend(result['errors'])
                else:
                    # If S3 presigned URL generation completely failed
                    logger.error(f"Failed to generate S3 presigned URLs: {result.get('message')}")
                    if result.get('errors'):
                        errors.extend(result['errors'])

            # Prepare response
            total_processed = len(presigned_by_id)
            total_requested = len(file_records)

            logger.info(f"Processed {total_processed}/{total_requested} files: {len(ext_files)} ext, {len(s3_files)} s3")

            message_parts = []
            if ext_files:
                message_parts.append(f"{len(ext_files)} external URLs")
            if len(presigned_by_id) - len(ext_files) > 0:
                message_parts.append(f"{len(presigned_by_id) - len(ext_files)} presigned URLs")

            message = f"Generated {' and '.join(message_parts)}" if message_parts else "No URLs generated"

            if errors:
                message += f" ({len(errors)} failed)"

            return {
                'success': True if presigned_by_id else False,
                'message': message,
                'presigned_urls': presigned_by_id,
                'expires_in_seconds': expiration_seconds,
                'errors': errors if errors else []
            }

        except Exception as e:
            logger.error(f"Error generating presigned URLs by file IDs: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to generate presigned URLs: {str(e)}',
                'presigned_urls': {}
            }

    def get_transaction_file_view_presigned_urls(
        self,
        file_urls: List[str],
        organization_id: int,
        user_id: int,
        expiration_seconds: int = 3600,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Generate presigned URLs for viewing transaction files

        For files with source='ext', returns the URL directly without generating presigned URL
        For files with source='s3', generates presigned URLs for secure access

        Args:
            file_urls: List of S3 file URLs to generate view URLs for
            organization_id: Organization ID for access control
            user_id: User ID for audit trail
            expiration_seconds: URL expiration time (default: 1 hour)
            db: Optional database session to check file source types

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
            errors = []

            # If db session provided, check file sources first
            url_to_source = {}
            if db:
                try:
                    file_records = db.query(File).filter(
                        File.url.in_(file_urls),
                        File.organization_id == organization_id,
                        File.is_active == True
                    ).all()
                    url_to_source = {f.url: f.source for f in file_records}
                    logger.info(f"Found {len(url_to_source)} file records in database")
                except Exception as e:
                    logger.warning(f"Could not query file sources from database: {str(e)}")
                    # Continue without source information

            for file_url in file_urls:
                try:
                    # Check if this is an external URL (source='ext')
                    file_source = url_to_source.get(file_url)

                    if file_source == FileSource.ext:
                        # External URL - return directly without generating presigned URL
                        logger.info(f"File is external, using URL directly: {file_url}")
                        presigned_data.append({
                            'original_url': file_url,
                            's3_key': None,
                            'view_url': file_url,  # Use original URL directly
                            'source': 'ext',
                            'expires_at': None  # External URLs don't expire
                        })
                        continue

                    # For S3 files or unknown sources, generate presigned URL
                    # Extract S3 key from the URL
                    s3_key = self._extract_s3_key_from_url(file_url)
                    if not s3_key:
                        error_msg = f"Could not extract S3 key from URL: {file_url}"
                        logger.warning(error_msg)
                        errors.append({'url': file_url, 'error': 'Invalid S3 URL format'})
                        continue

                    # Verify the file belongs to the organization (basic security check)
                    if not s3_key.startswith(f"org/{organization_id}/"):
                        error_msg = f"File does not belong to organization {organization_id}: {s3_key}"
                        logger.warning(error_msg)
                        errors.append({'url': file_url, 'error': 'Access denied - file does not belong to organization'})
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
                        'source': 's3',
                        'expires_at': (datetime.now() + timedelta(seconds=expiration_seconds)).isoformat()
                    })

                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    error_msg = f"AWS ClientError for {file_url} - Code: {error_code}, Message: {str(e)}"
                    logger.error(error_msg)
                    errors.append({'url': file_url, 'error': f"AWS Error ({error_code}): {str(e)}"})
                    continue
                except Exception as e:
                    error_msg = f"Error processing {file_url}: {str(e)}"
                    logger.error(error_msg)
                    errors.append({'url': file_url, 'error': str(e)})
                    continue

            if not presigned_data:
                error_details = '; '.join([f"{err['url']}: {err['error']}" for err in errors[:3]])  # Show first 3 errors
                return {
                    'success': False,
                    'message': f'Failed to generate any view presigned URLs. Errors: {error_details}',
                    'errors': errors
                }

            logger.info(f"Successfully generated {len(presigned_data)} view presigned URLs")

            # Prepare response message
            if errors:
                message = f'Generated {len(presigned_data)} view presigned URLs ({len(errors)} failed)'
            else:
                message = f'Generated {len(presigned_data)} view presigned URLs'

            return {
                'success': True,
                'message': message,
                'presigned_urls': presigned_data,
                'expires_in_seconds': expiration_seconds,
                'errors': errors if errors else []
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