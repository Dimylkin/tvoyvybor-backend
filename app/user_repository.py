from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserRole


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email))

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def create(self, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash, role=UserRole.USER)
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user
