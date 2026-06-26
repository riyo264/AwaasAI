"""JWT Auth Middleware — Validates Cognito JWTs at the gateway level for local dev."""

import json
import logging

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from gateway.jwks_cache import JWKSCache, JWKSFetchError, KeyNotFoundError

logger = logging.getLogger(__name__)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Validates Cognito JWTs at the gateway level.

    - Skips validation for public paths (/, /health, /services/health)
    - Skips validation entirely when auth_enabled is False
    - Validates JWT signature, issuer, audience/client_id, and expiration
    - Injects X-User-Sub and X-User-Email headers for downstream services
    """

    PUBLIC_PATHS = {"/", "/health", "/services/health"}

    def __init__(self, app, *, auth_enabled: bool, cognito_issuer: str,
                 cognito_app_client_id: str, jwks_cache: JWKSCache):
        super().__init__(app)
        self._auth_enabled = auth_enabled
        self._cognito_issuer = cognito_issuer
        self._cognito_app_client_id = cognito_app_client_id
        self._jwks_cache = jwks_cache

    async def dispatch(self, request: Request, call_next):
        # Skip all validation when auth is disabled
        if not self._auth_enabled:
            return await call_next(request)

        # Skip validation for public paths
        if self._is_public(request.url.path):
            return await call_next(request)

        # Extract token
        token = self._extract_token(request)
        if token is None:
            return self._error_response(
                401, "Missing or invalid Authorization header"
            )

        # Validate token
        try:
            claims = await self._validate_token(token)
        except _AuthError as exc:
            return self._error_response(exc.status_code, exc.detail)

        # Inject identity headers for downstream services
        sub = claims.get("sub", "")
        email = claims.get("email", "")

        # Modify request headers by creating a mutable scope
        headers = dict(request.scope["headers"])
        new_headers = list(request.scope["headers"])
        new_headers.append((b"x-user-sub", sub.encode()))
        new_headers.append((b"x-user-email", email.encode()))
        request.scope["headers"] = new_headers

        return await call_next(request)

    def _is_public(self, path: str) -> bool:
        """Check if the path is a public path that doesn't require auth."""
        return path in self.PUBLIC_PATHS

    def _extract_token(self, request: Request) -> str | None:
        """Extract Bearer token from Authorization header.

        Returns the token string, or None if header is missing/malformed.
        """
        auth_header = request.headers.get("authorization")
        if not auth_header:
            return None

        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        token = parts[1].strip()
        if not token:
            return None

        return token

    async def _validate_token(self, token: str) -> dict:
        """Validate JWT signature, issuer, audience, and expiration.

        Returns the decoded claims dict on success.
        Raises _AuthError on failure.
        """
        # Decode header to get kid
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.exceptions.DecodeError:
            raise _AuthError(401, "Token signature verification failed")

        kid = unverified_header.get("kid")
        if not kid:
            raise _AuthError(401, "Token signature verification failed")

        # Get the public key from JWKS cache
        try:
            public_key = await self._jwks_cache.get_key(kid)
        except JWKSFetchError:
            raise _AuthError(503, "Authentication service unavailable")
        except KeyNotFoundError:
            raise _AuthError(401, "Token signature verification failed")

        # Decode and verify the token
        # Cognito access tokens use client_id claim instead of aud
        try:
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=self._cognito_issuer,
                options={"verify_aud": False},
            )
        except jwt.ExpiredSignatureError:
            raise _AuthError(401, "Token has expired")
        except jwt.InvalidIssuerError:
            raise _AuthError(401, "Invalid token issuer")
        except jwt.InvalidSignatureError:
            raise _AuthError(401, "Token signature verification failed")
        except jwt.DecodeError:
            raise _AuthError(401, "Token signature verification failed")
        except jwt.InvalidTokenError:
            raise _AuthError(401, "Token signature verification failed")

        # Manually verify client_id (Cognito access tokens use this instead of aud)
        token_client_id = claims.get("client_id") or claims.get("aud")
        if token_client_id != self._cognito_app_client_id:
            raise _AuthError(401, "Invalid token audience")

        return claims

    @staticmethod
    def _error_response(status_code: int, detail: str) -> Response:
        """Build a JSON error response with appropriate headers."""
        headers = {}
        if status_code == 401:
            headers["WWW-Authenticate"] = "Bearer"

        return Response(
            content=json.dumps({"detail": detail}),
            status_code=status_code,
            media_type="application/json",
            headers=headers,
        )


class _AuthError(Exception):
    """Internal exception for auth validation failures."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)
