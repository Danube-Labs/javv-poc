"""Read a setting stored in `system-config` leniently. After a rollback, the older release finds
settings a newer release saved, possibly with fields it doesn't know. Every settings model is
`extra="forbid"`, because the same models validate request bodies, so parsing the stored value
directly would 500 every read of that setting, and a broken scan scope stops every scanner.

Unknown top-level fields are dropped with one warning per setting per process (the reads are
per-request and per-scan-cycle; one line is enough to notice) and a counter bump on every such
read, so the trend stays visible after the log goes quiet. The rest goes through the strict
model unchanged, so a bad value on a known field still fails. Writes stay strict: a release
stores only the fields it knows (issue 640). Every stored-settings read goes through here; a
guard test holds that.
"""

from typing import Any

import structlog
from pydantic import BaseModel

from backend.core.metrics import STORED_SETTING_UNKNOWN_FIELDS

log = structlog.get_logger()

_warned: set[str] = set()


def parse_stored_setting[M: BaseModel](model: type[M], value: dict[str, Any], *, key: str) -> M:
    """Validate a stored setting's `value` against `model`, dropping fields `model` doesn't
    declare. `key` is the setting's `system-config` doc id: the warning names it, and the counter is
    labelled with its kind (the part before any `:<cluster_id>`)."""
    fields = model.model_fields
    dropped = sorted(name for name in value if name not in fields)
    if dropped:
        # the kind (`lifecycle`), not the doc id (`lifecycle:<cluster_id>`): bounded label values
        STORED_SETTING_UNKNOWN_FIELDS.labels(key.split(":", 1)[0]).inc()
        if key not in _warned:
            _warned.add(key)
            # field names only: a value could be anything a newer release chose to store
            log.warning("stored setting has unknown keys", setting=key, dropped=dropped)
    return model.model_validate({name: v for name, v in value.items() if name in fields})
