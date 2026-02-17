"""
PDF Export Hub
Centralized hub for PDF generation via Lambda function.
Routes to appropriate export functions based on export_type.
"""

from typing import Dict, Any, Optional
import os
import re
import json
import boto3
import base64
import uuid
import logging
from datetime import datetime
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def _invoke_pdf_lambda(payload: Dict[str, Any], export_type: str = "reports") -> Dict[str, Any]:
    """
    Invoke the PDF export Lambda with the aggregated payload and export type.
    The Lambda function will route to the appropriate export function based on export_type.
    
    Args:
        payload: The data to be used for PDF generation
        export_type: Type of export ("reports" or "gri")
    
    Returns:
        Dict with at least {success: bool, pdf_base64?: str, filename?: str, error?: str}
    """
    fn_name = os.getenv("PDF_EXPORT_FUNCTION", "DEV-GEPPGenerateV3Report")
    client = boto3.client("lambda")
    
    # Include export_type in the payload so Lambda can route appropriately
    lambda_payload = {
        "data": payload,
        "export_type": export_type
    }
    
    print(f"[PDF_HUB] Invoking Lambda: {fn_name} with export_type: {export_type}")
    resp = client.invoke(
        FunctionName=fn_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(lambda_payload).encode("utf-8"),
    )
    
    print(f"[PDF_HUB] Lambda response keys: {list(resp.keys())}")
    print(f"[PDF_HUB] FunctionError in response: {'FunctionError' in resp}")
    
    # Check for Lambda function errors
    if "FunctionError" in resp:
        error_type = resp.get("FunctionError", "Unknown")
        print(f"[PDF_HUB] Lambda function error detected: {error_type}")
        logger.error(f"Lambda function error: {error_type}")
        try:
            raw = resp.get("Payload").read()
            print(f"[PDF_HUB] Error payload raw (first 500 chars): {raw[:500] if raw else 'None'}")
            error_payload = json.loads(raw)
            print(f"[PDF_HUB] Error payload parsed: {error_payload}")
            error_message = error_payload.get("errorMessage") or error_payload.get("error") or str(error_payload)
            print(f"[PDF_HUB] Extracted error message: {error_message}")
            logger.error(f"Lambda error details: {error_message}")
            return {"success": False, "error": f"Lambda function error ({error_type}): {error_message}"}
        except Exception as e:
            print(f"[PDF_HUB] Error reading Lambda error payload: {str(e)}")
            logger.error(f"Error reading Lambda error payload: {str(e)}", exc_info=True)
            return {"success": False, "error": f"Lambda function error ({error_type}): {str(e)}"}
    
    raw = resp.get("Payload").read()
    print(f"[PDF_HUB] Lambda response raw (first 500 chars): {raw[:500] if raw else 'None'}")
    
    try:
        out = json.loads(raw)
        print(f"[PDF_HUB] Lambda response parsed: {list(out.keys()) if isinstance(out, dict) else type(out)}")
        
        # API Gateway proxy shape
        if isinstance(out, dict) and "statusCode" in out and "body" in out:
            status_code = out.get("statusCode", 200)
            body_content = out.get("body") or "{}"
            
            print(f"[PDF_HUB] Lambda response statusCode: {status_code}")
            print(f"[PDF_HUB] Lambda response body (first 500 chars): {body_content[:500] if isinstance(body_content, str) else str(body_content)[:500]}")
            logger.info(f"Lambda response statusCode: {status_code}")
            
            try:
                parsed_body = json.loads(body_content) if isinstance(body_content, str) else body_content
                print(f"[PDF_HUB] Parsed body keys: {list(parsed_body.keys()) if isinstance(parsed_body, dict) else type(parsed_body)}")
                print(f"[PDF_HUB] Parsed body success: {parsed_body.get('success') if isinstance(parsed_body, dict) else 'N/A'}")
                print(f"[PDF_HUB] Parsed body error: {parsed_body.get('error') if isinstance(parsed_body, dict) else 'N/A'}")
                
                # Check for error status codes or error in body
                if status_code >= 400 or (isinstance(parsed_body, dict) and not parsed_body.get("success", True)):
                    error_msg = parsed_body.get("error") if isinstance(parsed_body, dict) else None
                    if not error_msg:
                        error_msg = f"Lambda returned status {status_code}"
                        if isinstance(parsed_body, dict):
                            error_msg = f"Lambda returned status {status_code}: {str(parsed_body)}"
                        else:
                            error_msg = f"Lambda returned status {status_code}: {body_content[:200]}"
                    
                    print(f"[PDF_HUB] Returning error: {error_msg}")
                    logger.error(f"Lambda returned error (status {status_code}): {error_msg}")
                    return {"success": False, "error": error_msg}
                
                print(f"[PDF_HUB] Lambda response successful")
                return parsed_body
            except json.JSONDecodeError as e:
                print(f"[PDF_HUB] JSON decode error: {str(e)}")
                logger.error(f"Error parsing Lambda response body: {str(e)}, statusCode: {status_code}, body: {body_content[:200]}")
                # If status code indicates error, return that
                if status_code >= 400:
                    error_msg = f"Lambda error (status {status_code}): {body_content[:200]}"
                    print(f"[PDF_HUB] Returning status code error: {error_msg}")
                    return {"success": False, "error": error_msg}
                # statusCode 200 with non-JSON body = binary PDF (API Gateway binary response)
                if status_code == 200 and body_content:
                    headers = out.get("headers") or {}
                    content_disp = headers.get("Content-Disposition") or ""
                    filename = None
                    if "filename=" in content_disp:
                        m = re.search(r'filename=["\']?([^"\']+)["\']?', content_disp)
                        if m:
                            filename = m.group(1).strip()
                    print(f"[PDF_HUB] Lambda binary PDF response (status 200), filename={filename}")
                    return {
                        "success": True,
                        "pdf_base64": body_content,
                        "filename": filename,
                    }
                return {"success": False, "error": f"Invalid JSON in Lambda response body: {str(e)}"}
        
        # Direct response format (not API Gateway proxy)
        if isinstance(out, dict):
            if not out.get("success", True):
                error_msg = out.get("error", "Unknown error in Lambda response")
                print(f"[PDF_HUB] Direct response error: {error_msg}")
                return {"success": False, "error": error_msg}
            print(f"[PDF_HUB] Direct response successful")
            return out
        
        print(f"[PDF_HUB] Unexpected response format: {type(out)}")
        return {"success": False, "error": "Unexpected Lambda response format"}
    except json.JSONDecodeError as e:
        print(f"[PDF_HUB] JSON decode error on raw response: {str(e)}")
        logger.error(f"Error parsing Lambda response: {str(e)}, raw: {raw[:200] if raw else 'None'}")
        return {"success": False, "error": f"Invalid JSON response from Lambda: {str(e)}"}
    except Exception as e:
        print(f"[PDF_HUB] Unexpected error processing response: {str(e)}")
        logger.error(f"Error processing Lambda response: {str(e)}", exc_info=True)
        return {"success": False, "error": f"Error processing Lambda response: {str(e)}"}


