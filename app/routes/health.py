from fastapi import APIRouter
from app.config import settings
from app.database import check_db_connection

router = APIRouter(tags=["Health"])


@router.get("/")
def root():
    return {
        "status": "online",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "version": "0.1.0",
    }


@router.get("/health")
def health_check():
    db_status = check_db_connection()
    return {
        "status": "healthy" if db_status["connected"] else "degraded",
        "database": db_status,
    }
