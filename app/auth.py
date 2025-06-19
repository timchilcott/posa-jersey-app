from sqlalchemy.orm import Session
from passlib.hash import bcrypt

from .models import User


def create_user(db: Session, email: str, password: str) -> User:
    """Create a user with hashed password."""
    user = User(email=email, password_hash=bcrypt.hash(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Return user if credentials are valid."""
    user = db.query(User).filter(User.email == email).first()
    if user and bcrypt.verify(password, user.password_hash):
        return user
    return None
