from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import tomllib

from mp3_labeler.domain.taxonomy import Taxonomy, TaxonomyNode


class TaxonomyValidationError(ValueError):
    """Raised when taxonomy configuration cannot be used safely."""


class TaxonomyLoader:
    def load(self, path: Path) -> Taxonomy:
        if not path.exists():
            raise FileNotFoundError(f"Taxonomy file does not exist: {path}")
        if not path.is_file():
            raise IsADirectoryError(f"Taxonomy path is not a file: {path}")

        with path.open("rb") as file:
            try:
                data = tomllib.load(file)
            except tomllib.TOMLDecodeError as error:
                raise TaxonomyValidationError(f"Invalid taxonomy TOML: {error}") from error

        return self._load_from_data(data)

    def _load_from_data(self, data: Mapping[str, Any]) -> Taxonomy:
        node_values = data.get("nodes")
        if not isinstance(node_values, list) or not node_values:
            raise TaxonomyValidationError("Taxonomy must contain at least one [[nodes]] entry")

        nodes = tuple(self._parse_node(value, index) for index, value in enumerate(node_values, start=1))
        self._validate_ids_and_paths(nodes)
        self._validate_genre_match_labels(nodes)
        self._validate_parent_relationships(nodes)
        return Taxonomy(nodes=nodes)

    def _parse_node(self, data: Any, index: int) -> TaxonomyNode:
        if not isinstance(data, Mapping):
            raise TaxonomyValidationError(f"Node {index} must be a TOML table")

        node_id = self._required_text(data, "id", index)
        name = self._required_text(data, "name", index)
        folder_path = self._valid_folder_path(self._required_text(data, "folder_path", index), node_id)
        parent_id = self._optional_text(data, "parent_id", node_id)
        threshold = data.get("auto_accept_threshold", 0.9)
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
            raise TaxonomyValidationError(
                f"Node '{node_id}' auto_accept_threshold must be a number between 0.0 and 1.0"
            )

        priority = data.get("priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise TaxonomyValidationError(f"Node '{node_id}' priority must be an integer")

        return TaxonomyNode(
            id=node_id,
            name=name,
            parent_id=parent_id,
            folder_path=folder_path,
            aliases=self._text_tuple(data, "aliases", node_id),
            positive_tags=self._text_tuple(data, "positive_tags", node_id),
            negative_tags=self._text_tuple(data, "negative_tags", node_id),
            required_tags=self._text_tuple(data, "required_tags", node_id),
            broad_tags=self._text_tuple(data, "broad_tags", node_id),
            priority=priority,
            auto_accept_threshold=float(threshold),
        )

    @staticmethod
    def _required_text(data: Mapping[str, Any], field: str, index: int) -> str:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise TaxonomyValidationError(f"Node {index} requires non-empty text field '{field}'")
        return value.strip()

    @staticmethod
    def _optional_text(data: Mapping[str, Any], field: str, node_id: str) -> str | None:
        value = data.get(field)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise TaxonomyValidationError(f"Node '{node_id}' field '{field}' must be non-empty text")
        return value.strip()

    @staticmethod
    def _text_tuple(data: Mapping[str, Any], field: str, node_id: str) -> tuple[str, ...]:
        values = data.get(field, [])
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise TaxonomyValidationError(f"Node '{node_id}' field '{field}' must be a list of non-empty strings")
        return tuple(value.strip() for value in values)

    @staticmethod
    def _valid_folder_path(value: str, node_id: str) -> str:
        if "\\" in value:
            raise TaxonomyValidationError(f"Node '{node_id}' folder_path must use '/' separators")

        path = PurePosixPath(value)
        if path.is_absolute() or PureWindowsPath(value).is_absolute():
            raise TaxonomyValidationError(f"Node '{node_id}' folder_path must be relative")
        if value != str(path) or any(part in {"", ".", ".."} for part in value.split("/")):
            raise TaxonomyValidationError(f"Node '{node_id}' folder_path contains invalid segments")
        return value

    @staticmethod
    def _validate_ids_and_paths(nodes: tuple[TaxonomyNode, ...]) -> None:
        ids: set[str] = set()
        paths: set[str] = set()
        for node in nodes:
            if node.id in ids:
                raise TaxonomyValidationError(f"Duplicate taxonomy node id: '{node.id}'")
            if node.folder_path.casefold() in paths:
                raise TaxonomyValidationError(f"Duplicate taxonomy folder_path: '{node.folder_path}'")
            ids.add(node.id)
            paths.add(node.folder_path.casefold())

    @staticmethod
    def _validate_genre_match_labels(nodes: tuple[TaxonomyNode, ...]) -> None:
        owners: dict[str, str] = {}
        for node in nodes:
            for label in (node.name, *node.aliases):
                normalized_label = Taxonomy.normalize_label(label)
                existing_owner = owners.get(normalized_label)
                if existing_owner is not None and existing_owner != node.id:
                    raise TaxonomyValidationError(
                        f"Genre label '{label}' is ambiguous between nodes '{existing_owner}' and '{node.id}'"
                    )
                owners[normalized_label] = node.id

    def _validate_parent_relationships(self, nodes: tuple[TaxonomyNode, ...]) -> None:
        by_id = {node.id: node for node in nodes}
        for node in nodes:
            if node.parent_id is not None and node.parent_id not in by_id:
                raise TaxonomyValidationError(
                    f"Node '{node.id}' refers to unknown parent_id '{node.parent_id}'"
                )

        checked: set[str] = set()
        checking: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in checking:
                raise TaxonomyValidationError(f"Taxonomy contains a parent cycle involving '{node_id}'")
            if node_id in checked:
                return
            checking.add(node_id)
            parent_id = by_id[node_id].parent_id
            if parent_id is not None:
                visit(parent_id)
            checking.remove(node_id)
            checked.add(node_id)

        for node in nodes:
            visit(node.id)

        for node in nodes:
            if node.parent_id is not None:
                parent = by_id[node.parent_id]
                parent_parts = PurePosixPath(parent.folder_path).parts
                node_parts = PurePosixPath(node.folder_path).parts
                if node_parts[:-1] != parent_parts:
                    raise TaxonomyValidationError(
                        f"Node '{node.id}' folder_path must be directly nested under parent '{parent.id}'"
                    )


__all__ = ["TaxonomyLoader", "TaxonomyValidationError"]
