# Shared Libraries

Shared runtime helpers live here. Lambda entry modules should import reusable
logic from `libs` or `services`; they should not carry business logic directly.

Compatibility shims still exist at `GEPPPlatform.config`, `GEPPPlatform.database`,
and `GEPPPlatform.exceptions` so existing imports continue to work during the
transition.

