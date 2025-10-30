#!/usr/bin/env python3
"""
Test script to validate OpenAPI specification
"""

import json
import sys
sys.path.insert(0, '/Users/tanawatgepp/Documents/Workspace/gepp-platform/backend')

from GEPPPlatform.docs.swagger.aggregator import get_full_swagger_spec

# Generate the spec
print("Generating OpenAPI specification...")
spec = get_full_swagger_spec('dev')

# Check for required fields
print("\n" + "="*60)
print("OpenAPI Specification Validation")
print("="*60)

# Check openapi version
if 'openapi' in spec:
    print(f"✓ openapi field found: {spec['openapi']}")
else:
    print("✗ ERROR: 'openapi' field is missing!")

# Check info
if 'info' in spec:
    print(f"✓ info field found")
    print(f"  - title: {spec['info'].get('title')}")
    print(f"  - version: {spec['info'].get('version')}")
else:
    print("✗ ERROR: 'info' field is missing!")

# Check paths
if 'paths' in spec:
    path_count = len(spec['paths'])
    print(f"✓ paths field found: {path_count} paths defined")
    print(f"  Paths:")
    for path in list(spec['paths'].keys())[:10]:  # Show first 10
        print(f"    - {path}")
    if path_count > 10:
        print(f"    ... and {path_count - 10} more")
else:
    print("✗ ERROR: 'paths' field is missing!")

# Check components
if 'components' in spec:
    print(f"✓ components field found")
    if 'schemas' in spec['components']:
        schema_count = len(spec['components']['schemas'])
        print(f"  - {schema_count} schemas defined")
    if 'securitySchemes' in spec['components']:
        print(f"  - Security schemes defined")
else:
    print("✗ ERROR: 'components' field is missing!")

# Check servers
if 'servers' in spec:
    print(f"✓ servers field found: {len(spec['servers'])} servers")
else:
    print("✗ ERROR: 'servers' field is missing!")

print("\n" + "="*60)
print("Specification Structure:")
print("="*60)
print(json.dumps({k: type(v).__name__ for k, v in spec.items()}, indent=2))

print("\n" + "="*60)
print("Sample Output (first 1000 chars):")
print("="*60)
spec_json = json.dumps(spec, indent=2)
print(spec_json[:1000])
print("...")

# Save to file
output_file = '/Users/tanawatgepp/Documents/Workspace/gepp-platform/backend/openapi_test.json'
with open(output_file, 'w') as f:
    json.dump(spec, f, indent=2)
print(f"\n✓ Full spec saved to: {output_file}")
print(f"  File size: {len(spec_json):,} bytes")
