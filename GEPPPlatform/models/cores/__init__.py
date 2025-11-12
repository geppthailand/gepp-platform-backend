"""
Core models package - Reference data and lookup tables
"""

from .locations import (
    LocationCountry, LocationRegion, LocationProvince,
    LocationDistrict, LocationSubdistrict
)
from .references import (
    Bank, Currency, Locale, Material, MainMaterial, MaterialCategory,
    MaterialTag, MaterialTagGroup,
    Nationality, PhoneNumberCountryCode
)
from .iot_devices import IoTDevice
from .permissions import Permission, PermissionType
from .translations import Translation
from .roles import SystemRole, SystemPermission
from .files import File, FileType, FileStatus, FileSource

__all__ = [
    # Locations
    'LocationCountry', 'LocationRegion', 'LocationProvince',
    'LocationDistrict', 'LocationSubdistrict',

    # References
    'Bank', 'Currency', 'Locale', 'Material', 'MainMaterial', 'MaterialCategory',
    'MaterialTag', 'MaterialTagGroup',
    'Nationality', 'PhoneNumberCountryCode',
    'IoTDevice',
    
    # Permissions
    'Permission', 'PermissionType',

    # Roles
    'SystemRole', 'SystemPermission',

    # Translations
    'Translation',

    # Files
    'File', 'FileType', 'FileStatus', 'FileSource'
]