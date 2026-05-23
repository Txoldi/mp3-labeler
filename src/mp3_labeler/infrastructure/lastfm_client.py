from __future__ import annotations


class LastFmClient:
    def __init__(self, api_key: str, api_secret: str | None = None) -> None:
        self.api_key = api_key
        self.api_secret = api_secret

