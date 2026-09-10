from __future__ import annotations

import logging
import re
from typing import Any


_TOKEN_QUERY = re.compile(r"(?i)([?&]token=)[^&\s\"']+")


def _redact_query_tokens(value: Any) -> Any:
    if isinstance(value, str):
        return _TOKEN_QUERY.sub(r"\1[REDACTED]", value)
    return value


class SensitiveQueryRedactionFilter(logging.Filter):
    """Remove bearer tokens embedded in request/WebSocket query strings."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_query_tokens(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_query_tokens(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                key: _redact_query_tokens(value)
                for key, value in record.args.items()
            }
        return True


def install_sensitive_query_redaction() -> None:
    for logger_name in ("uvicorn.error", "uvicorn.access"):
        target = logging.getLogger(logger_name)
        if not any(isinstance(item, SensitiveQueryRedactionFilter) for item in target.filters):
            target.addFilter(SensitiveQueryRedactionFilter())
