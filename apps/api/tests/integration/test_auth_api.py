import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.models import AuthSession, User

pytestmark = [pytest.mark.database, pytest.mark.integration]

AUTH_PREFIX = "/api/v1/auth"
PASSWORD = "correct-horse-battery-staple"


def assert_no_store(response: httpx.Response) -> None:
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"


@pytest.mark.asyncio
async def test_register_validates_input_persists_user_and_maps_duplicate_email(
    auth_client: httpx.AsyncClient,
) -> None:
    response = await auth_client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": "Api.Register@example.com",
            "password": PASSWORD,
            "display_name": "API Register",
        },
    )
    payload = response.json()
    assert response.status_code == 200
    assert_no_store(response)
    assert set(payload) == {"access_token", "refresh_token", "token_type", "expires_in"}
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["refresh_token"]

    duplicate = await auth_client.post(
        f"{AUTH_PREFIX}/register",
        json={"email": "api.register@example.com", "password": PASSWORD},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "email_conflict"
    assert PASSWORD not in duplicate.text

    invalid = await auth_client.post(
        f"{AUTH_PREFIX}/register",
        json={"email": "not-an-email", "password": "short"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert "short" not in invalid.text


@pytest.mark.asyncio
async def test_login_and_me_enforce_bearer_authentication_and_inactive_users(
    auth_client: httpx.AsyncClient,
    auth_database_session: AsyncSession,
) -> None:
    registration = await auth_client.post(
        f"{AUTH_PREFIX}/register",
        json={"email": "api-login@example.com", "password": PASSWORD},
    )
    assert registration.status_code == 200
    login = await auth_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": "API-LOGIN@EXAMPLE.COM", "password": PASSWORD},
    )
    login_payload = login.json()
    assert login.status_code == 200
    assert_no_store(login)

    missing_credentials = await auth_client.get(f"{AUTH_PREFIX}/me")
    assert missing_credentials.status_code == 401
    assert missing_credentials.json()["error"]["code"] == "authentication_required"
    current_user = await auth_client.get(
        f"{AUTH_PREFIX}/me",
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )
    current_payload = current_user.json()
    assert current_user.status_code == 200
    assert current_payload["email"] == "api-login@example.com"
    assert current_payload["email_verified"] is False
    assert "password_hash" not in current_payload
    assert "refresh_token" not in current_payload

    wrong_password = await auth_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": "api-login@example.com", "password": "wrong-password-value"},
    )
    assert wrong_password.status_code == 401
    assert wrong_password.json()["error"]["code"] == "invalid_credentials"
    assert "wrong-password-value" not in wrong_password.text

    user = await auth_database_session.scalar(
        select(User).where(User.normalized_email == "api-login@example.com")
    )
    assert user is not None
    user.is_active = False
    await auth_database_session.commit()
    inactive_login = await auth_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": "api-login@example.com", "password": PASSWORD},
    )
    inactive_me = await auth_client.get(
        f"{AUTH_PREFIX}/me",
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )
    assert inactive_login.status_code == 401
    assert inactive_me.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_persisted_session_and_maps_unknown_tokens(
    auth_client: httpx.AsyncClient,
    auth_database_session: AsyncSession,
) -> None:
    registration = await auth_client.post(
        f"{AUTH_PREFIX}/register",
        json={"email": "api-refresh@example.com", "password": PASSWORD},
    )
    initial_pair = registration.json()
    assert registration.status_code == 200

    refreshed = await auth_client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": initial_pair["refresh_token"]},
    )
    refreshed_pair = refreshed.json()
    assert refreshed.status_code == 200
    assert_no_store(refreshed)
    assert refreshed_pair["refresh_token"] != initial_pair["refresh_token"]

    auth_database_session.expire_all()
    sessions = list((await auth_database_session.scalars(select(AuthSession))).all())
    assert len(sessions) == 2
    parent = next(
        auth_session for auth_session in sessions if auth_session.replaced_by_session_id is not None
    )
    replacement = next(
        auth_session
        for auth_session in sessions
        if auth_session.id == parent.replaced_by_session_id
    )
    assert parent.revoked_at is not None
    assert replacement.revoked_at is None
    assert replacement.family_id == parent.family_id
    initial_refresh_token = initial_pair["refresh_token"]
    refreshed_refresh_token = refreshed_pair["refresh_token"]
    assert all(initial_refresh_token not in auth_session.token_digest for auth_session in sessions)
    assert all(
        refreshed_refresh_token not in auth_session.token_digest for auth_session in sessions
    )

    unknown = await auth_client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": "x" * 64},
    )
    assert unknown.status_code == 401
    assert unknown.json()["error"]["code"] == "invalid_refresh_token"


@pytest.mark.asyncio
async def test_logout_revokes_only_the_requested_refresh_session(
    auth_client: httpx.AsyncClient,
) -> None:
    registration = await auth_client.post(
        f"{AUTH_PREFIX}/register",
        json={"email": "api-logout@example.com", "password": PASSWORD},
    )
    target_pair = registration.json()
    sibling_login = await auth_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": "api-logout@example.com", "password": PASSWORD},
    )
    sibling_pair = sibling_login.json()
    assert registration.status_code == 200
    assert sibling_login.status_code == 200

    logout = await auth_client.post(
        f"{AUTH_PREFIX}/logout",
        json={"refresh_token": target_pair["refresh_token"]},
    )
    assert logout.status_code == 200
    assert logout.json() == {"success": True}
    assert_no_store(logout)

    target_refresh = await auth_client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": target_pair["refresh_token"]},
    )
    sibling_refresh = await auth_client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": sibling_pair["refresh_token"]},
    )
    assert target_refresh.status_code == 401
    assert sibling_refresh.status_code == 200


@pytest.mark.asyncio
async def test_logout_all_is_bearer_scoped_and_preserves_other_users_sessions(
    auth_client: httpx.AsyncClient,
) -> None:
    first_registration = await auth_client.post(
        f"{AUTH_PREFIX}/register",
        json={"email": "api-logout-all@example.com", "password": PASSWORD},
    )
    first_pair = first_registration.json()
    first_login = await auth_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": "api-logout-all@example.com", "password": PASSWORD},
    )
    first_login_pair = first_login.json()
    second_registration = await auth_client.post(
        f"{AUTH_PREFIX}/register",
        json={"email": "api-logout-all-other@example.com", "password": PASSWORD},
    )
    second_pair = second_registration.json()
    assert first_registration.status_code == 200
    assert first_login.status_code == 200
    assert second_registration.status_code == 200

    logout_all = await auth_client.post(
        f"{AUTH_PREFIX}/logout-all",
        headers={"Authorization": f"Bearer {first_pair['access_token']}"},
    )
    assert logout_all.status_code == 200
    assert logout_all.json() == {"success": True}
    assert_no_store(logout_all)

    first_refresh = await auth_client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": first_pair["refresh_token"]},
    )
    first_login_refresh = await auth_client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": first_login_pair["refresh_token"]},
    )
    second_refresh = await auth_client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": second_pair["refresh_token"]},
    )
    assert first_refresh.status_code == 401
    assert first_login_refresh.status_code == 401
    assert second_refresh.status_code == 200
