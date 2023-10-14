import pathlib
import tomllib
import os.path
import sqlite3

import dacite
import typer

from sqlalchemy import create_engine
from typing_extensions import Annotated

from .bot import Ebert
from .config import Config
from .db import Base

app = typer.Typer()


@app.command()
def run(
    config_file: Annotated[pathlib.Path, typer.Option("--config", "-c")],
    sync_commands: Annotated[bool, typer.Option("--sync-commands", "-s")] = False,
):
    with open(config_file, "rb") as fp:
        config = dacite.from_dict(Config, tomllib.load(fp))
        config.root = os.path.dirname(config_file)

    bot = Ebert(config=config, sync_commands=sync_commands)
    bot.run()


@app.command()
def register():
    pass


@app.command()
def init(config_file: Annotated[pathlib.Path, typer.Option("--config", "-c")]):
    with open(config_file, "rb") as fp:
        config = dacite.from_dict(Config, tomllib.load(fp))
        config.root = os.path.dirname(config_file)

    db_path = os.path.abspath(os.path.join(config.root, config.db.path))

    engine = create_engine(f"sqlite:////{db_path}")

    Base.metadata.create_all(engine)
