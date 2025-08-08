from fastapi import Request, status
from fastapi.responses import JSONResponse
from loguru import logger
import os


auth_tokens = os.getenv("AUTH_TOKENS", "").split(",") if os.getenv("AUTH_TOKENS") else []

async def auth_middleware(request: Request, call_next):
    # skip authentication if the auth_tokens list is empty
    if not len(auth_tokens):
        return await call_next(request)
    # authenticate all requests except the /health endpoint
    if request.url.path != "/health":
        auth_token = request.headers.get("Authorization")
        logger.bind(
            path=request.url.path,
            method=request.method,
            auth_token=auth_token,
        ).debug("Received request")
        if not auth_token or auth_token not in auth_tokens:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Unauthorized"},
            )
    response = await call_next(request)
    return response
