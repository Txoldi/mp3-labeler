from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaxonomyNode:
    id: str
    name: str
    folder_path: str
    parent_id: str | None = None
    aliases: tuple[str, ...] = ()
    positive_tags: tuple[str, ...] = ()
    negative_tags: tuple[str, ...] = ()
    required_tags: tuple[str, ...] = ()
    broad_tags: tuple[str, ...] = ()
    priority: int = 0
    auto_accept_threshold: float = 0.9


@dataclass(frozen=True, slots=True)
class Taxonomy:
    nodes: tuple[TaxonomyNode, ...]

    def by_id(self) -> dict[str, TaxonomyNode]:
        return {node.id: node for node in self.nodes}

