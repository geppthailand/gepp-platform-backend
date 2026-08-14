"""
S3 File Upload Service
Handles file uploads to AWS S3 with proper naming and organization
"""

import boto3
import os
import re
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import quote
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError, BotoCoreError
import mimetypes
import hashlib


def safe_ascii_filename(filename: Optional[str], fallback_stem: str = 'file', default_ext: str = '') -> str:
    """Auto-rename a user-supplied filename to a readable ASCII one.

    Thai (or any non-ASCII) filenames cannot be sent as S3 metadata, so rename rather than
    encode: slugify whatever ASCII the name has and keep the extension. When the stem has no
    usable ASCII at all — the normal case for a Thai filename — fall back to
    `{fallback_stem}-{hash}`, where the hash is derived from the original name so re-uploading
    the same file yields the same label.

    Note the stored S3 *key* is already generated independently (id + timestamp + uuid); this
    only names the human-readable copy kept in metadata.
    """
    name = (filename or '').strip()
    stem, ext = os.path.splitext(name)
    ext = (ext or default_ext).lower()
    # Reject a bogus "extension" (e.g. a dot inside a Thai word) rather than propagate it.
    if not re.match(r'^\.[a-z0-9]{1,8}$', ext):
        ext = default_ext
    slug = re.sub(r'[^A-Za-z0-9._-]+', '-', stem).strip('-._')
    if not slug:
        digest = hashlib.sha1(stem.encode('utf-8')).hexdigest()[:8] if stem else ''
        slug = f"{fallback_stem}-{digest}" if digest else fallback_stem
    return f"{slug[:80]}{ext}"


def ascii_metadata(value: Optional[str], fallback: str = 'unknown') -> str:
    """Make a value safe to send as S3 object metadata.

    S3 metadata travels in HTTP headers, so it must be ASCII. botocore enforces this
    *client-side* and raises ParamValidationError before the request is sent, which means a
    Thai filename silently kills the whole upload — see `upload_material_image`, where the
    resulting `None` used to be logged as "S3 unavailable?" and the image quietly dropped.

    Percent-encode rather than strip, so the original stays recoverable with
    `urllib.parse.unquote`. Thai text is ~3 bytes/char before encoding and ~9 after, well
    within S3's 2KB user-metadata budget for filename-length values.
    """
    if not value:
        return fallback
    try:
        value.encode('ascii')
        return value
    except UnicodeEncodeError:
        return quote(value, safe='')


def presentable_image_url(url: Optional[str], s3=None) -> Optional[str]:
    """Turn a stored image_url into something a browser can actually load.

    Images uploaded by the platform live in the PRIVATE `prod-gepp-platform-assets` bucket, so a
    raw S3 URL 403s — presign a short-lived GET for those. Legacy images in the public `gepp-prod`
    bucket are returned untouched. Never raises: on any failure it falls back to the stored URL so
    one bad row degrades to a broken thumbnail instead of failing the whole list.

    Pass `s3` when resolving a batch so the client is built once per request, not per image.
    """
    if not url or not isinstance(url, str):
        return url
    marker = ".amazonaws.com/"
    if "prod-gepp-platform-assets" not in url or marker not in url:
        return url
    key = url.split(marker, 1)[1]
    try:
        if s3 is None:
            s3 = S3FileUploadService()
        return s3.s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": s3.bucket_name, "Key": key},
            ExpiresIn=3600,
        )
    except Exception:
        return url


