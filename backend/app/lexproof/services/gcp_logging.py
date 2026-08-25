"""Google Cloud logging adapter with a standard logging fallback."""
from __future__ import annotations
import logging
from ..config import LexProofSettings


def configure_google_cloud_logging(settings: LexProofSettings) -> logging.Logger:
    logger = logging.getLogger("lexproof")
    if settings.has_gcp_project():
        try:
            import google.cloud.logging
            google.cloud.logging.Client(project=settings.project_id).setup_logging()
        except ImportError:
            logger.warning("google-cloud-logging is not installed; using standard logging")
        except Exception:
            logger.exception("Google Cloud logging setup failed; using standard logging")
    return logger
