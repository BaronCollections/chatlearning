from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from enterprise_rag_mvp.document_parsing import ParsedDocument, normalize_whitespace
from enterprise_rag_mvp.policy_structure.models import PolicySectionNode, PolicyStructureDocument, PolicyStructureQualityReport
from enterprise_rag_mvp.policy_structure.validator import validate_policy_structure

PARSER_NAME = "policy_structure_parser"
PARSER_VERSION = "1"

_MAJOR_HEADING_RE = re.compile(r"^([一二三四五六七八九十]{1,3}、)\s*(.+)$")
_VIOLATION_LEVEL_RE = re.compile(r"^(（([一二三四五六七八九十]{1,3})）)\s*([一二三]类违规行为)\s*$")
_GROUP_HEADING_RE = re.compile(r"^(\d{1,2})\.\s*(?!\d)(.+)$")
_SUBCLAUSE_RE = re.compile(r"^(\d{1,2}\.\d{1,2})\s*(.+)$")
_ACTION_MAPPING_RE = re.compile(r"^(\d{1,2}\.\d{1,2})\s*([一二三]类违规行为)\s*[:：]\s*(.+)$")

_VIOLATION_LEVELS = {
    "一类违规行为": "category_1",
    "二类违规行为": "category_2",
    "三类违规行为": "category_3",
}


@dataclass(frozen=True)
class _Line:
    text: str
    element_id: str
    start: int
    end: int
    index: int


def parse_policy_structure(
    parsed_document: ParsedDocument,
    *,
    doc_id: str | None = None,
    source_name: str | None = None,
    base_heading_path: list[str] | None = None,
    source_url: str | None = None,
) -> PolicyStructureDocument:
    actual_doc_id = doc_id or parsed_document.source_id
    actual_source_name = source_name or parsed_document.source_name
    actual_source_url = source_url if source_url is not None else parsed_document.source_url
    base_path = _base_heading_path(base_heading_path, actual_source_name)
    lines = _document_lines(parsed_document)
    nodes: list[PolicySectionNode] = []

    current_major: PolicySectionNode | None = None
    current_violation: PolicySectionNode | None = None
    current_group: PolicySectionNode | None = None
    current_action_group: PolicySectionNode | None = None

    for line in lines:
        text = line.text
        major_match = _MAJOR_HEADING_RE.match(text)
        if major_match:
            ordinal_label = major_match.group(1)
            title = _clean_title(major_match.group(2))
            current_major = _new_node(
                nodes,
                doc_id=actual_doc_id,
                parent_id=None,
                level=1,
                ordinal_label=ordinal_label,
                ordinal_value=_chinese_ordinal_to_int(ordinal_label.rstrip("、")),
                title=title,
                text=text,
                heading_path=[*base_path, f"{ordinal_label}{title}"],
                line=line,
                node_type="major_section",
                metadata={"is_action_section": _is_action_section(title)},
            )
            current_violation = None
            current_group = None
            current_action_group = None
            continue

        action_mapping_match = _ACTION_MAPPING_RE.match(text)
        if action_mapping_match and _is_current_action_section(current_major):
            ordinal_label = action_mapping_match.group(1)
            target_title = _clean_title(action_mapping_match.group(2))
            parent = current_action_group or current_major
            _new_node(
                nodes,
                doc_id=actual_doc_id,
                parent_id=parent.node_id if parent is not None else None,
                level=(parent.level + 1) if parent is not None else 2,
                ordinal_label=ordinal_label,
                ordinal_value=_last_numeric_part(ordinal_label),
                title=target_title,
                text=text,
                heading_path=[*_parent_heading_path(parent, base_path), f"{ordinal_label} {target_title}"],
                line=line,
                node_type="action_mapping",
                metadata={"action_target": _VIOLATION_LEVELS.get(target_title), "violation_level": _VIOLATION_LEVELS.get(target_title)},
            )
            if parent is not None:
                _extend_node(parent, line)
            current_group = None
            current_violation = current_violation if not _is_current_action_section(current_major) else None
            continue

        violation_match = _VIOLATION_LEVEL_RE.match(text)
        if violation_match and not _is_current_action_section(current_major):
            marker = violation_match.group(1)
            title = _clean_title(violation_match.group(3))
            current_violation = _new_node(
                nodes,
                doc_id=actual_doc_id,
                parent_id=current_major.node_id if current_major is not None else None,
                level=2,
                ordinal_label=marker,
                ordinal_value=_chinese_ordinal_to_int(violation_match.group(2)),
                title=title,
                text=text,
                heading_path=[*base_path, title],
                line=line,
                node_type="violation_level",
                metadata={"violation_level": _VIOLATION_LEVELS.get(title)},
            )
            current_group = None
            current_action_group = None
            continue

        subclause_match = _SUBCLAUSE_RE.match(text)
        if subclause_match and current_group is not None and not _is_current_action_section(current_major):
            ordinal_label = subclause_match.group(1)
            title = _clean_title(subclause_match.group(2))
            _new_node(
                nodes,
                doc_id=actual_doc_id,
                parent_id=current_group.node_id,
                level=current_group.level + 1,
                ordinal_label=ordinal_label,
                ordinal_value=_last_numeric_part(ordinal_label),
                title=title,
                text=text,
                heading_path=[*current_group.heading_path, f"{ordinal_label} {title}"],
                line=line,
                node_type="leaf_clause",
                metadata={"violation_level": current_group.metadata.get("violation_level")},
            )
            _extend_node(current_group, line)
            continue

        group_match = _GROUP_HEADING_RE.match(text)
        if group_match:
            ordinal_value = int(group_match.group(1))
            ordinal_label = f"{ordinal_value}."
            title = _clean_title(group_match.group(2))
            if _is_current_action_section(current_major):
                current_action_group = _new_node(
                    nodes,
                    doc_id=actual_doc_id,
                    parent_id=current_major.node_id if current_major is not None else None,
                    level=(current_major.level + 1) if current_major is not None else 2,
                    ordinal_label=ordinal_label,
                    ordinal_value=ordinal_value,
                    title=title,
                    text=text,
                    heading_path=[*_parent_heading_path(current_major, base_path), f"{ordinal_label} {title}"],
                    line=line,
                    node_type="action_group",
                    metadata={},
                )
                current_group = None
                continue
            if current_violation is not None:
                current_group = _new_node(
                    nodes,
                    doc_id=actual_doc_id,
                    parent_id=current_violation.node_id,
                    level=current_violation.level + 1,
                    ordinal_label=ordinal_label,
                    ordinal_value=ordinal_value,
                    title=title,
                    text=text,
                    heading_path=[*current_violation.heading_path, f"{ordinal_label} {title}"],
                    line=line,
                    node_type="violation_group",
                    metadata={"violation_level": current_violation.metadata.get("violation_level")},
                )
                continue

        if current_group is not None and not _is_current_action_section(current_major):
            _extend_node(current_group, line)
            continue
        if current_violation is not None and not _is_current_action_section(current_major):
            _extend_node(current_violation, line)
            continue
        if current_action_group is not None:
            _extend_node(current_action_group, line)
            continue
        if current_major is not None:
            _extend_node(current_major, line)

    issues = validate_policy_structure(nodes)
    status = "failed" if not nodes else "partial" if issues else "success"
    warnings = [issue["message"] for issue in issues if issue.get("severity") == "warning"]
    return PolicyStructureDocument(
        doc_id=actual_doc_id,
        source_name=actual_source_name,
        source_url=actual_source_url,
        nodes=nodes,
        quality=PolicyStructureQualityReport(
            parser_name=PARSER_NAME,
            parser_version=PARSER_VERSION,
            status=status,
            node_count=len(nodes),
            issue_count=len(issues),
            issues=issues,
            warnings=warnings,
        ),
        metadata={"base_heading_path": base_path},
    )


