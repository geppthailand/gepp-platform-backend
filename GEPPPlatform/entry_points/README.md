# Lambda Entry Points

Deployment-facing handlers live here. Keep this package thin: route Lambda
events into services, but keep reusable business logic in `GEPPPlatform.services`
or shared helpers in `GEPPPlatform.libs`.

| Lambda purpose | Handler |
| --- | --- |
| Main HTTP API | `GEPPPlatform.entry_points.app.main` |
| AI audit cron | `GEPPPlatform.entry_points.audit_cron.cron_process_audits` |
| IoT health cron | `GEPPPlatform.entry_points.iot_health_cron.cron_iot_health_snapshot` |
| PDF export hub | `GEPPPlatform.entry_points.pdf_export_hub.lambda_handler` |
| Scheduled reports | `GEPPPlatform.entry_points.schedule_report.lambda_handler` |
| Legacy reports PDF export | `GEPPPlatform.entry_points.reports_pdf_export.lambda_handler` |
| CRM campaign scheduler | `GEPPPlatform.entry_points.campaign_scheduler.lambda_handler` |
| CRM profile refresher | `GEPPPlatform.entry_points.profile_refresher.lambda_handler` |