def generate_pdf_via_lambda(
    data: Dict[str, Any],
    export_type: str = "reports",
    default_filename_prefix: str = "report"
) -> Dict[str, Any]:
    """
    Hub function to generate PDF via Lambda.
    Routes to appropriate export function based on export_type.
    
    Args:
        data: The data to be used for PDF generation
        export_type: Type of export ("reports" or "gri")
        default_filename_prefix: Prefix for filename if Lambda doesn't provide one
    
    Returns:
        API Gateway binary proxy response format with PDF as base64-encoded body
    
    Raises:
        APIException: If PDF generation fails
    """
    from ...exceptions import APIException
    
    # Invoke Lambda with data and export_type
    print(f"[PDF_HUB] generate_pdf_via_lambda called with export_type: {export_type}")
    lambda_result = _invoke_pdf_lambda(data, export_type)
    
    print(f"[PDF_HUB] Lambda result keys: {list(lambda_result.keys()) if isinstance(lambda_result, dict) else type(lambda_result)}")
    print(f"[PDF_HUB] Lambda result success: {lambda_result.get('success') if isinstance(lambda_result, dict) else 'N/A'}")
    print(f"[PDF_HUB] Lambda result error: {lambda_result.get('error') if isinstance(lambda_result, dict) else 'N/A'}")
    
    if not lambda_result.get('success'):
        error_msg = lambda_result.get('error')
        if not error_msg:
            # Try to extract error from different possible keys
            error_msg = (
                lambda_result.get('errorMessage') or 
                lambda_result.get('message') or 
                str(lambda_result) if lambda_result else 'Unknown error'
            )
        print(f"[PDF_HUB] Raising APIException with error: {error_msg}")
        raise APIException(
            f"PDF Lambda error: {error_msg}",
            status_code=500,
            error_code="PDF_ERROR"
        )
    
    pdf_b64 = lambda_result.get('pdf_base64')
    filename = lambda_result.get('filename')
    
    # Generate default filename if Lambda didn't provide one
    if not filename:
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"{default_filename_prefix}_{timestamp}.pdf"
    
    # Return as downloadable PDF (API Gateway binary proxy response)
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/pdf",
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
        "isBase64Encoded": True,
        "body": pdf_b64 or ""
    }


