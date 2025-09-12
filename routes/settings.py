from fastapi import APIRouter, HTTPException, Depends, status, Body, Request
from pydantic import BaseModel, EmailStr
from typing import Optional
from routes.database import get_user_collection
from routes.auth import verify_token, sendmail
from bson import ObjectId

router = APIRouter(prefix="/settings", tags=["settings"])

# Password helper functions (matching auth.py system)
def create_user_credential(name: str, password: str) -> str:
    """Create a simple credential by combining name and password"""
    return f"{name}:{password}"

def verify_user_credential(name: str, password: str, stored_credential: str) -> bool:
    """Verify user credential by comparing name+password combination"""
    expected_credential = create_user_credential(name, password)
    return expected_credential == stored_credential

# Helper function to convert ObjectId to string
def convert_objectid_to_str(obj):
    """Convert ObjectId fields to strings for JSON serialization"""
    if isinstance(obj, dict):
        return {key: convert_objectid_to_str(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid_to_str(item) for item in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj

class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    degree: Optional[str] = None
    dob: Optional[str] = None
    mobileNumber: Optional[str] = None

class PasswordUpdateRequest(BaseModel):
    old: str
    new: str

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class SettingsUpdateRequest(BaseModel):
    profile: Optional[ProfileUpdateRequest] = None
    password: Optional[PasswordUpdateRequest] = None

@router.get("/")
async def get_settings(current_user: str = Depends(verify_token)):
    """Get user profile settings (name, email, degree, DOB only)"""
    user_collection = get_user_collection()
    
    # Find user by email
    found_user = user_collection.find_one({"email": current_user})
    
    if not found_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Return only the required fields
    settings_data = {
        "name": found_user.get("name", ""),
        "email": found_user.get("email", ""),
        "degree": found_user.get("degree", ""),
        "dob": found_user.get("dob", ""),
        "mobileNumber": found_user.get("mobileNumber", "")
    }
    
    return {
        "success": True,
        "message": "Settings retrieved successfully",
        "data": settings_data
    }

@router.post("/")
async def update_settings(
    update_request: SettingsUpdateRequest = Body(...),
    current_user: str = Depends(verify_token)
):
    """Update user settings - either profile details or password"""
    user_collection = get_user_collection()
    
    # Find user by email
    found_user = user_collection.find_one({"email": current_user})
    
    if not found_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    update_data = {}
    updated_fields = []
    
    # Handle profile updates
    if update_request.profile:
        profile_data = update_request.profile.dict(exclude_unset=True)
        
        # Check if email is being changed and if it already exists
        if "email" in profile_data:
            new_email = profile_data["email"]
            if new_email != current_user:
                existing_user = user_collection.find_one({"email": new_email})
                if existing_user:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already exists"
                    )
        
        # Add profile fields to update
        for field, value in profile_data.items():
            if value is not None:
                update_data[field] = value
                updated_fields.append(f"profile.{field}")
    
    # Handle password update
    if update_request.password:
        password_data = update_request.password
        
        # Verify old password
        if not verify_user_credential(found_user["name"], password_data.old, found_user["password"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )
        
        # Create new password credential
        new_credential = create_user_credential(found_user["name"], password_data.new)
        update_data["password"] = new_credential
        updated_fields.append("password")
    
    # Check if there are any updates to make
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )
    
    # Update user in database
    result = user_collection.update_one(
        {"email": current_user},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get updated user data for response
    updated_user = user_collection.find_one({"email": current_user})
    
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found after update"
        )
    
    # Prepare response data
    response_data = {
        "name": updated_user.get("name", ""),
        "email": updated_user.get("email", ""),
        "degree": updated_user.get("degree", ""),
        "dob": updated_user.get("dob", ""),
        "mobileNumber": updated_user.get("mobileNumber", "")
    }
    
    return {
        "success": True,
        "message": "Settings updated successfully",
        "data": {
            "updated_fields": updated_fields,
            "settings": response_data
        }
    }

@router.put("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: str = Depends(verify_token)
):
    """Change user password (dedicated endpoint)"""
    user_collection = get_user_collection()
    
    # Find user in database
    found_user = user_collection.find_one({"email": current_user})
    if not found_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify current password
    if not verify_user_credential(found_user["name"], password_data.current_password, found_user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )
    
    # Create new password credential
    new_credential = create_user_credential(found_user["name"], password_data.new_password)
    
    # Update password in database
    result = user_collection.update_one(
        {"email": current_user},
        {"$set": {"password": new_credential}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {
        "success": True,
        "message": "Password changed successfully"
    }



@router.post("/support")
async def support(request : Request, current_user: str = Depends(verify_token)):
    user_collection = get_user_collection()
    found_user = user_collection.find_one({"email": current_user})
    if not found_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    data = await request.json()
    print(data)
    if sendmail("aruniankur7@gmail.com", str(data) + " " + current_user):
        return {"status": "ok"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send"
        )