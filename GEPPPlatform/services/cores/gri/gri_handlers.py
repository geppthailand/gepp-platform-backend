"""
GRI API Handlers
"""

from typing import Dict, Any, List, Optional
import logging
import json
from datetime import datetime

from .gri_service import GriService
from ....exceptions import (
    APIException,
    BadRequestException
)

logger = logging.getLogger(__name__)

def handle_gri_routes(event: Dict[str, Any], **params) -> Dict[str, Any]:
    """
    Main handler for GRI routes
    """
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')
    query_params = params.get('query_params', {})
    path_params = params.get('path_params', {})
    
    # Safely get body, ensuring it's not None
    body_raw = event.get("body")
    body_data = {}

    if method == 'POST':
        try:
            body_data = json.loads(body_raw) if body_raw else {}
        except Exception:
            raise BadRequestException("Invalid JSON body")
        
        if body_data is None:
            body_data = {}

    # Get database session
    db_session = params.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    gri_service = GriService(db_session)

    # Extract user info
    current_user = params.get('current_user', {})
    organization_id = current_user.get('organization_id')
    user_id = current_user.get('user_id')

    if not organization_id:
        raise BadRequestException("Organization ID is required")

    # --- GET Routes ---
    if method == 'GET':
        record_year = query_params.get('year')

        # GET /api/gri/306-1
        if '/api/gri/306-1' in path:
            result = gri_service.get_gri306_1_records(organization_id, record_year)
            return {"data": result}
            
        # GET /api/gri/306-2
        if '/api/gri/306-2' in path:
            # Parse record_id from query params (comma-separated string like "20,6")
            record_id_param = query_params.get('record_ids')
            approached_ids = None
            if record_id_param:
                try:
                    approached_ids = [int(id.strip()) for id in record_id_param.split(',') if id.strip().isdigit()]
                except (ValueError, AttributeError):
                    raise BadRequestException("Invalid record_id format. Expected comma-separated integers (e.g., '20,6')")
            
            result = gri_service.get_gri306_2_records(organization_id, record_year, approached_ids)
            return {"data": result}

        # GET /api/gri/versions - Get all export versions
        if '/api/gri/versions' in path or '/api/gri/export/versions' in path:
            from ....models.gri.gri_306 import Gri306Export
            from ....models.users.user_location import UserLocation
            
            # Get year filter from query params
            filter_year = query_params.get('year')
            
            # Query all exports for this organization with a join to get creator info
            query = db_session.query(
                Gri306Export,
                UserLocation.display_name,
                UserLocation.name_en,
                UserLocation.name_th
            ).outerjoin(
                UserLocation, Gri306Export.created_by == UserLocation.id
            ).filter(
                Gri306Export.organization == organization_id,
                Gri306Export.is_active == True
            )
            
            # Filter by year if provided
            if filter_year:
                query = query.filter(Gri306Export.record_year == str(filter_year))
            
            query = query.order_by(Gri306Export.created_date.desc())
            
            results = query.all()
            
            # Build response with version, created_date, and creator name
            versions = []
            for export, display_name, name_en, name_th in results:
                # Prefer display_name, fallback to name_en or name_th
                creator_name = display_name or name_en or name_th
                
                versions.append({
                    "version": export.version,
                    "created_date": export.created_date.isoformat() if export.created_date else None,
                    "created_by_name": creator_name,
                    "record_year": export.record_year,
                    "export_file_url": export.export_file_url
                })
            
            return {"data": versions}
        
        # GET /api/gri/306-3
        if '/api/gri/306-3' in path:
            result = gri_service.get_gri306_3_records(organization_id, record_year)
            return {"data": result}


    # --- POST Routes ---
    if method == 'POST':
        # POST /api/gri/306-1
        if '/api/gri/306-1' in path:
            if not user_id:
                raise BadRequestException("User ID is required for creation")
                
            global_year = body_data.get('year', '')
            records_to_process = body_data.get('records', [])
            delete_records = body_data.get('deleted_ids', []) 
            affected_id = body_data.get('affected_ids', [])
                
            if not isinstance(records_to_process, list):
                 raise BadRequestException("Records must be an array")
                 
            result = gri_service.create_gri306_1_records(
                organization_id, 
                user_id, 
                records_to_process,
                delete_records, 
                affected_id,
                str(global_year) if global_year else None
            )
            return {"data": result, "message": "Records processed successfully"}

        # POST /api/gri/306-2
        if '/api/gri/306-2' in path:
            if not user_id:
                raise BadRequestException("User ID is required for creation")
                
            global_year = body_data.get('year', '')
            records_to_process = body_data.get('records', [])
            delete_records = body_data.get('deleted_ids', [])
            
            if not isinstance(records_to_process, list):
                 raise BadRequestException("Records must be an array")
                 
            result = gri_service.create_gri306_2_records(
                organization_id,
                user_id,
                records_to_process,
                delete_records,
                str(global_year) if global_year else None
            )
            return {"data": result, "message": "GRI 306-2 Records processed successfully"}

        # POST /api/gri/306-3
        if '/api/gri/306-3' in path:
            if not user_id:
                raise BadRequestException("User ID is required for creation")
                
            global_year = body_data.get('year', '')
            records_to_process = body_data.get('records', [])
            delete_records = body_data.get('deleted_ids', [])
            
            if not isinstance(records_to_process, list):
                 raise BadRequestException("Records must be an array")
                 
            result = gri_service.create_gri306_3_records(
                organization_id,
                user_id,
                records_to_process,
                delete_records,
                str(global_year) if global_year else None
            )
            return {"data": result, "message": "GRI 306-3 Records processed successfully"}

        # POST /api/gri/export
        if '/api/gri/export' in path:
            if not user_id:
                raise BadRequestException("User ID is required for export")
            
            version_name = body_data.get('version_name')
            record_year = body_data.get('year')
            
            if not record_year:
                raise BadRequestException("Year is required for export")
            
            # Calculate and get all GRI 306-1, 306-2, and 306-3 data with calculations
            result = gri_service.calculate_gri_export_data(organization_id, record_year)
            
            # Generate PDF via Lambda hub (routes to GRI export function)
            from ..pdf_export_hub import generate_pdf_via_lambda, upload_pdf_to_s3
            from ....models.gri.gri_306 import Gri306Export
            
            year_str = record_year or ""
            default_filename = f"gri_report_{year_str}" if year_str else "gri_report"
            
            # Generate PDF and get the response (same format as reports)
            pdf_response = generate_pdf_via_lambda(result, export_type="gri", default_filename_prefix=default_filename)
            
            # Extract PDF base64 and filename from response for S3 upload and DB save
            pdf_b64 = pdf_response.get('body', '')
            content_disposition = pdf_response.get('headers', {}).get('Content-Disposition', '')
            if 'filename="' in content_disposition:
                filename = content_disposition.split('filename="')[1].split('"')[0]
            else:
                filename = f"{default_filename}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            # Upload PDF to S3
            upload_result = upload_pdf_to_s3(
                pdf_base64=pdf_b64,
                filename=filename,
                organization_id=organization_id,
                file_type="gri_report",
                db_session=db_session,
                user_id=user_id
            )
            
            s3_url = upload_result['s3_url']
            
            # Save export record to gri306_export table
            try:
                export_record = Gri306Export(
                    version=version_name if version_name else None,  # Store version_name as string
                    export_file_url=s3_url,
                    record_year=str(record_year),
                    organization=organization_id,
                    created_by=user_id
                )
                db_session.add(export_record)
                db_session.commit()
                
                logger.info(f"Saved GRI export record: version_name={version_name}, URL: {s3_url}")
            except Exception as e:
                logger.error(f"Error saving GRI export record: {str(e)}", exc_info=True)
                db_session.rollback()
                # Continue without failing - PDF is still uploaded and will be returned
            
            # Return PDF blob (same format as reports)
            return pdf_response

        # POST /api/gri/versions
        if '/api/gri/versions' in path:
            version_name = body_data.get('version_name')
            record_year = body_data.get('year')
            
            if not record_year:
                raise BadRequestException("Year is required for export")
                
            result = gri_service.get_gri_export_data(
                organization_id, 
                str(record_year), 
                version_name
            )
            return {"data": result, "message": "GRI Report data generated successfully"}

    raise APIException(f"Route not found: {method} {path}", 404)
