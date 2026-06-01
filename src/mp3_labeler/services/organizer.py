from __future__ import annotations

from pathlib import Path

from mp3_labeler.domain.models import AlbumFolder, Decision, DecisionAction, ManualOverride
from mp3_labeler.domain.taxonomy import Taxonomy
from mp3_labeler.infrastructure.filesystem import FileSystem


ALBUM_BUCKET_FOLDER = "_Albums"


def album_destination(album_folder: AlbumFolder, taxonomy_node_id: str, taxonomy: Taxonomy, library: Path) -> Path:
    node = taxonomy.by_id()[taxonomy_node_id]
    folder_path = Path(node.folder_path)
    if _node_has_children(taxonomy_node_id, taxonomy):
        folder_path /= ALBUM_BUCKET_FOLDER
    return library / folder_path / album_folder.path.name


def _node_has_children(taxonomy_node_id: str, taxonomy: Taxonomy) -> bool:
    return any(node.parent_id == taxonomy_node_id for node in taxonomy.nodes)


class AlbumOrganizer:
    def __init__(self, filesystem: FileSystem | None = None) -> None:
        self.filesystem = filesystem or FileSystem()

    def decision_for_override(
        self,
        album_folder: AlbumFolder,
        override: ManualOverride,
        taxonomy: Taxonomy,
        library: Path,
        *,
        dry_run: bool = True,
    ) -> Decision:
        return self.decision_for_node(
            album_folder,
            override.taxonomy_node_id,
            taxonomy,
            library,
            dry_run=dry_run,
            reason=f"matched {override.match_type} override",
        )

    def decision_for_node(
        self,
        album_folder: AlbumFolder,
        taxonomy_node_id: str,
        taxonomy: Taxonomy,
        library: Path,
        *,
        dry_run: bool = True,
        reason: str = "accepted taxonomy classification",
    ) -> Decision:
        node = taxonomy.by_id()[taxonomy_node_id]
        destination = album_destination(album_folder, taxonomy_node_id, taxonomy, library)
        return Decision(
            album_folder=album_folder,
            action=DecisionAction.MOVE,
            reason=f"{reason} for taxonomy node '{node.id}'",
            destination_path=destination,
            dry_run=dry_run,
        )

    def validate(self, decision: Decision) -> None:
        if decision.destination_path is None:
            raise ValueError("A move decision requires a destination path")
        self.filesystem.validate_album_move(decision.album_folder.path, decision.destination_path)

    def apply(self, decision: Decision) -> None:
        if decision.action is not DecisionAction.MOVE:
            return
        if decision.destination_path is None:
            raise ValueError("A move decision requires a destination path")
        self.filesystem.move_album(
            decision.album_folder.path,
            decision.destination_path,
            dry_run=decision.dry_run,
        )


__all__ = ["ALBUM_BUCKET_FOLDER", "AlbumOrganizer", "album_destination"]
