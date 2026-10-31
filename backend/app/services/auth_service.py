"""Registration, login and token refresh."""

from __future__ import annotations

from typing import Any

from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.mongo import Collections, get_collection
from app.models.common import object_id, utc_now
from app.models.customer import Address, Customer
from app.models.enums import AuditAction, CustomerStatus, UserRole, UserStatus
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    StaffCreateRequest,
    TokenResponse,
    UserResponse,
)
from app.services import audit_service, numbering
from app.utils.money import decode_decimals, encode_decimals


def _user_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user.model_dump())


def _issue_tokens(user: User) -> TokenResponse:
    claims = {"role": user.role, "email": user.email}
    if user.customer_id:
        claims["customer_id"] = user.customer_id
    return TokenResponse(
        access_token=create_access_token(str(user.id), claims),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.access_token_expire_minutes * 60,
        user=_user_response(user),
    )


async def get_user_by_email(email: str) -> User | None:
    raw = await get_collection(Collections.USERS).find_one(
        {"email": email.strip().lower()}
    )
    return User.from_mongo(raw)


async def get_user_by_id(user_id: str) -> User | None:
    raw = await get_collection(Collections.USERS).find_one({"_id": object_id(user_id)})
    return User.from_mongo(raw)


async def register_customer(
    payload: RegisterRequest, *, request_context: dict[str, Any] | None = None
) -> TokenResponse:
    """Create a CUSTOMER user together with the customer record it acts for.

    Both documents are written so a self-registered customer is immediately a
    first-class commercial party, not a half-provisioned login.
    """
    email = payload.email.strip().lower()
    if await get_user_by_email(email):
        raise ConflictError("An account with that email address already exists.")

    customers = get_collection(Collections.CUSTOMERS)
    if await customers.find_one({"email": email}):
        raise ConflictError("A customer record with that email address already exists.")

    address = None
    if payload.address_line1 or payload.city:
        address = Address(
            line1=payload.address_line1 or "",
            city=payload.city or "",
            state=payload.state or "",
            postal_code=payload.postal_code or "",
        )

    customer = Customer(
        code=await numbering.next_document_number("CUST", width=4),
        company_name=payload.company_name,
        contact_name=payload.full_name,
        email=email,
        phone=payload.phone,
        status=CustomerStatus.ACTIVE,
        billing_address=address,
        tax_id=payload.tax_id,
    )
    customer_result = await customers.insert_one(
        encode_decimals(customer.model_dump(exclude={"id"}))
    )
    customer_id = str(customer_result.inserted_id)

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.CUSTOMER,
        phone=payload.phone,
        customer_id=customer_id,
    )
    try:
        user_result = await get_collection(Collections.USERS).insert_one(
            user.model_dump(exclude={"id"})
        )
    except DuplicateKeyError as exc:
        # Lost a race on the unique email index: roll the customer record back so
        # we do not leave an orphan behind.
        await customers.delete_one({"_id": customer_result.inserted_id})
        raise ConflictError("An account with that email address already exists.") from exc

    user.id = str(user_result.inserted_id)

    await audit_service.record(
        action=AuditAction.USER_REGISTERED,
        entity_type="user",
        entity_id=user.id,
        summary=f"Customer account registered for {payload.company_name}.",
        actor={"id": user.id, "email": email, "role": UserRole.CUSTOMER.value},
        metadata={"customer_id": customer_id, "customer_code": customer.code},
        **(request_context or {}),
    )
    await audit_service.record(
        action=AuditAction.CUSTOMER_CREATED,
        entity_type="customer",
        entity_id=customer_id,
        summary=f"Customer {customer.code} created by self-registration.",
        actor={"id": user.id, "email": email, "role": UserRole.CUSTOMER.value},
        **(request_context or {}),
    )

    return _issue_tokens(user)


async def create_staff_user(
    payload: StaffCreateRequest,
    *,
    actor: dict[str, Any],
    request_context: dict[str, Any] | None = None,
) -> UserResponse:
    """Provision a sales employee or manager account."""
    if payload.role == UserRole.CUSTOMER:
        raise PermissionDeniedError(
            "Customer accounts are created through the registration endpoint."
        )

    email = payload.email.strip().lower()
    if await get_user_by_email(email):
        raise ConflictError("An account with that email address already exists.")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        phone=payload.phone,
    )
    result = await get_collection(Collections.USERS).insert_one(
        user.model_dump(exclude={"id"})
    )
    user.id = str(result.inserted_id)

    await audit_service.record(
        action=AuditAction.USER_REGISTERED,
        entity_type="user",
        entity_id=user.id,
        summary=f"{payload.role} account created for {payload.full_name}.",
        actor=actor,
        metadata={"role": payload.role},
        **(request_context or {}),
    )
    return _user_response(user)


async def login(
    payload: LoginRequest, *, request_context: dict[str, Any] | None = None
) -> TokenResponse:
    user = await get_user_by_email(payload.email)

    # Verify against a dummy hash when the user is unknown so that a missing
    # account and a wrong password take comparable time.
    stored_hash = user.password_hash if user else hash_password("not-a-real-password")
    password_ok = verify_password(payload.password, stored_hash)

    if user is None or not password_ok:
        raise AuthenticationError("The email address or password is incorrect.")
    if user.status != UserStatus.ACTIVE:
        raise AuthenticationError("This account has been suspended.")

    now = utc_now()
    await get_collection(Collections.USERS).update_one(
        {"_id": object_id(str(user.id))},
        {"$set": {"last_login_at": now, "updated_at": now}},
    )
    user.last_login_at = now

    await audit_service.record(
        action=AuditAction.USER_LOGGED_IN,
        entity_type="user",
        entity_id=str(user.id),
        summary=f"{user.email} signed in.",
        actor={"id": str(user.id), "email": user.email, "role": user.role},
        **(request_context or {}),
    )
    return _issue_tokens(user)


async def refresh_tokens(refresh_token: str) -> TokenResponse:
    payload = decode_token(refresh_token, expected_type="refresh")
    user = await get_user_by_id(payload["sub"])
    if user is None:
        raise AuthenticationError("The account linked to this token no longer exists.")
    if user.status != UserStatus.ACTIVE:
        raise AuthenticationError("This account has been suspended.")
    return _issue_tokens(user)


async def change_password(
    user_id: str, current_password: str, new_password: str
) -> None:
    user = await get_user_by_id(user_id)
    if user is None:
        raise NotFoundError("User not found.")
    if not verify_password(current_password, user.password_hash):
        raise AuthenticationError("The current password is incorrect.")

    await get_collection(Collections.USERS).update_one(
        {"_id": object_id(user_id)},
        {"$set": {"password_hash": hash_password(new_password), "updated_at": utc_now()}},
    )


async def get_profile(user_id: str) -> dict[str, Any]:
    """Current user plus, for a customer, the customer record they act for."""
    user = await get_user_by_id(user_id)
    if user is None:
        raise NotFoundError("User not found.")

    profile: dict[str, Any] = {"user": _user_response(user), "customer": None}
    if user.customer_id:
        raw = await get_collection(Collections.CUSTOMERS).find_one(
            {"_id": object_id(user.customer_id)}
        )
        if raw:
            # Return the same shape the customer endpoints do. The bare Customer
            # model would omit available_credit, because that is a Python
            # property and Pydantic does not serialise properties - which left
            # the client with no figure to show.
            from app.services import customer_service

            profile["customer"] = customer_service.to_response(
                Customer.from_mongo(decode_decimals(raw))
            )
    return profile
