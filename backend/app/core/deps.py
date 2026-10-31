"""FastAPI dependencies: the authenticated principal and the role guards.

Note: this module must not use ``from __future__ import annotations``.
:class:`RequireRoles` is used as a callable instance, and FastAPI resolves a
dependency's type hints against ``callable.__globals__`` - which an instance does
not have - so a stringised annotation on ``__call__`` would never resolve.
"""

from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_token
from app.models.enums import UserRole, UserStatus
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")


class Principal:
    """The authenticated caller, as the API layer sees them."""

    def __init__(self, user: User) -> None:
        self.user = user
        self.id = str(user.id)
        self.email = user.email
        self.role = UserRole(user.role)
        self.full_name = user.full_name
        self.customer_id = user.customer_id

    @property
    def is_customer(self) -> bool:
        return self.role == UserRole.CUSTOMER

    @property
    def is_manager(self) -> bool:
        return self.role == UserRole.SALES_MANAGER

    @property
    def is_staff(self) -> bool:
        return self.role in {UserRole.SALES_EMPLOYEE, UserRole.SALES_MANAGER}

    def as_actor(self) -> dict[str, Any]:
        """Shape the audit service expects."""
        return {"id": self.id, "email": self.email, "role": self.role.value}


async def get_current_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> Principal:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("An access token is required.")

    payload = decode_token(credentials.credentials, expected_type="access")

    # Load the user on every request rather than trusting the token's claims, so
    # a suspension or role change takes effect immediately instead of at expiry.
    from app.services import auth_service

    user = await auth_service.get_user_by_id(payload["sub"])
    if user is None:
        raise AuthenticationError("The account linked to this token no longer exists.")
    if user.status != UserStatus.ACTIVE:
        raise AuthenticationError("This account has been suspended.")
    return Principal(user)


CurrentUser = Annotated[Principal, Depends(get_current_principal)]


class RequireRoles:
    """Dependency factory that admits only the listed roles.

    Usage::

        @router.get("/", dependencies=[Depends(RequireRoles(UserRole.SALES_MANAGER))])
    """

    def __init__(self, *roles: UserRole) -> None:
        self.roles = set(roles)

    async def __call__(self, principal: CurrentUser) -> Principal:
        if principal.role not in self.roles:
            allowed = ", ".join(sorted(role.value for role in self.roles))
            raise PermissionDeniedError(
                f"This action requires one of the following roles: {allowed}."
            )
        return principal


class RequireManagerAuthority:
    """Admits sales staff, but lets only a manager through.

    Distinct from ``RequireRoles(UserRole.SALES_MANAGER)`` only in the refusal
    it raises: adding master data is something a sales employee *may* ask for,
    just not do, so the error names the route that asks instead of stopping at
    "you need another role". The permission boundary is identical.
    """

    def __init__(self, action: str, submit_route: str) -> None:
        self.action = action
        self.submit_route = submit_route

    async def __call__(self, principal: CurrentUser) -> Principal:
        if principal.role == UserRole.SALES_MANAGER:
            return principal
        if principal.role == UserRole.SALES_EMPLOYEE:
            raise PermissionDeniedError(
                f"Only a sales manager may {self.action} directly. Submit it for "
                f"approval at POST {self.submit_route}.",
                details={"submit_route": self.submit_route},
            )
        raise PermissionDeniedError(
            f"This action requires one of the following roles: "
            f"{UserRole.SALES_MANAGER.value}."
        )


require_customer = RequireRoles(UserRole.CUSTOMER)
require_sales_employee = RequireRoles(UserRole.SALES_EMPLOYEE)
require_manager = RequireRoles(UserRole.SALES_MANAGER)
require_staff = RequireRoles(UserRole.SALES_EMPLOYEE, UserRole.SALES_MANAGER)
require_any_role = RequireRoles(
    UserRole.CUSTOMER, UserRole.SALES_EMPLOYEE, UserRole.SALES_MANAGER
)

#: Creating master data is manager-only; an employee is pointed at the queue.
require_customer_authority = RequireManagerAuthority(
    "add a customer", "/api/v1/master-data-requests/customers"
)
require_product_authority = RequireManagerAuthority(
    "add a product", "/api/v1/master-data-requests/products"
)

CustomerUser = Annotated[Principal, Depends(require_customer)]
StaffUser = Annotated[Principal, Depends(require_staff)]
ManagerUser = Annotated[Principal, Depends(require_manager)]
CustomerAuthority = Annotated[Principal, Depends(require_customer_authority)]
ProductAuthority = Annotated[Principal, Depends(require_product_authority)]


def get_request_context(request: Request) -> dict[str, Any]:
    """Client metadata attached to audit entries."""
    forwarded = request.headers.get("x-forwarded-for")
    ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else None)
    )
    return {
        "ip_address": ip,
        "user_agent": request.headers.get("user-agent"),
    }


RequestContext = Annotated[dict, Depends(get_request_context)]
