from __future__ import annotations

from pathlib import Path

import pytest

from mp3_labeler.config.taxonomy_loader import TaxonomyLoader, TaxonomyValidationError


def write_taxonomy(tmp_path: Path, contents: str) -> Path:
    path = tmp_path / "taxonomy.toml"
    path.write_text(contents, encoding="utf-8")
    return path


def test_load_builds_arbitrary_depth_taxonomy_with_tuple_fields(tmp_path) -> None:
    path = write_taxonomy(
        tmp_path,
        """
[[nodes]]
id = "metal"
name = "Metal"
folder_path = "Metal"
aliases = ["Heavy Metal"]
positive_tags = ["metal"]
auto_accept_threshold = 0.85

[[nodes]]
id = "black-metal"
name = "Black Metal"
parent_id = "metal"
folder_path = "Metal/Black Metal"
required_tags = ["black metal"]

[[nodes]]
id = "symphonic-black-metal"
name = "Symphonic Black Metal"
parent_id = "black-metal"
folder_path = "Metal/Black Metal/Symphonic Black Metal"
positive_tags = ["symphonic black metal"]

[[nodes]]
id = "orchestral-black-metal"
name = "Orchestral Black Metal"
parent_id = "symphonic-black-metal"
folder_path = "Metal/Black Metal/Symphonic Black Metal/Orchestral Black Metal"
negative_tags = ["symphonic metal"]
priority = 2
auto_accept_threshold = 0.94
""",
    )

    taxonomy = TaxonomyLoader().load(path)
    nodes = taxonomy.by_id()

    assert len(taxonomy.nodes) == 4
    assert nodes["metal"].aliases == ("Heavy Metal",)
    assert nodes["metal"].positive_tags == ("metal",)
    assert nodes["orchestral-black-metal"].parent_id == "symphonic-black-metal"
    assert nodes["orchestral-black-metal"].negative_tags == ("symphonic metal",)
    assert nodes["orchestral-black-metal"].priority == 2
    assert nodes["orchestral-black-metal"].auto_accept_threshold == pytest.approx(0.94)


def test_load_accepts_example_taxonomy_configuration() -> None:
    path = Path(__file__).parent.parent / "config" / "taxonomy.example.toml"

    taxonomy = TaxonomyLoader().load(path)

    assert "metal" in taxonomy.by_id()
    assert "melodic-death-metal" in taxonomy.by_id()


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("", "at least one"),
        ('[[nodes]]\nname = "Metal"\nfolder_path = "Metal"\n', "field 'id'"),
        (
            '[[nodes]]\nid = "metal"\nname = "Metal"\nfolder_path = "Metal"\n'
            '[[nodes]]\nid = "metal"\nname = "Again"\nfolder_path = "Again"\n',
            "Duplicate taxonomy node id",
        ),
        (
            '[[nodes]]\nid = "black-metal"\nname = "Black Metal"\n'
            'parent_id = "metal"\nfolder_path = "Metal/Black Metal"\n',
            "unknown parent_id",
        ),
        (
            '[[nodes]]\nid = "metal"\nname = "Metal"\nfolder_path = "../Metal"\n',
            "invalid segments",
        ),
        (
            '[[nodes]]\nid = "metal"\nname = "Metal"\nfolder_path = "Metal"\n'
            "auto_accept_threshold = 1.5\n",
            "between 0.0 and 1.0",
        ),
    ],
)
def test_load_rejects_invalid_taxonomy_configuration(tmp_path, contents: str, message: str) -> None:
    with pytest.raises(TaxonomyValidationError, match=message):
        TaxonomyLoader().load(write_taxonomy(tmp_path, contents))


def test_load_rejects_parent_cycle(tmp_path) -> None:
    path = write_taxonomy(
        tmp_path,
        """
[[nodes]]
id = "one"
name = "One"
parent_id = "two"
folder_path = "Two/One"

[[nodes]]
id = "two"
name = "Two"
parent_id = "one"
folder_path = "One/Two"
""",
    )

    with pytest.raises(TaxonomyValidationError, match="parent cycle"):
        TaxonomyLoader().load(path)


def test_load_rejects_child_folder_outside_parent_folder(tmp_path) -> None:
    path = write_taxonomy(
        tmp_path,
        """
[[nodes]]
id = "metal"
name = "Metal"
folder_path = "Metal"

[[nodes]]
id = "black-metal"
name = "Black Metal"
parent_id = "metal"
folder_path = "Extreme/Black Metal"
""",
    )

    with pytest.raises(TaxonomyValidationError, match="directly nested"):
        TaxonomyLoader().load(path)


def test_load_raises_for_missing_file_or_directory_path(tmp_path) -> None:
    loader = TaxonomyLoader()

    with pytest.raises(FileNotFoundError):
        loader.load(tmp_path / "missing.toml")
    with pytest.raises(IsADirectoryError):
        loader.load(tmp_path)
