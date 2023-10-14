from __future__ import annotations


import asyncio
import datetime

from sqlalchemy import Table, Column, ForeignKey, String, UniqueConstraint
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.collections import attribute_keyed_dict


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Poll(Base):
    __tablename__ = "poll"

    id: Mapped[int] = mapped_column(primary_key=True)

    open: Mapped[bool]

    channel_id: Mapped[int]
    message_id: Mapped[int]

    poll_movies: Mapped[list[PollMovie]] = relationship(
        back_populates="poll",
        cascade="all, delete-orphan",
        collection_class=attribute_keyed_dict("react"),
        lazy="joined",
    )
    movies: AssociationProxy[dict[str, Movie]] = association_proxy(
        "poll_movies",
        "movie",
        creator=lambda k, v: PollMovie(react=k, movie=v),
    )

    winner_id: Mapped[int | None] = mapped_column(ForeignKey("movie.id"), nullable=True)
    winner: Mapped[Movie | None] = relationship(lazy="joined")


class Movie(Base):
    __tablename__ = "movie"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(unique=True)
    tmdb_id: Mapped[int] = mapped_column(unique=True)


class PollMovie(Base):
    __tablename__ = "poll_movie"
    __table_args__ = (UniqueConstraint("poll_id", "react"),)

    poll_id: Mapped[int] = mapped_column(ForeignKey("poll.id"), primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movie.id"), primary_key=True)
    react: Mapped[str]

    poll: Mapped[Poll] = relationship(back_populates="poll_movies", lazy="joined")
    movie: Mapped[Movie] = relationship(lazy="joined")
