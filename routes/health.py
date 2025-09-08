from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])

@router.get("/")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "Service is running"}

@router.get("/ping")
async def ping():
    """Simple ping endpoint"""
    return {"message": "pong"}
