"""Authentication endpoints."""

from fastapi import APIRouter, status

from app.core.deps import CurrentUser, ManagerUser, RequestContext
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    StaffCreateRequest,
    TokenResponse,
    UserResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a customer account",
)
async def register(payload: RegisterRequest, context: RequestContext) -> TokenResponse:
    """Create a customer login and its linked customer record, then sign in."""
    return await auth_service.register_customer(payload, request_context=context)


@router.post("/login", response_model=TokenResponse, summary="Sign in")
async def login(payload: LoginRequest, context: RequestContext) -> TokenResponse:
    return await auth_service.login(payload, request_context=context)


@router.post("/refresh", response_model=TokenResponse, summary="Exchange a refresh token")
async def refresh(payload: RefreshRequest) -> TokenResponse:
    return await auth_service.refresh_tokens(payload.refresh_token)


@router.get("/me", summary="Current user and linked customer record")
async def me(principal: CurrentUser) -> dict:
    return await auth_service.get_profile(principal.id)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change your own password",
)
async def change_password(
    payload: ChangePasswordRequest, principal: CurrentUser
) -> None:
    await auth_service.change_password(
        principal.id, payload.current_password, payload.new_password
    )


@router.post(
    "/staff",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a sales employee or manager account",
)
async def create_staff(
    payload: StaffCreateRequest, principal: ManagerUser, context: RequestContext
) -> UserResponse:
    return await auth_service.create_staff_user(
        payload, actor=principal.as_actor(), request_context=context
    )
