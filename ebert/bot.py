import datetime
import os.path
import random
import re

import discord
import discord.ui
import tmdb.route

from discord import app_commands
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


from .config import Config
from .db import Poll, Movie


_emoji_regex = re.compile(r"^<a?:(\w+):(\d+)>$")


class Ebert(discord.Client):
    config: Config
    cmds: app_commands.CommandTree

    _sync_commands: bool

    def __init__(self, *, config: Config, sync_commands: bool = False):
        super().__init__(intents=discord.Intents.default())

        self.config = config
        self._sync_commands = sync_commands

        self.event(self.on_message)

        self.cmds = app_commands.CommandTree(self)
        self.cmds.add_command(ebert)
        self.cmds.add_command(suggest_movie)

    def run(self, token=None, *args, **kwargs):
        if token is None:
            token = self.config.discord.token
        super().run(token, *args, **kwargs)

    async def setup_hook(self):
        if self._sync_commands:
            if self.config.discord.guild is not None:
                guild = discord.Object(id=self.config.discord.guild)
                self.cmds.copy_global_to(guild=guild)
                await self.cmds.sync(guild=guild)
            else:
                await self.cmds.sync()

        db_path = os.path.abspath(os.path.join(self.config.root, self.config.db.path))

        self.engine = create_async_engine(f"sqlite+aiosqlite:////{db_path}")
        self.db = async_sessionmaker(self.engine)

        self.tmdb = tmdb.route.Base()
        self.tmdb.key = self.config.tmdb.api_key

    async def on_message(self, message: discord.Message):
        if message.channel.id == self.config.discord.channel:
            if not message.author.bot:
                await message.delete()


ebert = app_commands.Group(name="ebert", description="Ebert Management")
poll = app_commands.Group(name="poll", parent=ebert, description="Manage Polls")


@poll.command(name="start", description="Start a movie poll")
async def poll_start(ctx: discord.Interaction) -> None:
    await ctx.response.defer(ephemeral=True)

    async with client_db(ctx) as db:
        result = await db.execute(select(Poll).filter(Poll.open == True).limit(1))

        poll = result.unique().scalar_one_or_none()
        if poll is not None:
            ctx.followup.send(
                f"Could not start a movie poll, there is already an open one."
            )
            return

        poll = Poll(open=True)
        msg = await ctx.channel.send(poll_message(ctx.channel.guild, poll))
        await msg.pin()
        poll.channel_id = msg.channel.id
        poll.message_id = msg.id

        db.add(poll)

        await db.commit()

    await ctx.followup.send("Poll Started")


@poll.command(name="end", description="End a movie poll")
@app_commands.describe(
    winner="The winning movie.",
)
async def poll_end(ctx: discord.Interaction, winner: str) -> None:
    await ctx.response.defer(ephemeral=True)

    async with client_db(ctx) as db:
        result = await db.execute(select(Poll).filter(Poll.open == True).limit(1))

        poll = result.unique().scalar_one_or_none()
        if poll is None:
            await ctx.followup.send(
                "Could not end a movie poll, there isn't an open one."
            )
            return

        for m in poll.movies.values():
            if winner == m.title:
                movie = m
                break
        else:
            await ctx.followup.send(
                f"Could not end a movie poll, ``{winner}`` isn't an option."
            )
            return

        channel = ctx.client.get_channel(poll.channel_id)
        if channel is None:
            await ctx.followup.send("Could not locate channel")
            return
        try:
            message = await channel.fetch_message(poll.message_id)
        except discord.NotFound:
            await ctx.followup.send("Could not locate message")
            return

        poll.open = False
        poll.winner = movie

        await message.edit(content=poll_message(channel.guild, poll))
        await message.unpin()
        await db.commit()

    await ctx.followup.send("Poll Finished")


@app_commands.command(name="movie", description="Suggest a movie")
@app_commands.describe(
    movie="The name of a movie to suggest",
    year="(Optional) The year the movie was released (as reported by TMDB)",
)
async def suggest_movie(ctx: discord.Interaction, movie: str, year: str | None = None):
    await ctx.response.defer(ephemeral=True)

    try:
        year_i = int(year) if year else 0
    except ValueError:
        await ctx.followup.send(f"{year} is not a valid year.")
        return

    async with client_db(ctx) as db:
        result = await db.execute(select(Poll).filter(Poll.open == True).limit(1))

        poll = result.unique().scalar_one_or_none()
        if poll is None:
            await ctx.followup.send("No open movie night polls")
            return

        all_movies = (await tmdb.route.Movie().search(movie)).get("results", [])
        movies: list[tuple[str, int]] = []
        for result in all_movies:
            if (
                result.get("title").lower() != movie.lower()
                and result.get("original_title", "").lower() != movie.lower()
            ):
                continue

            if year_i:
                if "release_date" not in result:
                    continue

                release_date = datetime.date.fromisoformat(result["release_date"])
                if release_date.year != year_i:
                    continue

            movies.append(
                (result.get("title", result.get("original_title", movie)), result["id"])
            )

        if not movies:
            await ctx.followup.send(
                f"Could not find any movies in https://www.themoviedb.org for {movie}"
            )
            return
        if len(movies) > 1:
            await ctx.followup.send(
                f"Multiple movies found for {movie}, try adding a release year."
            )
            return

        selected_movie = movies[0]

        if selected_movie[1] in [m.tmdb_id for m in poll.movies.values()]:
            await ctx.followup.send(f"{movie} is already an option, try voting for it.")
            return

        channel = ctx.client.get_channel(poll.channel_id)
        if channel is None:
            await ctx.followup.send("Could not locate channel")
            return
        try:
            message = await channel.fetch_message(poll.message_id)
        except discord.NotFound:
            await ctx.followup.send("Could not locate message")
            return

        available_reacts = list(
            set(e.name for e in channel.guild.emojis) - set(poll.movies.keys())
        )
        if not available_reacts:
            await ctx.followup.send("No available emoji left, maybe next raid night?")
            return

        react_text: str = random.choice(available_reacts)

        result = await db.execute(
            select(Movie).filter(Movie.tmdb_id == selected_movie[1]).limit(1)
        )
        movie_obj = result.unique().scalar_one_or_none()
        if movie_obj is None:
            movie_obj = Movie(title=selected_movie[0], tmdb_id=selected_movie[1])
            db.add(movie_obj)

        poll.movies[react_text] = movie_obj

        await message.edit(content=poll_message(channel.guild, poll))
        await message.add_reaction(emoji(channel.guild, react_text))
        await channel.send(
            f"Added {movie_obj.title} (<https://www.themoviedb.org/movie/{movie_obj.tmdb_id}>), suggested by {ctx.user.mention}"
        )
        await db.commit()

    await ctx.followup.send("Poll Updated")


def client_db(ctx: discord.Interaction) -> AsyncSession:
    return ctx.client.db()


def tmdb_api(ctx: discord.Interaction) -> tmdb.route.Base:
    return ctx.client.tmdb


def poll_message(guild: discord.Guild, poll: Poll) -> str:
    if poll.open:
        msg = ["Vote on the next Movie Night Movie!"]
        msg += [
            f"- {emoji(guild, react)} {movie.title} (<https://www.themoviedb.org/movie/{movie.tmdb_id}>)"
            for react, movie in poll.movies.items()
        ]
        msg += ["", "To vote, click a react, or add another movie through ``/movie``"]
    else:
        msg = [f"Next Movie Night Movie: {poll.winner.title}"]

    return "\n".join(msg)


def emoji(guild: discord.Guild, emoji: str) -> str:
    for e in guild.emojis:
        if emoji == e.name:
            return e
    return emoji
