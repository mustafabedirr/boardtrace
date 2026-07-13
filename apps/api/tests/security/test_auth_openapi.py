import json

from boardtrace_api.app import create_app
from boardtrace_api.config import Settings

AUTH_PREFIX = "/api/v1/auth"


def response_schema(operation: dict[str, object], status_code: str) -> str:
    responses = operation["responses"]
    assert isinstance(responses, dict)
    response = responses[status_code]
    assert isinstance(response, dict)
    content = response["content"]
    assert isinstance(content, dict)
    body = content["application/json"]
    assert isinstance(body, dict)
    schema = body["schema"]
    assert isinstance(schema, dict)
    reference = schema["$ref"]
    assert isinstance(reference, str)
    return reference


def test_auth_openapi_contract_is_deterministic_and_hides_internal_models() -> None:
    app = create_app(Settings())
    document = app.openapi()
    assert document == app.openapi()

    paths = document["paths"]
    components = document["components"]
    assert isinstance(paths, dict)
    assert isinstance(components, dict)
    assert document["openapi"] == "3.1.0"
    assert document["info"] == {
        "title": "BoardTrace API",
        "description": "Backend API for post-game chess analysis.",
        "version": "0.1.0",
    }

    expected_operations = {
        "/register": ("post", "register_api_v1_auth_register_post"),
        "/login": ("post", "login_api_v1_auth_login_post"),
        "/refresh": ("post", "refresh_api_v1_auth_refresh_post"),
        "/logout": ("post", "logout_api_v1_auth_logout_post"),
        "/logout-all": ("post", "logout_all_api_v1_auth_logout_all_post"),
        "/me": ("get", "me_api_v1_auth_me_get"),
    }
    for suffix, (method, operation_id) in expected_operations.items():
        operation = paths[f"{AUTH_PREFIX}{suffix}"][method]
        assert operation["operationId"] == operation_id
        assert operation["tags"] == ["auth"]

    security_schemes = components["securitySchemes"]
    assert security_schemes == {
        "HTTPBearer": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    }
    for suffix in ("/logout-all", "/me"):
        operation = paths[f"{AUTH_PREFIX}{suffix}"]["post" if suffix == "/logout-all" else "get"]
        assert operation["security"] == [{"HTTPBearer": []}]
    for suffix in ("/register", "/login", "/refresh", "/logout"):
        assert "security" not in paths[f"{AUTH_PREFIX}{suffix}"]["post"]

    schemas = components["schemas"]
    assert isinstance(schemas, dict)
    assert schemas["RegisterRequest"]["properties"]["password"]["writeOnly"] is True
    assert schemas["LoginRequest"]["properties"]["password"]["writeOnly"] is True
    assert schemas["RefreshTokenRequest"]["properties"] == {
        "refresh_token": schemas["RefreshTokenRequest"]["properties"]["refresh_token"]
    }
    assert schemas["RefreshTokenRequest"]["properties"]["refresh_token"]["writeOnly"] is True
    assert set(schemas["TokenPairResponse"]["properties"]) == {
        "access_token",
        "refresh_token",
        "token_type",
        "expires_in",
    }
    assert set(schemas["UserResponse"]["properties"]) == {
        "id",
        "email",
        "is_active",
        "email_verified",
        "created_at",
    }
    serialized = json.dumps(document).lower()
    for internal_name in (
        "authsession",
        "password_hash",
        "token_digest",
        "family_id",
        "replaced_by_session_id",
        "bestmove",
        "evaluation",
        "principalvariation",
        "matescore",
    ):
        assert internal_name not in serialized


def test_auth_openapi_documents_success_headers_and_error_envelopes() -> None:
    paths = create_app(Settings()).openapi()["paths"]
    assert isinstance(paths, dict)

    for suffix in ("/register", "/login", "/refresh", "/logout", "/logout-all"):
        operation = paths[f"{AUTH_PREFIX}{suffix}"]["post"]
        headers = operation["responses"]["200"]["headers"]
        assert headers["Cache-Control"]["schema"]["const"] == "no-store"
        assert headers["Pragma"]["schema"]["const"] == "no-cache"

    expected_errors = {
        "/register": ("409", "422"),
        "/login": ("401", "422"),
        "/refresh": ("401", "422"),
        "/logout": ("422",),
        "/logout-all": ("401",),
        "/me": ("401",),
    }
    for suffix, status_codes in expected_errors.items():
        method = "post" if suffix != "/me" else "get"
        operation = paths[f"{AUTH_PREFIX}{suffix}"][method]
        for status_code in status_codes:
            assert response_schema(operation, status_code) == "#/components/schemas/ErrorResponse"
