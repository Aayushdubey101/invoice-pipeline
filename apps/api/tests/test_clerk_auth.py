"""Phase 14.8 — Clerk bearer-token verification (locally-signed JWT + stubbed JWKS)."""

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from invoice_pipeline.api.deps import get_current_workspace
from invoice_pipeline.api.main import app
from invoice_pipeline.auth import clerk
from invoice_pipeline.auth.clerk import ClerkTokenInvalid, verify_clerk_token
from invoice_pipeline.config import settings
from invoice_pipeline.db.models import Base, Workspace
from invoice_pipeline.db.session import get_session

TEST_ISSUER = "https://test.clerk.accounts.dev"
TEST_KID = "test-kid-1"


@pytest.fixture(scope="module")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture(autouse=True)
def clerk_settings(monkeypatch):
    monkeypatch.setattr(settings, "CLERK_ISSUER", TEST_ISSUER)
    monkeypatch.setattr(settings, "CLERK_AUDIENCE", "")
    monkeypatch.setattr(
        settings, "CLERK_JWKS_URL", "https://test.clerk.accounts.dev/.well-known/jwks.json"
    )


@pytest.fixture(autouse=True)
def stub_jwks(rsa_keypair, monkeypatch):
    _, public_key = rsa_keypair
    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = TEST_KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    jwks = {"keys": [jwk]}

    async def fake_get_jwks(force_refresh: bool = False) -> dict:
        return jwks

    monkeypatch.setattr(clerk, "_get_jwks", fake_get_jwks)
    clerk._jwks_cache = None
    clerk._jwks_cache_at = 0.0
    yield


def make_token(rsa_keypair, *, sub="user_abc123", issuer=TEST_ISSUER, exp_offset=3600, kid=TEST_KID):
    private_key, _ = rsa_keypair
    now = int(time.time())
    payload = {"sub": sub, "iss": issuer, "iat": now, "exp": now + exp_offset}
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


@pytest.mark.asyncio
async def test_verify_clerk_token_valid(rsa_keypair):
    token = make_token(rsa_keypair)
    clerk_user_id = await verify_clerk_token(token)
    assert clerk_user_id == "user_abc123"


@pytest.mark.asyncio
async def test_verify_clerk_token_expired(rsa_keypair):
    token = make_token(rsa_keypair, exp_offset=-60)
    with pytest.raises(ClerkTokenInvalid):
        await verify_clerk_token(token)


@pytest.mark.asyncio
async def test_verify_clerk_token_wrong_issuer(rsa_keypair):
    token = make_token(rsa_keypair, issuer="https://someone-else.clerk.accounts.dev")
    with pytest.raises(ClerkTokenInvalid):
        await verify_clerk_token(token)


@pytest.mark.asyncio
async def test_verify_clerk_token_malformed():
    with pytest.raises(ClerkTokenInvalid):
        await verify_clerk_token("not-a-jwt")


@pytest.mark.asyncio
async def test_verify_clerk_token_unknown_kid(rsa_keypair):
    token = make_token(rsa_keypair, kid="unknown-kid")
    with pytest.raises(ClerkTokenInvalid):
        await verify_clerk_token(token)


# ── get_current_workspace: Bearer path resolves/creates, guest fallback intact ──


@pytest.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bearer_token_get_or_creates_authenticated_workspace(
    db_session: AsyncSession, rsa_keypair
) -> None:
    token = make_token(rsa_keypair, sub="user_reuse_me")
    scope = {"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]}
    request = Request(scope)

    workspace = await get_current_workspace(request, db_session)
    assert workspace.workspace_type == "authenticated"
    assert workspace.clerk_user_id == "user_reuse_me"

    # Second call reuses the same row — no duplicate created.
    workspace_again = await get_current_workspace(request, db_session)
    assert workspace_again.id == workspace.id

    all_ws = (await db_session.execute(select(Workspace))).scalars().all()
    assert len(all_ws) == 1


@pytest.mark.asyncio
async def test_bearer_token_via_http_resolves_self_on_get_workspace(
    client: AsyncClient, db_session: AsyncSession, rsa_keypair
) -> None:
    token = make_token(rsa_keypair, sub="user_http_flow")
    headers = {"Authorization": f"Bearer {token}"}

    # First call creates the authenticated workspace lazily (no explicit id known yet).
    scope = {"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]}
    created = await get_current_workspace(Request(scope), db_session)

    res = await client.get(f"/workspaces/{created.id}", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == created.id
    assert body["workspace_type"] == "authenticated"

    # A different Clerk user must not be able to fetch this workspace.
    other_token = make_token(rsa_keypair, sub="user_someone_else")
    res_other = await client.get(
        f"/workspaces/{created.id}", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert res_other.status_code == 404


@pytest.mark.asyncio
async def test_guest_fallback_still_works_without_bearer(client: AsyncClient) -> None:
    res = await client.post("/workspaces")
    assert res.status_code == 201
    ws_id = res.json()["id"]

    res2 = await client.get(f"/workspaces/{ws_id}", headers={"X-Workspace-Id": ws_id})
    assert res2.status_code == 200


@pytest.mark.asyncio
async def test_missing_bearer_and_missing_header_is_401(client: AsyncClient) -> None:
    res = await client.get("/workspaces/some-id")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_invalid_bearer_token_is_401(client: AsyncClient) -> None:
    res = await client.get(
        "/workspaces/some-id", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert res.status_code == 401
