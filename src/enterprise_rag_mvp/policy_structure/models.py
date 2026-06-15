from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


StructureStatus = Literal["success", "partial", "failed"]


@dataclass
class PolicySectionNode:
    node_id: str
    doc_id: str
    parent_id: str | None
    level: int
    ordinal_label: str | None
    ordinal_value: int | None
    title: str
    normalized_title: str
    text: str
    heading_path: list[str]
    source_span: dict[str, int] | None
    element_ids: list[str]
    sort_order: int
    node_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyStructureQualityReport:
    parser_name: str
    parser_version: str
    status: StructureStatus
    node_count: int = 0
    issue_count: int = 0
    issues: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PolicyStructureDocument:
    doc_id: str
    source_name: str
    source_url: str | None
    nodes: list[PolicySectionNode]
    quality: PolicyStructureQualityReport
    metadata: dict[str, Any] = field(default_factory=dict)

    def children_of(self, parent_id: str, *, node_type: str | None = None) -> list[PolicySectionNode]:
        children = [node for node in self.nodes if node.parent_id == parent_id]
        if node_type is not None:
            children = [node for node in children if node.node_type == node_type]
        return sorted(children, key=lambda node: node.sort_order)

    def find_first(self, *, node_type: str | None = None, title: str | None = None) -> PolicySectionNode | None:
        normalized_title = _normalize_title(title) if title is not None else None
        for node in self.nodes:
            if node_type is not None and node.node_type != node_type:
                continue
            if normalized_title is not None and node.normalized_title != normalized_title:
                continue
            return node
        return None


def _normalize_title(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.replace("\xa0", " ").split()).strip(" ：:")
