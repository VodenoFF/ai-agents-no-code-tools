import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
import sys
from loguru import logger

from api_server.auth_middleware import auth_middleware
from api_server.v1_utils_router import v1_utils_router
from api_server.v1_media_router import v1_media_api_router
from video.config import device

logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level> | <blue>{extra}</blue>",
    level="DEBUG",
)

logger.info("This server was created by the 'AI Agents A-Z' YouTube channel")
logger.info("https://www.youtube.com/@aiagentsaz")
logger.info("Using device: {}", device)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up the server...")
    yield
    logger.info("Shutting down the server...")

app = FastAPI(lifespan=lifespan)


# add middleware to app, besides the /health endpoint
app.middleware("http")(auth_middleware)

@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {
        "message": "Welcome to the AI Agents A-Z No-Code Server",
        "version": "0.3.5",
        "documentation": "/docs",
        "created_by": "https://www.youtube.com/@aiagentsaz"
    }

@app.api_route("/health", methods=["GET", "HEAD"])
def healthcheck():
    return {"status": "ok"}

api_router = APIRouter()
v1_api_router = APIRouter()

# todo auto-delete files after 30 minutes (env var)

v1_api_router.include_router(v1_media_api_router, prefix="/media", tags=["media"])
v1_api_router.include_router(v1_utils_router, prefix="/utils", tags=["utils"])
api_router.include_router(v1_api_router, prefix="/v1", tags=["v1"])
app.include_router(api_router, prefix="/api", tags=["api"])
