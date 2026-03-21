"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, verify_token
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/auth", tags=["Authentication"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
limiter = Limiter(key_func=get_remote_address)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate and return a JWT token."""
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    if not user or not pwd_context.verify(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated"
        )

    token = create_access_token(
        data={"sub": str(user.id), "role": user.role.value, "username": user.username}
    )
    return TokenResponse(access_token=token)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    token_data: dict = Depends(verify_token),
):
    """Register a new analyst (requires admin or compliance_officer role)."""
    allowed_roles = {UserRole.ADMIN.value, UserRole.COMPLIANCE_OFFICER.value}
    if token_data.get("role") not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or compliance_officer can register new users",
        )
    user = User(
        username=data.username,
        email=data.email,
        full_name=data.full_name,
        hashed_password=pwd_context.hash(data.password),
        role=data.role,
    )
    db.add(user)
    await db.flush()

    # Audit log
    audit = AuditService(db)
    await audit.log(
        action="user_created",
        resource_type="user",
        resource_id=str(user.id),
        user_id=token_data.get("sub"),
        username=token_data.get("username"),
        details={"new_username": data.username, "role": data.role.value if hasattr(data.role, "value") else str(data.role)},
    )

    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def get_me(
    token_data: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Get the current authenticated user."""
    from uuid import UUID

    result = await db.execute(
        select(User).where(User.id == UUID(token_data["sub"]))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserResponse.model_validate(user)
