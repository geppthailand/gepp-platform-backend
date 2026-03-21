find python -type d -name "__pycache__" -exec rm -rf {} +

# Remove test directories (saves ~10-15%)
find python -type d -name "tests" -exec rm -rf {} +
find python -type d -name "test" -exec rm -rf {} +

# Remove documentation and other non-runtime files
find python -type d -name "docs" -exec rm -rf {} +
find python -type d -name "*.dist-info" -exec rm -rf {} +
find python -type d -name "*.egg-info" -exec rm -rf {} +