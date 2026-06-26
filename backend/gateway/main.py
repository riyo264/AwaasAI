"""
API Gateway — Single entry point that routes to all microservices.

In production, this would be replaced by AWS API Gateway / ALB with
path-based routing rules. For local dev, this FastAPI app proxies
requests to each service, simulating load-balanced routing.
"""
import logging
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from gateway.jwks_cache import JWKSCache
from gateway.auth_middleware import JWTAuthMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MoodSense AI — API Gateway",
    description="Routes requests to microservices. Simulates ALB path-based routing.",
    version="1.0.0",
)

# Auth middleware is added FIRST so it runs BEFORE the proxy handler.
# CORS middleware is added AFTER (Starlette processes middleware in reverse order),
# meaning CORS runs first → auth runs second → route handler runs last.
# This ensures CORS preflight OPTIONS requests are handled without requiring auth.
if settings.cognito_user_pool_id:
    jwks_cache = JWKSCache(
        jwks_url=settings.jwks_url,
        cache_ttl_seconds=settings.jwks_cache_ttl_seconds,
    )
    app.add_middleware(
        JWTAuthMiddleware,
        auth_enabled=settings.auth_enabled,
        cognito_issuer=settings.cognito_issuer,
        cognito_app_client_id=settings.cognito_app_client_id,
        jwks_cache=jwks_cache,
    )
else:
    logger.warning(
        "COGNITO_USER_POOL_ID not set — JWT auth middleware disabled. "
        "All requests will pass through without authentication."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service registry — uses environment variables so Docker can override with container names
import os

SERVICES = {
    "mood": os.environ.get("MOOD_SERVICE_URL", "http://localhost:8001"),
    "behavior": os.environ.get("BEHAVIOR_SERVICE_URL", "http://localhost:8002"),
    "patterns": os.environ.get("PATTERNS_SERVICE_URL", "http://localhost:8003"),
    "devices": os.environ.get("DEVICES_SERVICE_URL", "http://localhost:8004"),
    "orchestrate": os.environ.get("ORCHESTRATOR_SERVICE_URL", "http://localhost:8005"),
    "safety": os.environ.get("SAFETY_SERVICE_URL", "http://localhost:8006"),
}


@app.get("/")
def health():
    return {
        "status": "running",
        "app": "MoodSense AI Gateway",
        "architecture": "microservices",
        "services": list(SERVICES.keys()),
    }


@app.api_route("/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(service: str, path: str, request: Request):
    """Forward requests to the appropriate microservice."""
    if service not in SERVICES:
        return Response(
            content=f'{{"error": "Unknown service: {service}"}}',
            status_code=404,
            media_type="application/json",
        )

    target_url = f"{SERVICES[service]}/{path}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            body = await request.body()
            headers = dict(request.headers)
            headers.pop("host", None)

            response = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                headers=headers,
                params=dict(request.query_params),
            )

            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type", "application/json"),
            )
        except httpx.ConnectError:
            return Response(
                content=f'{{"error": "Service {service} unavailable"}}',
                status_code=503,
                media_type="application/json",
            )
        except Exception as e:
            logger.error(f"Gateway proxy error: {e}")
            return Response(
                content=f'{{"error": "Gateway error: {str(e)}"}}',
                status_code=502,
                media_type="application/json",
            )


@app.get("/services/health")
async def service_health():
    """Check health of all downstream services."""
    results = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in SERVICES.items():
            try:
                resp = await client.get(f"{url}/health")
                results[name] = {"status": "healthy", "code": resp.status_code}
            except Exception:
                results[name] = {"status": "unhealthy"}
    return results
