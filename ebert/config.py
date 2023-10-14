from dataclasses import dataclass


@dataclass
class Discord:
    token: str
    guild: int | None = None
    channel: int | None = None


@dataclass
class Database:
    path: str


@dataclass
class TMDB:
    api_key: str


@dataclass
class Config:
    discord: Discord
    db: Database
    tmdb: TMDB
    root: str = "."
