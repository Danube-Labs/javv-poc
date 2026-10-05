"""OpenSearch's `javv` role (issue 729): what the backend's OpenSearch user may do.

The role lives in the compose file's `configs` and, for a cluster someone runs, in
`docs/DEPLOYING.md`. `development/scripts/opensearch-role-walk.sh` is its proof: CI's compose job
calls every surface that reaches OpenSearch as `javv`, then checks what the role refuses. A role
changed here without that walk passing is not proven, so these tests hold the role to the one the
walk proved, and to what it must never grant.
"""

import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "compose" / "compose.yaml"
DEPLOYING = ROOT / "docs" / "DEPLOYING.md"
INDEX_MAP = ROOT / "docs" / "engineering" / "INDEX-MAP.md"

# the role the walk proved, each permission shown needed by a run without it (issue 729)
PROVEN_CLUSTER = {
    "cluster:monitor/main",
    "cluster:monitor/health",
    "cluster:monitor/nodes/info",
    "cluster:monitor/nodes/stats",
    "cluster:monitor/state",
    "cluster:monitor/shards",
    "indices:admin/index_template/get",
    "indices:admin/index_template/put",
    "cluster:admin/snapshot/get",
    "cluster:admin/snapshot/create",
    "cluster:admin/snapshot/restore",
    "indices:data/write/bulk",
    "indices:data/read/mget",
    "indices:data/read/scroll*",
}
PROVEN_INDEX = {
    ("findings", "javv-*", "system-*"): {
        "indices:data/read/*",
        "indices:data/write/*",
        "indices:admin/create",
        "indices:admin/get",
        "indices:admin/mapping/put",
        "indices:admin/mappings/get",
        "indices:admin/aliases",
        "indices:admin/aliases/get",
        "indices:admin/refresh*",
        "indices:monitor/*",
    },
    ("javv-*", "system-audit-log*"): {"indices:admin/rollover"},
    ("javv-*",): {"indices:admin/delete"},
    ("restored-*",): {"indices:admin/create", "indices:data/write/*"},
}


def _configs() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text())["configs"]


def _role() -> dict[str, Any]:
    return yaml.safe_load(_configs()["opensearch-roles"]["content"])["javv"]


def _index_permissions(role: dict[str, Any]) -> dict[tuple[str, ...], set[str]]:
    return {
        tuple(p["index_patterns"]): set(p["allowed_actions"]) for p in role["index_permissions"]
    }


def test_the_role_is_the_one_the_walk_proved() -> None:
    role = _role()
    assert set(role["cluster_permissions"]) == PROVEN_CLUSTER
    assert _index_permissions(role) == PROVEN_INDEX


def test_the_role_leaves_out_security_settings_repositories_and_other_indices() -> None:
    role = _role()
    granted = set(role["cluster_permissions"]) | {
        a for actions in _index_permissions(role).values() for a in actions
    }
    for action in granted:
        assert action not in {"*", "indices:*", "cluster:*", "cluster_all", "indices_all"}
        assert not action.startswith(("cluster:admin/opendistro", "cluster:admin/security")), action
        assert not action.startswith("restapi:"), action
        assert not action.startswith("cluster:admin/settings"), action
        assert not action.startswith("cluster:admin/repository"), action
        assert action != "cluster:admin/snapshot/delete", action
    patterns = {p for group in _index_permissions(role) for p in group}
    assert patterns <= {"findings", "javv-*", "system-*", "system-audit-log*", "restored-*"}
    # deletes and rollovers only where the lifecycle job makes them (jobs/lifecycle.py)
    for group, actions in _index_permissions(role).items():
        if "indices:admin/delete" in actions:
            assert group == ("javv-*",)
        if "indices:admin/rollover" in actions:
            assert set(group) <= {"javv-*", "system-audit-log*"}
    # a restore writes its copies; nothing in JAVV reads them
    assert not any(a.startswith("indices:data/read") for a in PROVEN_INDEX[("restored-*",)])


def test_the_mapping_keeps_admin_on_all_access_and_javv_on_javv() -> None:
    """The mounted mapping replaces the image's, which is where admin gets all_access."""
    mapping = yaml.safe_load(_configs()["opensearch-roles-mapping"]["content"])
    assert mapping["all_access"]["backend_roles"] == ["admin"]
    assert mapping["javv"]["users"] == ["javv"]
    assert set(mapping) == {"_meta", "all_access", "javv"}


def test_deploying_gives_the_same_role() -> None:
    section = DEPLOYING.read_text().split("## An OpenSearch of your own\n", 1)[1]
    section = section.split("\n## ", 1)[0]
    block = re.search(r"```json\n(.+?)\n```", section, re.S)
    assert block, "DEPLOYING gives the role as JSON"
    documented = json.loads(block[1])
    role = _role()
    assert documented == {
        k: role[k] for k in ("description", "cluster_permissions", "index_permissions")
    }


def test_every_index_in_the_index_map_is_in_the_role() -> None:
    """A new index outside the role's patterns would be refused on every secured install."""
    rows = re.findall(r"^\| `([^`]+)`", INDEX_MAP.read_text().split("## Summary", 1)[1], re.M)
    names = {re.sub(r"<[^>]+>", "x", row).replace("*", "x") for row in rows}
    assert "findings" in names and "restored-x" in names
    patterns = [p for group in PROVEN_INDEX for p in group]
    for name in names:
        assert any(name == p or (p.endswith("*") and name.startswith(p[:-1])) for p in patterns), (
            name
        )
