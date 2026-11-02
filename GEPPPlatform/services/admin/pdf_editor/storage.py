"""S3 access for the PDF editor: presigned POST up, presigned GET down, HEAD to confirm.

The browser moves every byte. The Lambda only signs — a 30 MB scanned PDF never
passes through API Gateway (6 MB payload ceiling) and never sits in Lambda memory.

`PDF_EDITOR_S3_ENDPOINT_URL` points the client at an S3-compatible endpoint (a local
moto server) so the editor can be exercised end-to-end on a laptop without writing
into the real bucket. Unset in dev/prod.
"""

import os
import uuid
from typing import Any, Dict, Optional

import boto3
from botocore.config import Config as BotoConfig

DEFAULT_BUCKET = 'prod-gepp-platform-assets'
KEY_ROOT = 'backoffice/pdf-editor'

_client = None


def bucket_name() -> str:
    return os.getenv('PDF_EDITOR_S3_BUCKET') or os.getenv('S3_BUCKET_NAME') or DEFAULT_BUCKET


def _s3():
    global _client
    if _client is None:
        kwargs: Dict[str, Any] = {
            'region_name': os.getenv('AWS_REGION', 'ap-southeast-1'),
            'config': BotoConfig(signature_version='s3v4'),
        }
        endpoint = os.getenv('PDF_EDITOR_S3_ENDPOINT_URL')
        if endpoint:
            kwargs['endpoint_url'] = endpoint
            # localhost has no per-bucket subdomains
            kwargs['config'] = BotoConfig(signature_version='s3v4', s3={'addressing_style': 'path'})
        _client = boto3.client('s3', **kwargs)
    return _client


def new_key(*parts: Any, ext: str) -> str:
    """`backoffice/pdf-editor/<parts...>/<uuid>.<ext>` — never derived from the
    uploaded file name, so a name cannot steer where the object lands."""
    clean = '/'.join(str(p).strip('/') for p in parts if p not in (None, ''))
    return f'{KEY_ROOT}/{clean}/{uuid.uuid4().hex}.{ext}'


def presign_upload(key: str, content_type: str, max_bytes: int,
                   expires: int = 900) -> Dict[str, Any]:
    """Presigned POST bound to this key, this Content-Type and a size ceiling —
    S3 itself refuses anything bigger, whatever the browser claims."""
    post = _s3().generate_presigned_post(
        Bucket=bucket_name(),
        Key=key,
        Fields={'Content-Type': content_type},
        Conditions=[
            {'Content-Type': content_type},
            ['content-length-range', 1, int(max_bytes)],
        ],
        ExpiresIn=expires,
    )
    return {'uploadUrl': post['url'], 'uploadFields': post['fields']}


def presign_get(key: str, content_type: Optional[str] = None,
                expires: int = 3600, bucket: Optional[str] = None) -> str:
    params: Dict[str, Any] = {'Bucket': bucket or bucket_name(), 'Key': key}
    if content_type:
        params['ResponseContentType'] = content_type
    return _s3().generate_presigned_url('get_object', Params=params, ExpiresIn=expires)


def head_size(key: str, bucket: Optional[str] = None) -> Optional[int]:
    """Size of the object S3 actually holds, or None when nothing landed."""
    try:
        res = _s3().head_object(Bucket=bucket or bucket_name(), Key=key)
        return int(res['ContentLength'])
    except Exception:
        return None
