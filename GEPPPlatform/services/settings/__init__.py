"""Platform-wide settings (see `global_settings`)."""

from .global_settings import (  # noqa: F401
    REGISTRY,
    SUBSCRIPTION_DISABLE_WHEN_NOT_IN_PERIOD,
    describe,
    get_all,
    get_setting,
    invalidate_cache,
    set_many,
    set_setting,
    subscription_gate_enabled,
)
