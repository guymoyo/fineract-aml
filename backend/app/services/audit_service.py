"""Audit logging service — records all compliance-critical actions."""

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Records administrative actions for compliance audit trail."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        user_id: str | None = None,
        username: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Create an audit log entry.

        Args:
            action: What happened (e.g. "alert_reviewed", "user_created", "config_changed")
            resource_type: Type of resource affected (e.g. "alert", "user", "config")
            resource_id: ID of the affected resource
            user_id: ID of the user who performed the action
            username: Username for display
            details: Additional context as a dict (serialized to JSON)
            ip_address: Client IP address
        """
        entry = AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            username=username,
            details=json.dumps(details, default=str) if details else None,
            ip_address=ip_address,
        )
        self.db.add(entry)
        return entry
