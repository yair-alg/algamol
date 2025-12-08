"""Database initialization and session management."""

import logging
from pathlib import Path
from typing import Optional, Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from src.models import Base
from src.config import get_config

logger = logging.getLogger(__name__)


# Enable foreign key constraints for SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Database:
    """Database manager for Algamol."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file. If None, uses config.
        """
        if db_path is None:
            config = get_config()
            db_path = config.get_db_path()

        self.db_path = db_path
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False}
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

        logger.info(f"Database initialized at {db_path}")

    def init_db(self):
        """Create all tables if they don't exist."""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created/verified")

    def drop_all(self):
        """Drop all tables. USE WITH CAUTION!"""
        Base.metadata.drop_all(bind=self.engine)
        logger.warning("All database tables dropped")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session as a context manager.

        Yields:
            Session: SQLAlchemy session

        Example:
            with db.get_session() as session:
                papers = session.query(Paper).all()
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    def create_full_text_search(self):
        """Create FTS5 virtual table for full-text search on papers."""
        with self.get_session() as session:
            # Check if FTS table already exists
            result = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='papers_fts'")
            ).fetchone()

            if result is None:
                # Create FTS5 virtual table
                session.execute(text("""
                    CREATE VIRTUAL TABLE papers_fts USING fts5(
                        paper_id UNINDEXED,
                        title,
                        abstract,
                        authors,
                        content='papers',
                        content_rowid='id'
                    )
                """))

                # Create triggers to keep FTS in sync
                session.execute(text("""
                    CREATE TRIGGER papers_fts_insert AFTER INSERT ON papers BEGIN
                        INSERT INTO papers_fts(paper_id, title, abstract, authors)
                        VALUES (new.id, new.title, new.abstract, json_extract(new.authors, '$'));
                    END
                """))

                session.execute(text("""
                    CREATE TRIGGER papers_fts_delete AFTER DELETE ON papers BEGIN
                        DELETE FROM papers_fts WHERE paper_id = old.id;
                    END
                """))

                session.execute(text("""
                    CREATE TRIGGER papers_fts_update AFTER UPDATE ON papers BEGIN
                        DELETE FROM papers_fts WHERE paper_id = old.id;
                        INSERT INTO papers_fts(paper_id, title, abstract, authors)
                        VALUES (new.id, new.title, new.abstract, json_extract(new.authors, '$'));
                    END
                """))

                session.commit()
                logger.info("Full-text search tables and triggers created")
            else:
                logger.debug("FTS table already exists")


# Global database instance
_db: Optional[Database] = None


def get_db() -> Database:
    """Get the global database instance."""
    global _db
    if _db is None:
        _db = Database()
        _db.init_db()
        _db.create_full_text_search()
    return _db


def init_database(db_path: Optional[Path] = None):
    """Initialize the database and create all tables.

    Args:
        db_path: Optional path to database file
    """
    global _db
    _db = Database(db_path)
    _db.init_db()
    _db.create_full_text_search()
    return _db