class S3FileUploadService:
    """Service to handle file uploads to S3"""

    def __init__(self):
        """Initialize S3 client.

        Pinned to SigV4: boto3 still defaults to SigV2 for plain `client('s3')`, which produces
        presigned URLs of the `?AWSAccessKeyId=...&Signature=...` form. S3 no longer accepts
        those in regions launched after 2014 and is retiring them elsewhere, so a presigned
        thumbnail would start 403-ing with no code change on our side. `pdf_export_hub` already
        pins s3v4 for the same reason.
        """
        self.s3_client = boto3.client('s3', config=BotoConfig(signature_version='s3v4'))
        self.bucket_name = 'prod-gepp-platform-assets'

    def upload_transaction_files(
        self,
        files: List[Dict[str, Any]],
        transaction_record_id: int,
        upload_type: str = 'transaction'
    ) -> List[Dict[str, Any]]:
        """
        Upload files for a transaction/transaction_record to S3

        Args:
            files: List of file objects with 'data', 'filename', 'content_type'
            transaction_record_id: ID of the transaction record
            upload_type: Type of upload ('transaction' or 'transaction_record')

        Returns:
            List of uploaded file info with S3 URLs
        """
        uploaded_files = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for file_obj in files:
            try:
                # Generate unique filename
                original_filename = file_obj.get('filename', 'unknown')
                file_extension = os.path.splitext(original_filename)[1]
                unique_filename = f"{transaction_record_id}_{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"

                # Create S3 key path
                s3_key = f"business/transactions/{upload_type}/{transaction_record_id}/{unique_filename}"

                # Determine content type
                content_type = file_obj.get('content_type')
                if not content_type:
                    content_type, _ = mimetypes.guess_type(original_filename)
                    content_type = content_type or 'application/octet-stream'

                # Calculate file size and hash
                file_data = file_obj['data']
                file_size = len(file_data) if isinstance(file_data, (bytes, str)) else 0
                file_hash = hashlib.md5(file_data if isinstance(file_data, bytes) else file_data.encode()).hexdigest()

                # Upload to S3
                extra_args = {
                    'ContentType': content_type,
                    'Metadata': {
                        'original_filename': original_filename,
                        'transaction_record_id': str(transaction_record_id),
                        'upload_type': upload_type,
                        'upload_timestamp': timestamp,
                        'file_hash': file_hash
                    }
                }

                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=file_data,
                    **extra_args
                )

                # Generate S3 URL
                s3_url = f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}"

                uploaded_files.append({
                    'original_filename': original_filename,
                    's3_url': s3_url,
                    's3_key': s3_key,
                    'content_type': content_type,
                    'file_size': file_size,
                    'file_hash': file_hash,
                    'upload_timestamp': timestamp
                })

            except (ClientError, BotoCoreError) as e:
                print(f"Error uploading file {file_obj.get('filename', 'unknown')}: {str(e)}")
                # Continue with other files even if one fails
                continue
            except Exception as e:
                print(f"Unexpected error uploading file {file_obj.get('filename', 'unknown')}: {str(e)}")
                continue

        return uploaded_files

    def upload_import_file(
        self,
        file_data: bytes,
        filename: str,
        content_type: Optional[str],
        import_type: str,
        organization_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Upload a raw import file (e.g. an .xlsx) to S3 under business/imports/.

        Returns a dict {s3_key, s3_url, s3_bucket, file_size, content_type, original_filename}
        or None on failure.
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = os.path.splitext(filename or '')[1] or '.xlsx'
            unique_filename = f"{organization_id}_{timestamp}_{uuid.uuid4().hex[:8]}{ext}"
            s3_key = f"business/imports/{import_type}/{organization_id}/{unique_filename}"

            if not content_type:
                content_type, _ = mimetypes.guess_type(filename or '')
                content_type = content_type or 'application/octet-stream'

            file_size = len(file_data) if isinstance(file_data, (bytes, bytearray)) else 0
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_data,
                ContentType=content_type,
                Metadata={
                    'original_filename': safe_ascii_filename(filename, f'import-{organization_id}', '.xlsx'),
                    'original_filename_encoded': ascii_metadata(filename),
                    'import_type': import_type,
                    'organization_id': str(organization_id),
                    'upload_timestamp': timestamp,
                },
            )
            return {
                'original_filename': filename,
                's3_key': s3_key,
                's3_url': f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}",
                's3_bucket': self.bucket_name,
                'file_size': file_size,
                'content_type': content_type,
            }
        except (ClientError, BotoCoreError) as e:
            print(f"Error uploading import file {filename}: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error uploading import file {filename}: {str(e)}")
            return None

    def upload_material_image(
        self,
        file_data: bytes,
        filename: Optional[str],
        content_type: Optional[str],
        material_id: int,
    ) -> Optional[str]:
        """Upload a single material image to S3 under business/materials/{id}/ and return its
        public URL (or None on failure)."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = os.path.splitext(filename or '')[1] or '.png'
            unique_filename = f"{material_id}_{timestamp}_{uuid.uuid4().hex[:8]}{ext}"
            s3_key = f"business/materials/{material_id}/{unique_filename}"
            if not content_type:
                content_type, _ = mimetypes.guess_type(filename or '')
                content_type = content_type or 'image/png'
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_data,
                ContentType=content_type,
                Metadata={
                    'material_id': str(material_id),
                    # Renamed for readability; the exact original is kept percent-encoded so
                    # nothing is lost (urllib.parse.unquote round-trips it).
                    'original_filename': safe_ascii_filename(filename, f'material-{material_id}', '.png'),
                    'original_filename_encoded': ascii_metadata(filename),
                    'upload_timestamp': timestamp,
                },
            )
            return f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}"
        except (ClientError, BotoCoreError) as e:
            print(f"Error uploading material image {filename}: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error uploading material image {filename}: {str(e)}")
            return None

    def download_file(self, s3_key: str) -> Optional[bytes]:
        """Download a file's bytes from S3; None on failure."""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            return response['Body'].read()
        except (ClientError, BotoCoreError) as e:
            print(f"Error downloading file {s3_key}: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error downloading file {s3_key}: {str(e)}")
            return None

    def delete_file(self, s3_key: str) -> bool:
        """
        Delete a file from S3

        Args:
            s3_key: S3 key of the file to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except (ClientError, BotoCoreError) as e:
            print(f"Error deleting file {s3_key}: {str(e)}")
            return False
        except Exception as e:
            print(f"Unexpected error deleting file {s3_key}: {str(e)}")
            return False

    def get_file_info(self, s3_key: str) -> Optional[Dict[str, Any]]:
        """
        Get file information from S3

        Args:
            s3_key: S3 key of the file

        Returns:
            File information dict or None if not found
        """
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return {
                's3_key': s3_key,
                's3_url': f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}",
                'content_type': response.get('ContentType'),
                'file_size': response.get('ContentLength'),
                'last_modified': response.get('LastModified'),
                'metadata': response.get('Metadata', {})
            }
        except (ClientError, BotoCoreError) as e:
            print(f"Error getting file info for {s3_key}: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error getting file info for {s3_key}: {str(e)}")
            return None

    def list_transaction_files(self, transaction_record_id: int, upload_type: str = None) -> List[Dict[str, Any]]:
        """
        List all files for a transaction record

        Args:
            transaction_record_id: ID of the transaction record
            upload_type: Optional filter by upload type

        Returns:
            List of file information
        """
        try:
            prefix = f"business/transactions/"
            if upload_type:
                prefix += f"{upload_type}/"
            prefix += f"{transaction_record_id}/"

            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )

            files = []
            for obj in response.get('Contents', []):
                s3_key = obj['Key']
                file_info = self.get_file_info(s3_key)
                if file_info:
                    files.append(file_info)

            return files

        except (ClientError, BotoCoreError) as e:
            print(f"Error listing files for transaction record {transaction_record_id}: {str(e)}")
            return []
        except Exception as e:
            print(f"Unexpected error listing files for transaction record {transaction_record_id}: {str(e)}")
            return []