"""Redact opaque session state at the final record boundary without changing live messages."""
import copy
from zhipu_adapter import log_snapshot


def prepare_record(record, credential=""):
    def scrub(value):
        if isinstance(value, str):
            return value.replace(credential, "[REDACTED]") if credential else value
        if isinstance(value, dict):
            if value.get("type") == "provider_reasoning":
                return log_snapshot(value) if "text" in value else copy.deepcopy(value)
            return {key: scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return copy.deepcopy(value)

    return scrub(record)
