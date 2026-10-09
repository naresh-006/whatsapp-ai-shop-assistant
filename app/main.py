import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import settings
from app.database import close_mongo_connection, check_db_connection
from app.routes.health import router as health_router
from app.routes.products import router as products_router
from app.routes.billing import router as billing_router
from app.routes.orders import router as orders_router
from app.routes.ai import router as ai_router
from app.routes.resolver import router as resolver_router
from app.routes.pipeline import router as pipeline_router
from app.routes.sales import router as sales_router
from app.routes.audio import router as audio_router
from app.routes.whatsapp import router as whatsapp_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager to handle DB startup check and shutdown cleanup."""
    db_status = check_db_connection()
    if db_status["connected"]:
        logger.info("Successfully connected to live MongoDB (%s).", db_status["database"])
    else:
        logger.info(
            "MongoDB is offline. Active in In-Memory Demo Mode with pre-seeded products. "
            "All endpoints are fully operational!"
        )

    yield

    close_mongo_connection()
    logger.info("MongoDB connection pool closed.")


app = FastAPI(
    title=settings.APP_NAME,
    description="Backend billing & sales assistant for retail + wholesale family shop.",
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

from fastapi.responses import JSONResponse
from fastapi import Request
from app.models.billing import BillingError

@app.exception_handler(BillingError)
async def billing_exception_handler(request: Request, exc: BillingError):
    return JSONResponse(
        status_code=400,
        content={"error": "BillingValidationError", "detail": str(exc)},
    )

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"error": "InvalidInputError", "detail": str(exc)},
    )

# Register routers
app.include_router(health_router)
app.include_router(products_router)
app.include_router(billing_router)
app.include_router(orders_router)
app.include_router(ai_router)
app.include_router(resolver_router)
app.include_router(pipeline_router)
app.include_router(sales_router)
app.include_router(audio_router)
app.include_router(whatsapp_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
