import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.auth_service import AuthService, DuplicateUserError, InvalidCredentialsError
from app.database import get_session
from app.models import User, UserRole
from app.security import parse_access_token
from app.user_repository import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("Invalid email")
        return email


class LoginCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=320)
    password: str = Field(max_length=128)


class UserResponse(BaseModel):
    id: int
    email: str
    role: UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


SessionDep = Annotated[Session, Depends(get_session)]


def current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    user_id = parse_access_token(credentials.credentials) if credentials else None
    user = UserRepository(session).get_by_id(user_id) if user_id else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


@router.post("/register", response_model=UserResponse, status_code=201)
def register(data: Credentials, session: SessionDep) -> User:
    try:
        return AuthService(UserRepository(session)).register(data.email, data.password)
    except DuplicateUserError as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc


@router.post("/login", response_model=TokenResponse)
def login(data: LoginCredentials, session: SessionDep) -> TokenResponse:
    try:
        token = AuthService(UserRepository(session)).login(
            data.email.strip().lower(), data.password
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail="Invalid credentials") from exc
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(user: Annotated[User, Depends(current_user)]) -> User:
    return user
