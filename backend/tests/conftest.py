"""Shared test fixtures.

The environment is pointed at a dedicated ``quoteflow_test`` database *before*
any application module is imported, because ``app.core.config.settings`` is a
module-level singleton. Collections are cleared between tests so each one starts
from a known state.
"""

import os
import tempfile
from pathlib import Path

# Must precede every app import: settings are read once, at import time.
os.environ["MONGODB_DB_NAME"] = "quoteflow_test"
# Render test PDFs into a temp directory rather than the project's storage
# folder, so a test run leaves no artefacts behind in the repository.
os.environ["PDF_STORAGE_DIR"] = str(
    Path(tempfile.gettempdir()) / "quoteflow-test-pdfs"
)
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-quoteflow-tests"
os.environ["VERIFICATION_SECRET"] = "test-verification-secret"
os.environ["APP_ENV"] = "test"
# DEBUG logging turns the driver's command log on, which buries test failures.
os.environ["DEBUG"] = "false"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.indexes import ensure_indexes  # noqa: E402
from app.db.mongo import (  # noqa: E402
    Collections,
    close_mongo_connection,
    connect_to_mongo,
    get_collection,
)
from app.main import create_app  # noqa: E402
from app.models.customer import Address, Customer  # noqa: E402
from app.models.enums import CustomerTier, ProductStatus, UserRole  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import settings_service  # noqa: E402
from app.utils.money import encode_decimals  # noqa: E402

TEST_PASSWORD = "TestPassw0rd!"


def _guard_database_name() -> None:
    """Refuse to run if the tests are pointed at a non-test database."""
    if "test" not in settings.mongodb_db_name:
        raise RuntimeError(
            f"Refusing to run tests against {settings.mongodb_db_name!r}: the "
            f"database name must contain 'test'."
        )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def database():
    _guard_database_name()
    db = await connect_to_mongo()
    await ensure_indexes(db)
    yield db
    # Drop the whole test database so repeated runs do not accumulate data.
    client = db.client
    await client.drop_database(settings.mongodb_db_name)
    await close_mongo_connection()


@pytest_asyncio.fixture(autouse=True)
async def clean_collections(database):
    """Empty every collection before each test."""
    for name in Collections.all():
        await database[name].delete_many({})
    await settings_service.initialise_settings()
    # The settings cache is per-call, but the counters are not: resetting them
    # keeps document numbers predictable inside a test.
    yield


@pytest_asyncio.fixture(scope="session")
async def app(database):
    # create_app() installs a lifespan that would open a second connection; the
    # database fixture already owns one, so the app is used without it.
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        yield async_client


# ---------------------------------------------------------------------------
# Data builders
# ---------------------------------------------------------------------------


async def create_user(
    *,
    email: str,
    role: UserRole,
    full_name: str = "Test User",
    customer_id: str | None = None,
    password: str = TEST_PASSWORD,
) -> dict:
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
        customer_id=customer_id,
    )
    result = await get_collection(Collections.USERS).insert_one(
        user.model_dump(exclude={"id"})
    )
    return {"id": str(result.inserted_id), "email": email, "password": password}


async def create_customer(
    *,
    code: str = "CUST-TEST-1",
    company_name: str = "Test Industries",
    email: str = "buyer@test.example",
    tier: CustomerTier = CustomerTier.STANDARD,
    credit_limit: str = "0.00",
    status: str | None = None,
) -> str:
    payload: dict = {
        "code": code,
        "company_name": company_name,
        "contact_name": "Test Buyer",
        "email": email,
        "phone": "+91 90000 00000",
        "tier": tier.value,
        "credit_limit": credit_limit,
        "billing_address": Address(
            line1="1 Test Road",
            city="Pune",
            state="Maharashtra",
            postal_code="411001",
        ),
    }
    if status:
        payload["status"] = status
    customer = Customer.model_validate(payload)
    result = await get_collection(Collections.CUSTOMERS).insert_one(
        encode_decimals(customer.model_dump(exclude={"id"}))
    )
    return str(result.inserted_id)


async def create_product(
    *,
    sku: str = "TEST-001",
    name: str = "Test Widget",
    unit_price: str = "1000.00",
    cost_price: str = "600.00",
    stock_quantity: int = 500,
    reserved_quantity: int = 0,
    category: str = "Testing",
    status: ProductStatus = ProductStatus.ACTIVE,
    max_discount_percent: str | None = None,
    tax_rate: str | None = None,
    lead_time_days: int = 5,
    reorder_level: int = 0,
) -> str:
    product = Product.model_validate(
        {
            "sku": sku,
            "name": name,
            "category": category,
            "unit_price": unit_price,
            "cost_price": cost_price,
            "stock_quantity": stock_quantity,
            "reserved_quantity": reserved_quantity,
            "reorder_level": reorder_level,
            "status": status.value,
            "max_discount_percent": max_discount_percent,
            "tax_rate": tax_rate,
            "lead_time_days": lead_time_days,
        }
    )
    result = await get_collection(Collections.PRODUCTS).insert_one(
        encode_decimals(product.model_dump(exclude={"id"}))
    )
    return str(result.inserted_id)


# ---------------------------------------------------------------------------
# Authenticated actors
# ---------------------------------------------------------------------------


async def _login(client: AsyncClient, email: str, password: str = TEST_PASSWORD) -> str:
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class Actor:
    """A logged-in user plus the headers needed to act as them."""

    def __init__(self, user_id: str, email: str, token: str, customer_id: str | None = None):
        self.id = user_id
        self.email = email
        self.token = token
        self.customer_id = customer_id
        self.headers = auth(token)


@pytest_asyncio.fixture
async def manager(client) -> Actor:
    user = await create_user(
        email="manager@test.example", role=UserRole.SALES_MANAGER, full_name="Test Manager"
    )
    return Actor(user["id"], user["email"], await _login(client, user["email"]))


@pytest_asyncio.fixture
async def employee(client) -> Actor:
    user = await create_user(
        email="employee@test.example",
        role=UserRole.SALES_EMPLOYEE,
        full_name="Test Employee",
    )
    return Actor(user["id"], user["email"], await _login(client, user["email"]))


@pytest_asyncio.fixture
async def customer_actor(client) -> Actor:
    customer_id = await create_customer()
    user = await create_user(
        email="buyer@test.example",
        role=UserRole.CUSTOMER,
        full_name="Test Buyer",
        customer_id=customer_id,
    )
    return Actor(
        user["id"],
        user["email"],
        await _login(client, user["email"]),
        customer_id=customer_id,
    )


@pytest.fixture
def widget_factory():
    """Expose the product builder to tests that need several products."""
    return create_product
