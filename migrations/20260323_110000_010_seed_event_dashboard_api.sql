-- Seed Event Dashboard V1 custom API and enable for organization_id=2596
-- Migration: 20260323_110000_010_seed_event_dashboard_api

-- Insert custom API definition
INSERT INTO custom_apis (name, description, service_path, root_fn_name, is_active, created_date)
VALUES (
    'Event Dashboard V1',
    'Event dashboard API providing waste statistics and org structure extraction',
    'event-dashboard-v1',
    'event_dashboard_v1',
    true,
    NOW()
)
ON CONFLICT DO NOTHING;

-- Enable for organization_id=2596
INSERT INTO organization_custom_apis (organization_id, custom_api_id, enable, api_call_quota, api_call_used, process_quota, process_used, created_date)
SELECT 2596, id, true, 100000, 0, 100000, 0, NOW()
FROM custom_apis
WHERE service_path = 'event-dashboard-v1'
  AND NOT EXISTS (
    SELECT 1 FROM organization_custom_apis
    WHERE organization_id = 2596
      AND custom_api_id = (SELECT id FROM custom_apis WHERE service_path = 'event-dashboard-v1')
);
