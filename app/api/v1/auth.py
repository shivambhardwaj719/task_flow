from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.core.auth import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import Token, UserCreate, UserLogin, UserOut

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    """Register a new user account.

    Passwords are automatically hashed with bcrypt before storing.
    Plain passwords are never returned or logged.
    """
    existing_user = (
        db.query(User)
        .filter(or_(User.email == user_in.email, User.username == user_in.username))
        .first()
    )

    if existing_user:
        if existing_user.email == user_in.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address already exists.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this username already exists.",
        )

    new_user = User(
        email=user_in.email,
        username=user_in.username,
        hashed_password=hash_password(user_in.password),
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/login", response_model=Token)
def login(login_in: UserLogin, db: Session = Depends(get_db)):
    """Authenticate a user using email or username and password.

    Returns a signed JWT bearer token and user profile.
    """
    user = (
        db.query(User)
        .filter(
            or_(
                User.email == login_in.username_or_email,
                User.username == login_in.username_or_email,
            )
        )
        .first()
    )

    if not user or not verify_password(login_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User account is inactive"
        )

    access_token = create_access_token(
        subject=user.id, extra_claims={"username": user.username, "email": user.email}
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user,
    )


@router.get("/me", response_model=UserOut)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return current_user