def upload_pdf_to_s3(
    pdf_base64: str,
    filename: str,
    organization_id: int,
    file_type: str = "gri_report",
    db_session: Optional[Any] = None,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Upload a PDF file to S3 and optionally create a file record in the database.
    
    Args:
        pdf_base64: Base64-encoded PDF content
        filename: Original filename for the PDF
        organization_id: Organization ID for S3 path structure
        file_type: Type of file (default: "gri_report")
        db_session: Optional database session for creating file records
        user_id: Optional user ID for audit trail
    
    Returns:
        Dict with S3 URL, S3 key, and file metadata
    
    Raises:
        APIException: If upload fails
    """
    from ...exceptions import APIException
    
    try:
        # Decode base64 PDF to bytes
        pdf_bytes = base64.b64decode(pdf_base64)
        
        # Initialize S3 client
        aws_region = os.getenv('AWS_REGION', 'ap-southeast-1')
        bucket_name = os.getenv('S3_BUCKET_NAME', 'prod-gepp-platform-assets')
        
        # Use path-style addressing if bucket name contains dots
        s3_config = boto3.session.Config(
            signature_version='s3v4',
            s3={'addressing_style': 'path'} if '.' in bucket_name else {}
        )
        s3_client = boto3.client('s3', region_name=aws_region, config=s3_config)
        
        # Generate unique S3 key
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_extension = os.path.splitext(filename)[1] or '.pdf'
        unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"
        
        # S3 key structure: org/{org_id}/reports/{file_type}/{year}/{filename}
        current_date = datetime.now()
        s3_key = f"org/{organization_id}/reports/{file_type}/{current_date.year}/{unique_filename}"
        
        # Upload to S3
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=pdf_bytes,
            ContentType='application/pdf',
            Metadata={
                'original_filename': filename,
                'organization_id': str(organization_id),
                'file_type': file_type,
                'upload_timestamp': timestamp
            }
        )
        
        # Generate S3 URL
        if '.' in bucket_name:
            # Path-style URL for buckets with dots
            if aws_region == 'us-east-1':
                s3_url = f"https://s3.amazonaws.com/{bucket_name}/{s3_key}"
            else:
                s3_url = f"https://s3.{aws_region}.amazonaws.com/{bucket_name}/{s3_key}"
        else:
            # Virtual-hosted-style URL
            if aws_region == 'us-east-1':
                s3_url = f"https://{bucket_name}.s3.amazonaws.com/{s3_key}"
            else:
                s3_url = f"https://{bucket_name}.s3.{aws_region}.amazonaws.com/{s3_key}"
        
        logger.info(f"Successfully uploaded PDF to S3: {s3_key}")
        
        # Optionally create file record in database
        file_id = None
        if db_session and user_id:
            try:
                from ...models.cores.files import File, FileType, FileStatus, FileSource
                
                try:
                    file_type_enum = FileType[file_type] if isinstance(file_type, str) else file_type
                except (KeyError, AttributeError):
                    # Default to 'other' if file_type is not a valid FileType
                    file_type_enum = FileType.other if hasattr(FileType, 'other') else FileType['other']
                
                file_record = File(
                    file_type=file_type_enum,
                    status=FileStatus.active,
                    url=s3_url,
                    s3_key=s3_key,
                    s3_bucket=bucket_name,
                    original_filename=filename,
                    mime_type='application/pdf',
                    organization_id=organization_id,
                    uploader_id=user_id,
                    source=FileSource.s3,
                    file_metadata={
                        'upload_timestamp': timestamp,
                        'file_type': file_type
                    }
                )
                db_session.add(file_record)
                db_session.flush()
                file_id = file_record.id
                db_session.commit()
                logger.info(f"Created file record in database: {file_id}")
            except Exception as db_error:
                logger.warning(f"Failed to create file record in database: {str(db_error)}")
                if db_session:
                    db_session.rollback()
                # Continue without failing - file is still uploaded to S3
        
        return {
            'success': True,
            's3_url': s3_url,
            's3_key': s3_key,
            'filename': filename,
            'file_id': file_id,
            'file_size': len(pdf_bytes)
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = f"AWS S3 error ({error_code}): {str(e)}"
        logger.error(error_msg)
        raise APIException(error_msg, status_code=500, error_code="S3_UPLOAD_ERROR")
    except Exception as e:
        error_msg = f"Error uploading PDF to S3: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise APIException(error_msg, status_code=500, error_code="S3_UPLOAD_ERROR")


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    Lambda handler function that routes to the appropriate PDF export function.
    This is the entry point called by the Lambda function.
    
    Expected event structure (direct invocation):
    {
        "data": {...},  # Data for PDF generation
        "export_type": "reports" | "gri"  # Type of export
    }
    
    Or (API Gateway format):
    {
        "body": "{\"data\": {...}, \"export_type\": \"reports\"}"
    }
    
    Returns:
        API Gateway proxy response format with PDF as base64-encoded body
    """
    try:
        print(f"[LAMBDA_HANDLER] Event received. Keys: {list(event.keys()) if isinstance(event, dict) else type(event)}")
        print(f"[LAMBDA_HANDLER] Event (first 1000 chars): {str(event)[:1000]}")
        
        # Handle API Gateway format (body is JSON string)
        if 'body' in event and isinstance(event.get('body'), str):
            print(f"[LAMBDA_HANDLER] Found 'body' key, parsing JSON...")
            try:
                event = json.loads(event['body'])
                print(f"[LAMBDA_HANDLER] Parsed body. New event keys: {list(event.keys()) if isinstance(event, dict) else type(event)}")
            except json.JSONDecodeError as e:
                print(f"[LAMBDA_HANDLER] JSON decode error: {str(e)}")
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "success": False,
                        "error": f"Invalid JSON in event body: {str(e)}"
                    })
                }
        
        # Extract data and export_type from event
        data = event.get('data', {})
        export_type = event.get('export_type', 'reports')
        
        print(f"[LAMBDA_HANDLER] Extracted data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        print(f"[LAMBDA_HANDLER] Extracted export_type: {export_type}")
        
        if not data:
            print(f"[LAMBDA_HANDLER] No data found in event")
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "success": False,
                    "error": "Missing 'data' in event"
                })
            }
        
        logger.info(f"Lambda handler called with export_type: {export_type}")
        print(f"[LAMBDA_HANDLER] Starting PDF generation for export_type: {export_type}")
        
        # Route to appropriate PDF generator based on export_type
        if export_type == "gri":
            print(f"[LAMBDA_HANDLER] GRI export type detected")
            try:
                # Import GRI PDF generator directly from module file (bypasses __init__.py to avoid SQLAlchemy dependency)
                import importlib.util
                gri_pdf_path = os.path.join(os.path.dirname(__file__), 'gri', 'gri_pdf_generator.py')
                
                print(f"[LAMBDA_HANDLER] GRI PDF path: {gri_pdf_path}")
                print(f"[LAMBDA_HANDLER] GRI PDF path exists: {os.path.exists(gri_pdf_path)}")
                
                if not os.path.exists(gri_pdf_path):
                    raise FileNotFoundError(f"GRI PDF generator not found at: {gri_pdf_path}")
                
                spec = importlib.util.spec_from_file_location("gri_pdf_generator", gri_pdf_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Failed to create module spec for: {gri_pdf_path}")
                
                print(f"[LAMBDA_HANDLER] Module spec created successfully")
                gri_pdf_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(gri_pdf_module)
                print(f"[LAMBDA_HANDLER] Module loaded successfully")
                
                if not hasattr(gri_pdf_module, 'generate_pdf_bytes'):
                    raise AttributeError("gri_pdf_generator module does not have 'generate_pdf_bytes' function")
                
                print(f"[LAMBDA_HANDLER] generate_pdf_bytes function found")
                gri_generate_pdf_bytes = gri_pdf_module.generate_pdf_bytes
                
                # Generate PDF bytes with detailed error handling
                logger.info(f"Generating GRI PDF with data keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
                print(f"[LAMBDA_HANDLER] Calling generate_pdf_bytes with data keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
                try:
                    pdf_bytes = gri_generate_pdf_bytes(data)
                    print(f"[LAMBDA_HANDLER] PDF generated successfully, size: {len(pdf_bytes) if pdf_bytes else 0} bytes")
                except Exception as pdf_error:
                    error_details = f"GRI PDF generation failed: {type(pdf_error).__name__}: {str(pdf_error)}"
                    print(f"[LAMBDA_HANDLER] PDF generation error: {error_details}")
                    import traceback
                    print(f"[LAMBDA_HANDLER] PDF generation traceback: {traceback.format_exc()}")
                    logger.error(error_details, exc_info=True)
                    raise Exception(error_details) from pdf_error
                
                if not pdf_bytes:
                    raise ValueError("GRI PDF generation returned None")
                if not isinstance(pdf_bytes, bytes):
                    raise ValueError(f"GRI PDF generation returned wrong type: {type(pdf_bytes)}, expected bytes")
                if len(pdf_bytes) == 0:
                    raise ValueError("GRI PDF generation returned empty bytes")
                
                # Generate filename
                year = data.get('year') or data.get('data', {}).get('year') or ""
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                filename = f"gri_report_{year}_{timestamp}.pdf" if year else f"gri_report_{timestamp}.pdf"
                print(f"[LAMBDA_HANDLER] Filename generated: {filename}")
                print(f"[LAMBDA_HANDLER] Exiting GRI try block, continuing to base64 encoding...")
                
            except FileNotFoundError as e:
                error_msg = f"GRI PDF generator file not found: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return {
                    "statusCode": 500,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "success": False,
                        "error": error_msg,
                        "error_type": "FileNotFoundError"
                    })
                }
            except ImportError as e:
                error_msg = f"GRI PDF generator import failed: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return {
                    "statusCode": 500,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "success": False,
                        "error": error_msg,
                        "error_type": "ImportError"
                    })
                }
            except AttributeError as e:
                error_msg = f"GRI PDF generator missing function: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return {
                    "statusCode": 500,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "success": False,
                        "error": error_msg,
                        "error_type": "AttributeError"
                    })
                }
            except Exception as e:
                error_type = type(e).__name__
                error_msg = f"Error generating GRI PDF ({error_type}): {str(e)}"
                logger.error(error_msg, exc_info=True)
                import traceback
                tb_str = traceback.format_exc()
                logger.error(f"Full traceback: {tb_str}")
                return {
                    "statusCode": 500,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "success": False,
                        "error": error_msg,
                        "error_type": error_type,
                        "traceback": tb_str[-500:] if len(tb_str) > 500 else tb_str  # Last 500 chars of traceback
                    })
                }
            
        elif export_type == "reports":
            try:
                # Import reports PDF generator directly from module file (bypasses __init__.py to avoid SQLAlchemy dependency)
                import importlib.util
                reports_pdf_path = os.path.join(os.path.dirname(__file__), 'reports', 'pdf_export.py')
                
                if not os.path.exists(reports_pdf_path):
                    raise FileNotFoundError(f"Reports PDF generator not found at: {reports_pdf_path}")
                
                spec = importlib.util.spec_from_file_location("pdf_export", reports_pdf_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Failed to create module spec for: {reports_pdf_path}")
                
                reports_pdf_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(reports_pdf_module)
                
                if not hasattr(reports_pdf_module, 'generate_pdf_bytes'):
                    raise AttributeError("pdf_export module does not have 'generate_pdf_bytes' function")
                
                reports_generate_pdf_bytes = reports_pdf_module.generate_pdf_bytes
                
                # Generate PDF bytes
                logger.info("Generating reports PDF...")
                pdf_bytes = reports_generate_pdf_bytes(data)
                
                if not pdf_bytes or len(pdf_bytes) == 0:
                    raise ValueError("Reports PDF generation returned empty bytes")
                
                # Generate filename
                date_from = data.get('date_from', '')
                date_to = data.get('date_to', '')
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                if date_from and date_to:
                    filename = f"report_{timestamp}.pdf"
                else:
                    filename = f"report_{timestamp}.pdf"
                    
            except Exception as e:
                error_msg = f"Error generating reports PDF: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return {
                    "statusCode": 500,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "success": False,
                        "error": error_msg
                    })
                }
        else:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "success": False,
                    "error": f"Unknown export_type: {export_type}. Supported types: 'reports', 'gri'"
                })
            }
        
        # Convert PDF bytes to base64
        print(f"[LAMBDA_HANDLER] Starting base64 encoding, PDF size: {len(pdf_bytes)} bytes")
        try:
            pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
            print(f"[LAMBDA_HANDLER] Base64 encoding successful, length: {len(pdf_b64)} chars")
        except Exception as b64_error:
            error_msg = f"Base64 encoding failed: {type(b64_error).__name__}: {str(b64_error)}"
            print(f"[LAMBDA_HANDLER] {error_msg}")
            logger.error(error_msg, exc_info=True)
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "success": False,
                    "error": error_msg,
                    "error_type": type(b64_error).__name__
                })
            }
        
        logger.info(f"Successfully generated PDF: {filename}, size: {len(pdf_bytes)} bytes")
        print(f"[LAMBDA_HANDLER] Creating response JSON...")
        
        # Return API Gateway proxy response format
        try:
            response_body = {
                "success": True,
                "pdf_base64": pdf_b64,
                "filename": filename,
                "file_size": len(pdf_bytes)
            }
            print(f"[LAMBDA_HANDLER] Response body created, keys: {list(response_body.keys())}")
            print(f"[LAMBDA_HANDLER] PDF base64 length in response: {len(response_body['pdf_base64'])}")
            
            response_json = json.dumps(response_body)
            print(f"[LAMBDA_HANDLER] Response JSON created, length: {len(response_json)} chars")
            
            response = {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": response_json
            }
            print(f"[LAMBDA_HANDLER] Response object created, returning...")
            return response
        except Exception as json_error:
            error_msg = f"JSON serialization failed: {type(json_error).__name__}: {str(json_error)}"
            print(f"[LAMBDA_HANDLER] {error_msg}")
            logger.error(error_msg, exc_info=True)
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "success": False,
                    "error": error_msg,
                    "error_type": type(json_error).__name__
                })
            }
        
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        import traceback
        tb_str = traceback.format_exc()
        
        print(f"[LAMBDA_HANDLER] Exception caught: {error_type}")
        print(f"[LAMBDA_HANDLER] Error message: {error_msg}")
        print(f"[LAMBDA_HANDLER] Traceback: {tb_str}")
        
        logger.error(f"Error in Lambda handler: {error_msg}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "success": False,
                "error": f"PDF generation failed ({error_type}): {error_msg}",
                "error_type": error_type,
                "traceback": tb_str[-1000:] if len(tb_str) > 1000 else tb_str
            })
        }

