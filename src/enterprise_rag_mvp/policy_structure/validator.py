from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from enterprise_rag_mvp.policy_structure.models import PolicySectionNode


def validate_policy_structure(nodes: list[PolicySectionNode]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    issues.extend(_validate_same_parent_ordinals(nodes, node_type="violation_group"))
    issues.extend(_validate_subclause_parent_prefix(nodes))
    return issues


def ordinal_continuity_for_children(children: list[PolicySectionNode]) -> dict[str, Any]:
    ordinals = [child.ordinal_value for child in children if child.ordinal_value is not None]
    sequence = [child.ordinal_label for child in children if child.ordinal_label]
    duplicate_values = sorted(value for value, count in Counter(ordinals).items() if count > 1)
    missing: list[int] = []
    if len(set(ordinals)) >= 2:
        values = sorted(set(ordinals))
        missing = [value for value in range(values[0], values[-1] + 1) if value not in set(values)]
    return {
        "ordinal_sequence": sequence,
        "ordinal_continuity_status": "complete" if not missing and not duplicate_values else "incomplete",
        "missing_ordinals": missing,
        "duplicate_ordinals": duplicate_values,
    }


def _validate_same_parent_ordinals(nodes: list[PolicySectionNode], *, node_type: str) -> list[dict[str, Any]]:
    by_parent: dict[str | None, list[PolicySectionNode]] = defaultdict(list)
    for node in nodes:
        if node.node_type == node_type and node.ordinal_value is not None:
            by_parent[node.parent_id].append(node)

    issues: list[dict[str, Any]] = []
    nodes_by_id = {node.node_id: node for node in nodes}
    for parent_id, siblings in by_parent.items():
        if not siblings:
            continue
        ordinals = [node.ordinal_value for node in siblings if node.ordinal_value is not None]
        counts = Counter(ordinals)
        parent = nodes_by_id.get(parent_id or "")
        parent_title = parent.title if parent is not None else None
        for ordinal, count in sorted(counts.items()):
            if count > 1:
                issues.append(
                    {
                        "code": "duplicate_ordinal",
                        "severity": "error",
                        "node_type": node_type,
                        "parent_id": parent_id,
                        "parent_title": parent_title,
                        "ordinal": ordinal,
                        "message": f"同一父节点下存在重复编号 {ordinal}。",
                    }
                )
        unique = sorted(counts)
        if len(unique) >= 2:
            missing = [value for value in range(unique[0], unique[-1] + 1) if value not in counts]
            if missing:
                issues.append(
                    {
                        "code": "missing_ordinal",
                        "severity": "warning",
                        "node_type": node_type,
                        "parent_id": parent_id,
                        "parent_title": parent_title,
                        "missing": missing,
                        "message": f"同一父节点下编号不连续，缺少 {missing}。",
                    }
                )
    return issues


def _validate_subclause_parent_prefix(nodes: list[PolicySectionNode]) -> list[dict[str, Any]]:
    by_id = {node.node_id: node for node in nodes}
    issues: list[dict[str, Any]] = []
    for node in nodes:
        if node.node_type != "leaf_clause" or not node.ordinal_label or "." not in node.ordinal_label:
            continue
        parent = by_id.get(node.parent_id or "")
        if parent is None or parent.ordinal_value is None:
            continue
        prefix = node.ordinal_label.split(".", 1)[0]
        if prefix != str(parent.ordinal_value):
            issues.append(
                {
                    "code": "subclause_parent_prefix_mismatch",
                    "severity": "warning",
                    "node_id": node.node_id,
                    "parent_id": parent.node_id,
                    "ordinal_label": node.ordinal_label,
                    "parent_ordinal": parent.ordinal_label,
                    "message": "子条款编号前缀和父条款组编号不一致。",
                }
            )
    return issues
