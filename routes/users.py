from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/")
async def get_users():
    """Get all users"""
    return {"message": "List of users"}

@router.get("/{user_id}")
async def get_user(user_id: int):
    """Get user by ID"""
    return {"user_id": user_id, "message": f"User {user_id} details"}

@router.post("/")
async def create_user():
    """Create a new user"""
    return {"message": "User created successfully"}
