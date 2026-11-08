"""Redacted JSON logging (API-112).

Rules:
- Log events, not payloads. Request bodies, query strings, headers and
  exception messages are never logged.
- Every record carries the request id (from the middleware) when one exists.
- A last-line redaction filter masks anything that looks like a phone number,
  an email address or a bearer/API token in the message and extra fields, in
  case a future log call slips one through.

This lives in the auth package for now because of file ownership during the
parallel build; it can move to an `observability` module later.
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import datetime, timezone

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

# Phone-like: optional +, then 7+ digits allowing spaces, dots, dashes, parens.
_PHONE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TOKEN = re.compile(r"(?i)(bearer\s+|token=|key=|secret=)[^\s&\"']+")
# UUIDs are pseudonymous record ids and are useful in logs; keep them.
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

# Standard LogRecord attributes; anything else on a record is an "extra".
_STD = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}

# Extra keys that may be logged verbatim (all non-personal by construction).
_ALLOWED_EXTRA = {
    "request_id", "method", "route", "status", "duration_ms", "user_id",
    "session_id", "exc_type", "event", "reason", "limit", "auth_method",
    "org_id", "count",
}


def redact(text: str) -> str:
    uuids: list[str] = []

    def _stash(m: re.Match) -> str:
        uuids.append(m.group(0))
        return f"\x00{len(uuids) - 1}\x00"

    out = _UUID.sub(_stash, text)
    out = _TOKEN.sub(lambda m: m.group(1) + "[redacted]", out)
    out = _EMAIL.sub("[email]", out)
    out = _PHONE.sub("[phone]", out)
    return re.sub(r"\x00(\d+)\x00", lambda m: uuids[int(m.group(1))], out)


class RedactingFilter(logging.Filter):
    """Masks personal-looking data and drops non-allow-listed extras."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # bad format args: keep the template only
            msg = str(record.msg)
        record.msg = redact(msg)
        record.args = None
        for key in list(vars(record)):
            if key in _STD:
                continue
            if key not in _ALLOWED_EXTRA:
                delattr(record, key)
            else:
                val = getattr(record, key)
                if isinstance(val, str):
                    setattr(record, key, redact(val))
        if not getattr(record, "request_id", ""):
            record.request_id = request_id_var.get()
        # Tracebacks can contain local values or SQL parameters: keep only the
        # exception type, never the message or frames' values.
        if record.exc_info:
            etype = record.exc_info[0]
            record.exc_type = etype.__name__ if etype else ""
            record.exc_info = None
            record.exc_text = None
        record.stack_info = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _ALLOWED_EXTRA:
            val = getattr(record, key, None)
            if val not in (None, ""):
                out[key] = val
        return json.dumps(out, ensure_ascii=False)


_configured = False


def build_handler(stream, json_logs: bool = True) -> logging.Handler:
    """The production handler: redaction filter + JSON formatter."""
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactingFilter())
    handler.setFormatter(
        JsonFormatter() if json_logs else logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    return handler


def configure_logging(json_logs: bool = True, level: str = "INFO") -> None:
    """Install one redacting handler on the root logger (idempotent)."""
    global _configured
    root = logging.getLogger()
    if _configured:
        return
    root.addHandler(build_handler(sys.stdout, json_logs))
    root.setLevel(level.upper())
    # Uvicorn's access log includes the raw query string (e.g. hub.verify_token
    # on the webhook handshake). Our middleware logs route templates instead.
    logging.getLogger("uvicorn.access").disabled = True
    # httpx logs full URLs at INFO (OIDC calls); keep only warnings.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    _configured = True
