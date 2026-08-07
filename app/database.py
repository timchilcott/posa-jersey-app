import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Get database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL")

# Fix Render.com postgres:// to postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine. SQLite does not accept the Postgres-oriented pool options.
engine_options = {"pool_pre_ping": True}
if DATABASE_URL and not DATABASE_URL.startswith("sqlite"):
    engine_options.update(pool_size=10, max_overflow=20)

engine = create_engine(DATABASE_URL, **engine_options)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


# Dependency function for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
