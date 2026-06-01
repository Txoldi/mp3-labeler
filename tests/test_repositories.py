from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from mp3_labeler.domain.models import (
    AppliedAlbumDecision,
    ArtistCandidate,
    LastFmAlbumLookupResult,
    LastFmArtistLookupResult,
    LastFmLookupStatus,
    LastFmTag,
    ManualOverride,
)
from mp3_labeler.domain.scoring import ReviewItem, ReviewStatus, ScoreEvidence
from mp3_labeler.infrastructure.db import open_connection
from mp3_labeler.infrastructure.repositories import DecisionRepository, LastFmCacheRepository, ManualOverrideRepository, ReviewRepository


def test_open_connection_initializes_lastfm_cache_schema(tmp_path) -> None:
    connection = open_connection(tmp_path / "nested" / "cache.sqlite3")
    names = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'lastfm_%'"
        )
    }

    assert names == {
        "lastfm_album_lookup",
        "lastfm_album_tag",
        "lastfm_artist_lookup",
        "lastfm_artist_tag",
    }


def test_album_cache_round_trips_tags_using_normalized_query_keys(tmp_path) -> None:
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    repository = LastFmCacheRepository(open_connection(tmp_path / "cache.sqlite3"))
    repository.save_album(
        LastFmAlbumLookupResult(
            artist_query="Class  Traitor",
            album_query="The Images Aren't Mine",
            status=LastFmLookupStatus.FOUND,
            tags=(
                LastFmTag("metalcore", 100.0, "album"),
                LastFmTag("hardcore", 75.0, "album"),
            ),
        ),
        fetched_at=now,
        expires_at=now + timedelta(days=30),
    )

    cached = repository.get_album(" class traitor ", "THE IMAGES AREN'T MINE", at=now)

    assert cached is not None
    assert cached.result.artist_query == "Class  Traitor"
    assert [tag.name for tag in cached.result.tags] == ["metalcore", "hardcore"]


def test_artist_cache_round_trips_candidate_details_and_tags(tmp_path) -> None:
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    repository = LastFmCacheRepository(open_connection(tmp_path / "cache.sqlite3"))
    candidate = ArtistCandidate(
        name="Remote Artist",
        url="https://last.fm/artist",
        mbid="mbid",
        listeners=42,
        playcount=100,
        tags=(LastFmTag("punk", 50.0, "artist"),),
        similar_artists=("Peer Band",),
    )
    repository.save_artist(
        LastFmArtistLookupResult("Artist", LastFmLookupStatus.FOUND, candidate),
        fetched_at=now,
        expires_at=now + timedelta(days=30),
    )

    cached = repository.get_artist("artist", at=now)

    assert cached is not None
    assert cached.result.candidate == candidate


def test_expired_repository_result_is_not_returned(tmp_path) -> None:
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    repository = LastFmCacheRepository(open_connection(tmp_path / "cache.sqlite3"))
    repository.save_artist(
        LastFmArtistLookupResult("Missing", LastFmLookupStatus.NOT_FOUND),
        fetched_at=now - timedelta(days=8),
        expires_at=now - timedelta(days=1),
    )

    assert repository.get_artist("Missing", at=now) is None


def test_review_repository_round_trips_and_resolves_pending_review(tmp_path) -> None:
    now = datetime(2026, 5, 27, tzinfo=timezone.utc)
    repository = ReviewRepository(open_connection(tmp_path / "cache.sqlite3"))
    queued = repository.save_pending(
        ReviewItem(
            id=None,
            album_path=tmp_path / "inbox" / "Artist - Album",
            artist="Artist",
            album="Album",
            year=2026,
            existing_genres=("Metal",),
            matched_taxonomy_node_ids=("metal",),
            proposed_node_id="metal",
            score=1.05,
            confidence=1.0,
            reason="broad top-level category",
            evidence=(ScoreEvidence("existing_genre", "matched", 1.05),),
        ),
        at=now,
    )

    assert queued.id is not None
    assert repository.list() == (queued,)
    resolved = repository.set_status(queued.id, ReviewStatus.ACCEPTED, at=now + timedelta(minutes=1))
    assert resolved.status is ReviewStatus.ACCEPTED
    assert repository.list() == ()
    assert repository.list(ReviewStatus.ACCEPTED)[0].evidence == queued.evidence
    repository.delete(queued.id)
    assert repository.get(queued.id) is None


def test_review_repository_updates_requeued_album_instead_of_duplicating_it(tmp_path) -> None:
    now = datetime(2026, 5, 27, tzinfo=timezone.utc)
    repository = ReviewRepository(open_connection(tmp_path / "cache.sqlite3"))
    original = ReviewItem(
        id=None,
        album_path=tmp_path / "album",
        artist="Artist",
        album="Album",
        year=None,
        existing_genres=(),
        matched_taxonomy_node_ids=(),
        proposed_node_id=None,
        score=None,
        confidence=None,
        reason="unknown",
    )
    first = repository.save_pending(original, at=now)
    second = repository.save_pending(
        ReviewItem(
            id=None,
            album_path=original.album_path,
            artist=original.artist,
            album=original.album,
            year=original.year,
            existing_genres=original.existing_genres,
            matched_taxonomy_node_ids=original.matched_taxonomy_node_ids,
            proposed_node_id="metal",
            score=0.5,
            confidence=0.0,
            reason="new evidence",
        ),
        at=now + timedelta(minutes=1),
    )

    assert first.id == second.id
    assert second.reason == "new evidence"
    assert len(repository.list()) == 1


def test_manual_override_repository_round_trips_and_replaces_same_match(tmp_path) -> None:
    now = datetime(2026, 5, 27, tzinfo=timezone.utc)
    repository = ManualOverrideRepository(open_connection(tmp_path / "cache.sqlite3"))
    repository.save(
        ManualOverride(
            match_type="artist_album",
            artist="Artist",
            album="Album",
            taxonomy_node_id="metal",
        ),
        at=now,
    )
    repository.save(
        ManualOverride(
            match_type="artist_album",
            artist="Artist",
            album="Album",
            taxonomy_node_id="death-metal",
            notes="Corrected decision.",
        ),
        at=now + timedelta(minutes=1),
    )

    saved = repository.list()
    assert len(saved) == 1
    assert saved[0].taxonomy_node_id == "death-metal"
    assert saved[0].notes == "Corrected decision."


def test_applied_decision_history_round_trips_successful_processing(tmp_path) -> None:
    now = datetime(2026, 5, 27, tzinfo=timezone.utc)
    repository = DecisionRepository(open_connection(tmp_path / "history.sqlite3"))
    decision = AppliedAlbumDecision(
        source_path=Path("inbox/Artist - Album"),
        destination_path=Path("library/Metal/Death Metal/Artist - Album"),
        artist="Artist",
        album="Album",
        taxonomy_node_id="death-metal",
        genres_written=("Death Metal",),
        decision_source="confirmed_automatic",
        applied_at=now,
    )

    repository.save_applied(decision)

    assert repository.list_applied() == (decision,)
