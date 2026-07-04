"""Shared identifier shapes (task E / Codex M2, #142). `cluster_id` flows into index names,
routing, and every tenant filter — its shape rule must be ONE definition, not four drifting
copies. This is the envelope's original rule (models/envelope.py imports it back): lowercase
alnum/hyphen, 8–64 chars, alnum first. Use `ClusterId` in pydantic models and
`validate_cluster_id` in plain-Python callers (the token CLI)."""

import re
from typing import Annotated

from pydantic import AfterValidator

CLUSTER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{7,63}$")


def validate_cluster_id(v: str) -> str:
    if not CLUSTER_ID_RE.fullmatch(v):
        raise ValueError("cluster_id must be lowercase alnum/hyphen, 8-64 chars")
    return v


ClusterId = Annotated[str, AfterValidator(validate_cluster_id)]
