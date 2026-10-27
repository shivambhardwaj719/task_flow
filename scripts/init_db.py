"""Database initialization script to create all tables."""
import logging
from app.database import Base, engine
from app.models import User, Project, Task, Notification  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db():
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully.")


if __name__ == "__main__":
    init_db()
