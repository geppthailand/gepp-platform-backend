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
from .iot_hardwares import IoTHardware
from .device_health import DeviceHealth
from .device_events import DeviceEvent
from .device_commands import DeviceCommand
from .device_health_history import DeviceHealthHistory
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
    'IoTDevice', 'IoTHardware',
    'DeviceHealth', 'DeviceEvent', 'DeviceCommand', 'DeviceHealthHistory',

    # Permissions
    'Permission', 'PermissionType',

    # Roles
    'SystemRole', 'SystemPermission',

    # Translations
    'Translation',

    # Files
    'File', 'FileType', 'FileStatus', 'FileSource'
]