"""`users` collection - authentication identities and their role."""

from datetime import datetime

from pydantic import EmailStr, Field

from app.models.common import DocumentModel, PyObjectId, utc_now
from app.models.enums import UserRole, UserStatus


class User(DocumentModel):
    email: EmailStr
    password_hash: str
    full_name: str
    role: UserRole
    status: UserStatus = UserStatus.ACTIVE
    phone: str | None = None
    #: Set only for CUSTOMER accounts: the `customers` document they act for.
    customer_id: PyObjectId | None = None
    last_login_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def is_customer(self) -> bool:
        return self.role == UserRole.CUSTOMER
