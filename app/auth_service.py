from sqlalchemy.exc import IntegrityError

from app.models import User
from app.security import create_access_token, hash_password, verify_password
from app.user_repository import UserRepository


class DuplicateUserError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    def register(self, email: str, password: str) -> User:
        if self.users.get_by_email(email) is not None:
            raise DuplicateUserError
        try:
            return self.users.create(email, hash_password(password))
        except IntegrityError as exc:
            self.users.session.rollback()
            raise DuplicateUserError from exc

    def login(self, email: str, password: str) -> str:
        user = self.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError
        return create_access_token(user.id)