def _document_lines(parsed_document: ParsedDocument) -> list[_Line]:
    lines: list[_Line] = []
    cursor = 0
    for index, element in enumerate(parsed_document.elements):
        text = normalize_whitespace(element.text)
        if not text:
            continue
        start = cursor
        end = start + len(text)
        lines.append(_Line(text=text, element_id=element.element_id, start=start, end=end, index=index))
        cursor = end + 1
    return lines


def _new_node(
    nodes: list[PolicySectionNode],
    *,
    doc_id: str,
    parent_id: str | None,
    level: int,
    ordinal_label: str | None,
    ordinal_value: int | None,
    title: str,
    text: str,
    heading_path: list[str],
    line: _Line,
    node_type: str,
    metadata: dict[str, Any],
) -> PolicySectionNode:
    node = PolicySectionNode(
        node_id=f"{doc_id}:node-{len(nodes) + 1:04d}",
        doc_id=doc_id,
        parent_id=parent_id,
        level=level,
        ordinal_label=ordinal_label,
        ordinal_value=ordinal_value,
        title=title,
        normalized_title=_clean_title(title),
        text=normalize_whitespace(text),
        heading_path=heading_path,
        source_span={"start": line.start, "end": line.end},
        element_ids=[line.element_id],
        sort_order=line.index,
        node_type=node_type,
        metadata=dict(metadata),
    )
    nodes.append(node)
    return node


def _extend_node(node: PolicySectionNode, line: _Line) -> None:
    node.text = normalize_whitespace(f"{node.text}\n{line.text}")
    if node.source_span is None:
        node.source_span = {"start": line.start, "end": line.end}
    else:
        node.source_span = {"start": min(node.source_span["start"], line.start), "end": max(node.source_span["end"], line.end)}
    if line.element_id not in node.element_ids:
        node.element_ids.append(line.element_id)


def _base_heading_path(base_heading_path: list[str] | None, source_name: str) -> list[str]:
    if base_heading_path:
        return [_clean_title(part) for part in base_heading_path if _clean_title(part)]
    return [_clean_title(source_name)] if _clean_title(source_name) else []


def _parent_heading_path(parent: PolicySectionNode | None, base_path: list[str]) -> list[str]:
    return list(parent.heading_path) if parent is not None else list(base_path)


def _clean_title(value: str) -> str:
    return normalize_whitespace(value).strip(" ：:")


def _is_action_section(title: str) -> bool:
    return any(keyword in title for keyword in ["处理", "处分", "处罚"])


def _is_current_action_section(current_major: PolicySectionNode | None) -> bool:
    return bool(current_major and current_major.metadata.get("is_action_section"))


def _last_numeric_part(label: str) -> int | None:
    parts = [part for part in label.split(".") if part]
    if not parts:
        return None
    return int(parts[-1])


def _chinese_ordinal_to_int(value: str) -> int | None:
    normalized = value.strip("（）()、 ")
    values = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if normalized in values:
        return values[normalized]
    if normalized.startswith("十") and len(normalized) == 2:
        return 10 + values.get(normalized[1], 0)
    if normalized.endswith("十") and len(normalized) == 2:
        return values.get(normalized[0], 0) * 10
    if "十" in normalized and len(normalized) == 3:
        left, right = normalized.split("十", 1)
        return values.get(left, 0) * 10 + values.get(right, 0)
    return None
