"""
S3 File Upload Service
Handles file uploads to AWS S3 with proper naming and organization
"""

import boto3
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from botocore.exceptions import ClientError, BotoCoreError
import mimetypes
import hashlib


class S3FileUploadService:
    """Service to handle file uploads to S3"""

    def __init__(self):
        """Initialize S3 client"""
        self.s3_client = boto3.client('s3')
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