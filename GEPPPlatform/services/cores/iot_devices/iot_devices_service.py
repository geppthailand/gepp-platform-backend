"""
Reports Service - Business logic for reports and analytics
Handles data retrieval and processing for various reports
"""

from typing import List, Optional, Dict, Any
from GEPPPlatform.models.cores.references import Material
from GEPPPlatform.models.users.user_location_materials import UserLocationMaterial
from sqlalchemy.orm import Session
import logging


logger = logging.getLogger(__name__)


class IotDevicesService:
    """
    High-level reports service with business logic
    """

    def __init__(self, db: Session):
        self.db = db

    def get_locations_by_member(
        self,
        member_user_id: int,
        role: Optional[str] = None,
        organization_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get locations where the specified user is listed in members, optionally filtered by role.

        Intended for returning locations where the current user is a member with role like 'dataInput'.
        """
        locations = self.crud.get_locations_by_member(
            member_user_id=member_user_id,
            role=role,
            organization_id=organization_id
        )
        # Build material list per location in one query
        location_ids = [loc.id for loc in locations]
        materials_map: Dict[int, List[Dict[str, Any]]] = {loc_id: [] for loc_id in location_ids}

        if location_ids:
            rows = (
                self.db.query(
                    UserLocationMaterial.location_id,
                    Material.id,
                    Material.name_en,
                    Material.name_th
                )
                .join(Material, UserLocationMaterial.materials_id == Material.id)
                .filter(
                    UserLocationMaterial.location_id.in_(location_ids),
                    UserLocationMaterial.deleted_date.is_(None)
                )
                .all()
            )

            for location_id, material_id, name_en, name_th in rows:
                materials_map.setdefault(location_id, []).append({
                    'id': material_id,
                    'name_en': name_en,
                    'name_th': name_th,
                })

        # Reduced response: only id, display_name, materials
        result: List[Dict[str, Any]] = []
        for location in locations:
            result.append({
                'id': location.id,
                'display_name': location.display_name,
                'materials': materials_map.get(location.id, [])
            })

        return result
