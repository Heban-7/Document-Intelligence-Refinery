"""
PageIndex: hierarchical navigation over a document (section tree).
Enables "navigate then retrieve" with nested section relationships and a traversal API.
"""
from __future__ import annotations

from typing import Any, Iterator

from pydantic import BaseModel, Field


def _parse_heading_level(title: str) -> int:
    """
    Infer heading level from title. Returns 1 for top-level.
    - "1. Introduction" -> 1, "1.1 Background" -> 2, "1.1.1 Details" -> 3
    - "Chapter 1", "Section 2" -> 1
    - No number prefix -> 1
    """
    s = title.strip()
    if not s:
        return 1
    # Numbered: 1., 1.1., 1.1.1.
    import re
    m = re.match(r"^(\d+(?:\.\d+)*)\s*[.)]\s*", s)
    if m:
        depth = m.group(1).count(".") + 1
        return min(max(1, depth), 6)
    if re.match(r"^(chapter|part|section)\s+\d+", s, re.I):
        return 1
    return 1


class SectionNode(BaseModel):
    """One node in the PageIndex tree with hierarchy and traversal support."""
    title: str = ""
    page_start: int = Field(..., ge=1)
    page_end: int = Field(..., ge=1)
    level: int = Field(1, ge=1, le=6, description="Heading level (1 = top-level)")
    section_id: str = ""  # Stable id for traversal, e.g. "0", "0.1", "0.1.2"
    path: str = ""  # Human-readable path, e.g. "/Introduction/Background"
    child_sections: list["SectionNode"] = Field(default_factory=list)
    key_entities: list[str] = Field(default_factory=list)
    summary: str = ""
    data_types_present: list[str] = Field(default_factory=list)
    model_config = {"extra": "allow"}

    def __hash__(self) -> int:
        return hash((self.section_id, self.title))

    def all_titles(self) -> list[str]:
        """Return this section's title and all descendant section titles (for search filter)."""
        out = [self.title]
        for c in self.child_sections:
            out.extend(c.all_titles())
        return out


class PageIndex(BaseModel):
    """Root of the section tree for one document with traversal and topic navigation."""

    doc_id: str = ""
    file_name: str = ""
    sections: list[SectionNode] = Field(default_factory=list)
    model_config = {"extra": "allow"}

    def _id_to_node(self) -> dict[str, SectionNode]:
        """Build section_id -> node map (including descendants)."""
        out: dict[str, SectionNode] = {}

        def add(n: SectionNode) -> None:
            if n.section_id:
                out[n.section_id] = n
            for c in n.child_sections:
                add(c)

        for s in self.sections:
            add(s)
        return out

    def get_by_id(self, section_id: str) -> SectionNode | None:
        """Return the section with the given section_id, or None."""
        return self._id_to_node().get(section_id)

    def get_by_path(self, path: str) -> SectionNode | None:
        """
        Resolve a path to a section. Path format: "/Title1/Title2" or "/0/0.1".
        Returns the last segment match (by title or section_id).
        """
        path = path.strip("/")
        if not path:
            return None
        segments = [p.strip() for p in path.split("/") if p.strip()]
        if not segments:
            return None
        # Search in flat roots first by title or id
        current: list[SectionNode] = list(self.sections)
        node: SectionNode | None = None
        for seg in segments:
            found = None
            for n in current:
                if n.title == seg or n.section_id == seg:
                    found = n
                    break
            if found is None:
                return None
            node = found
            current = node.child_sections
        return node

    def children(self, node: SectionNode) -> list[SectionNode]:
        """Return direct children of the given node."""
        return list(node.child_sections)

    def ancestors(self, node: SectionNode) -> list[SectionNode]:
        """Return ancestors from root down to the node's parent (exclude node)."""
        by_id = self._id_to_node()
        # Find path from root to node by BFS/DFS
        path_ids: list[str] = []

        def find_path(roots: list[SectionNode], target_id: str, acc: list[str]) -> bool:
            for n in roots:
                if n.section_id == target_id:
                    acc.append(n.section_id)
                    return True
                acc.append(n.section_id)
                if find_path(n.child_sections, target_id, acc):
                    return True
                acc.pop()
            return False

        for s in self.sections:
            if find_path([s], node.section_id, path_ids):
                break
        out = []
        for sid in path_ids[:-1]:
            n = by_id.get(sid)
            if n:
                out.append(n)
        return out

    def flatten_depth_first(self) -> list[tuple[int, SectionNode]]:
        """Return (depth, node) for every section in depth-first order. Root sections at depth 0."""
        result: list[tuple[int, SectionNode]] = []

        def walk(nodes: list[SectionNode], depth: int) -> None:
            for n in nodes:
                result.append((depth, n))
                walk(n.child_sections, depth + 1)

        walk(self.sections, 0)
        return result

    def iter_depth_first(self) -> Iterator[tuple[int, SectionNode]]:
        """Yield (depth, node) for every section in depth-first order."""
        def walk(nodes: list[SectionNode], depth: int) -> Iterator[tuple[int, SectionNode]]:
            for n in nodes:
                yield (depth, n)
                yield from walk(n.child_sections, depth + 1)
        yield from walk(self.sections, 0)

    def find_sections_by_topic(
        self,
        topic: str,
        top_k: int = 5,
        *,
        score_fn: Any = None,
    ) -> list[tuple[float, SectionNode, str]]:
        """
        Topic-based navigation: score each section by relevance to topic (title, summary, entities).
        Returns list of (score, node, path) sorted by score descending.
        path is the human-readable path from root to the section (e.g. "/Introduction/Background").
        """
        topic_lower = topic.lower()
        words = set(w for w in topic_lower.split() if len(w) > 1)

        def default_score(node: SectionNode, path: str) -> float:
            text = " ".join([path, node.title, node.summary] + node.key_entities).lower()
            return sum(1 for w in words if w in text)

        scorer = score_fn or default_score
        scored: list[tuple[float, SectionNode, str]] = []

        def walk(nodes: list[SectionNode], path_prefix: str) -> None:
            for n in nodes:
                path = f"{path_prefix}/{n.title}" if path_prefix else f"/{n.title}"
                score = scorer(n, path)
                if score > 0:
                    scored.append((score, n, path))
                walk(n.child_sections, path.strip("/"))

        walk(self.sections, "")
        scored.sort(key=lambda x: (-x[0], x[2]))
        return scored[:top_k]

    def section_titles_for_topic(self, topic: str, top_k: int = 5) -> list[str]:
        """
        Return section titles to use for vector search filter when querying by topic.
        Uses find_sections_by_topic and returns all titles from the top-k sections
        (including their descendants) so retrieval can be scoped to those branches.
        """
        hits = self.find_sections_by_topic(topic, top_k=top_k)
        titles: list[str] = []
        seen: set[str] = set()
        for _score, node, _path in hits:
            for t in node.all_titles():
                if t and t not in seen:
                    seen.add(t)
                    titles.append(t)
        return titles


SectionNode.model_rebuild()
