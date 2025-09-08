from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def root():
    """Root endpoint"""
    return {"greeting": "Hello, World!", "message": "Welcome to FastAPI Arui!"}
