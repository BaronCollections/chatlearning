from enterprise_rag_mvp.models import SearchResult


def render_results(query: str, results: list[SearchResult]) -> str:
    lines = [f"Query: {query}", ""]
    if not results:
        lines.append("No matching policy chunks found.")
        return "\n".join(lines)

    for index, result in enumerate(results, start=1):
        chunk = result.chunk
        title = " > ".join(chunk.heading_path) if chunk.heading_path else chunk.doc_id
        source = chunk.metadata.get("source", chunk.doc_id)
        page = chunk.metadata.get("page")
        lines.append(f"{index}. {title}")
        lines.append(f"   distance={result.distance:.4f}")
        lines.append(f"   {chunk.text}")
        source_line = f"   source={source}"
        if page is not None:
            source_line += f" page={page}"
        lines.append(source_line)
        lines.append("")
    return "\n".join(lines).rstrip()
