# app/database.py
import os
from sqlmodel import SQLModel, create_engine, Session
from typing import Generator

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sihtimetable.db")

# For sqlite: allow multithread
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

def init_db() -> None:
    SQLModel.metadata.create_all(engine)

def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
