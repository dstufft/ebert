from dataclasses import dataclass


@dataclass
class Discord:
    token: str
    guild: int | None = None


@dataclass
class Database:
    path: str


@dataclass
class Config:
    discord: Discord
    db: Database
    root: str = "."
