"""Facebook-twin log emission helper.

Thin wrapper around :func:`twins_local.logs.build_log_record` that
supplies ``twin="facebook"`` and the request-scoped ``correlation_id``
from Flask's ``g`` so call sites stay terse without drifting from the
normative contract in twins-la/LOGGING.md §3.2.
"""

from typing import Optional

from twins_local.logs import build_log_record, current_correlation_id

TWIN_NAME = "facebook"


def emit(
    storage,
    *,
    tenant_id: str,
    plane: str,
    operation: str,
    resource: Optional[dict] = None,
    outcome: str = "success",
    reason: Optional[str] = None,
    details: Optional[dict] = None,
) -> dict:
    """Build a normative log record and append it to ``storage``."""
    record = build_log_record(
        twin=TWIN_NAME,
        tenant_id=tenant_id,
        correlation_id=current_correlation_id(),
        plane=plane,
        operation=operation,
        resource=resource,
        outcome=outcome,
        reason=reason,
        details=details,
    )
    storage.append_log(record)
    return record
