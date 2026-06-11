from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PolicyChunk:
    chunk_id: str
    doc_id: str
    block_id: str | None
    text: str
    heading_path: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResult:
    chunk: PolicyChunk
    distance: float
