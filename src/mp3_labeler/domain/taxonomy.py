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

    def match_genre_node_ids(self, genre: str) -> tuple[str, ...]:
        normalized_genre = self.normalize_label(genre)
        return tuple(
            node.id
            for node in self.nodes
            if normalized_genre in {self.normalize_label(node.name), *(self.normalize_label(alias) for alias in node.aliases)}
        )

    @staticmethod
    def normalize_label(value: str) -> str:
        return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())
