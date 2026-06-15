from __future__ import annotations

from typing import Any

from enterprise_rag_mvp.document_chunking.models import DocumentChunk
from enterprise_rag_mvp.document_parsing import normalize_whitespace
from enterprise_rag_mvp.policy_structure.models import PolicySectionNode, PolicyStructureDocument
from enterprise_rag_mvp.policy_structure.validator import ordinal_continuity_for_children

CHUNKER_NAME = "policy_structure_chunk_builder"
CHUNKER_VERSION = "1"


def build_policy_chunks_from_structure(
    structure: PolicyStructureDocument,
    *,
    base_metadata: dict[str, Any] | None = None,
    max_chars: int = 1200,
) -> list[DocumentChunk]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    metadata_base = dict(base_metadata or {})
    chunks: list[DocumentChunk] = []

    for node in structure.nodes:
        if node.node_type == "violation_level":
            definition = _section_definition_chunk(node, structure=structure, base_metadata=metadata_base)
            if definition is not None:
                chunks.extend(_bounded_chunks(definition, max_chars=max_chars))
            children = structure.children_of(node.node_id, node_type="violation_group")
            if children:
                chunks.extend(_bounded_chunks(_section_children_chunk(node, children, structure=structure, base_metadata=metadata_base), max_chars=max_chars))
        elif node.node_type == "leaf_clause":
            chunks.extend(
                _bounded_chunks(
                    _node_chunk(
                        node,
                        chunk_type="leaf_clause",
                        structure=structure,
                        base_metadata=metadata_base,
                    ),
                    max_chars=max_chars,
                )
            )
        elif node.node_type == "action_mapping":
            chunks.extend(
                _bounded_chunks(
                    _node_chunk(
                        node,
                        chunk_type="action_mapping",
                        structure=structure,
                        base_metadata=metadata_base,
                    ),
                    max_chars=max_chars,
                )
            )

    return [_renumber_chunk(chunk, index) for index, chunk in enumerate(chunks, start=1)]


def _section_definition_chunk(
    node: PolicySectionNode,
    *,
    structure: PolicyStructureDocument,
    base_metadata: dict[str, Any],
) -> DocumentChunk | None:
    text = normalize_whitespace(node.text)
    if not text:
        return None
    return _node_chunk(node, chunk_type="section_definition", structure=structure, base_metadata=base_metadata)


def _section_children_chunk(
    node: PolicySectionNode,
    children: list[PolicySectionNode],
    *,
    structure: PolicyStructureDocument,
    base_metadata: dict[str, Any],
) -> DocumentChunk:
    continuity = ordinal_continuity_for_children(children)
    child_lines = [f"{child.ordinal_label or ''} {child.title}".strip() for child in children]
    text = normalize_whitespace("\n".join([node.title, *child_lines]))
    metadata = _base_chunk_metadata(node, chunk_type="section_children", structure=structure, base_metadata=base_metadata)
    metadata.update(
        {
            "child_node_ids": [child.node_id for child in children],
            "child_count": len(children),
            **continuity,
        }
    )
    return DocumentChunk(chunk_id="", text=text, heading_path=list(node.heading_path), metadata=metadata)


def _node_chunk(
    node: PolicySectionNode,
    *,
    chunk_type: str,
    structure: PolicyStructureDocument,
    base_metadata: dict[str, Any],
) -> DocumentChunk:
    metadata = _base_chunk_metadata(node, chunk_type=chunk_type, structure=structure, base_metadata=base_metadata)
    metadata.update(node.metadata)
    return DocumentChunk(chunk_id="", text=normalize_whitespace(node.text), heading_path=list(node.heading_path), metadata=metadata)


def _base_chunk_metadata(
    node: PolicySectionNode,
    *,
    chunk_type: str,
    structure: PolicyStructureDocument,
    base_metadata: dict[str, Any],
) -> dict[str, Any]:
    metadata = {
        **base_metadata,
        "chunk_type": chunk_type,
        "chunking_strategy": "policy_structure",
        "chunker_name": CHUNKER_NAME,
        "chunker_version": CHUNKER_VERSION,
        "doc_id": structure.doc_id,
        "source_name": structure.source_name,
        "source_url": structure.source_url,
        "node_id": node.node_id,
        "parent_node_id": node.parent_id,
        "node_type": node.node_type,
        "ordinal_label": node.ordinal_label,
        "ordinal_value": node.ordinal_value,
        "section_title": node.title,
        "source_span": node.source_span,
        "element_ids": list(node.element_ids),
        "chunk_role": "retrieval",
        "retrieval_priority": "high",
    }
    parent = _parent_node(node, structure)
    if parent is not None:
        metadata["parent_node_type"] = parent.node_type
        metadata["parent_title"] = parent.title
    return metadata


def _parent_node(node: PolicySectionNode, structure: PolicyStructureDocument) -> PolicySectionNode | None:
    if node.parent_id is None:
        return None
    return next((candidate for candidate in structure.nodes if candidate.node_id == node.parent_id), None)


def _bounded_chunks(chunk: DocumentChunk, *, max_chars: int) -> list[DocumentChunk]:
    if len(chunk.text) <= max_chars:
        return [chunk]
    parts: list[DocumentChunk] = []
    start = 0
    split_index = 1
    while start < len(chunk.text):
        end = min(len(chunk.text), start + max_chars)
        part = chunk.text[start:end].strip()
        if part:
            metadata = dict(chunk.metadata)
            metadata["split_reason"] = "exceeds_max_chars"
            metadata["split_index"] = split_index
            parts.append(DocumentChunk(chunk_id="", text=part, heading_path=list(chunk.heading_path), metadata=metadata))
            split_index += 1
        start = end
    return parts


def _renumber_chunk(chunk: DocumentChunk, index: int) -> DocumentChunk:
    return DocumentChunk(chunk_id=f"structure-chunk-{index:04d}", text=chunk.text, heading_path=chunk.heading_path, metadata=chunk.metadata)
