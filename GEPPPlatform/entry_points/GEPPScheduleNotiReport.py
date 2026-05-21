"""Lambda entry point for scheduled report generation."""

from typing import Any, Dict

from GEPPPlatform.services.cores.reports.schedule_report import main


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Run the scheduled report job."""
    return main()

