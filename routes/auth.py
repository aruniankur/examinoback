from fastapi import APIRouter, HTTPException, Depends, status, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional
import smtplib
import ssl
import random
import string
import time
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
from routes.database import get_user_collection
from bson import ObjectId
import requests

router = APIRouter(prefix="/auth", tags=["authentication"])

# Security
security = HTTPBearer()

# JWT Settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# OTP and JWT storage (in production, use Redis or database)
otp_store = {}
jwt_blacklist = set()

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

# Pydantic models
class EmailRequest(BaseModel):
    email: EmailStr

class OTPVerification(BaseModel):
    email: EmailStr
    otp: str

class UserRegistration(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: str = "student"  # student, office employee, other
    dob: str
    degree: str  # can be various degrees or other
    mobileNumber: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

# Helper functions
def generate_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))

def create_user_credential(name: str, password: str) -> str:
    """Create a simple credential by combining name and password"""
    return f"{name}:{password}"

def verify_user_credential(name: str, password: str, stored_credential: str) -> bool:
    """Verify user credential by comparing name+password combination"""
    expected_credential = create_user_credential(name, password)
    return expected_credential == stored_credential

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if payload.get("jti") in jwt_blacklist:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return email
    except JWTError as e:
        error_detail = "Token has expired" if "expired" in str(e).lower() else "Invalid or expired token"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

def sendmail(email,otp):
    url = "https://mailman-717399453972.europe-west1.run.app"
    payload = {
    "email": email,
    "subject": "Your OTP Code for examino",
    "message": f"""
    Your otp for email verification for examino is {otp} \n valid for 5 minutes""",
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        print("Status Code:", response.status_code)
        return True
    except requests.exceptions.RequestException as e:
        print("Error:", e)
        return False

# Routes
@router.post("/request-otp")
async def request_otp(email_request: EmailRequest):
    """Request OTP for email verification"""
    email = email_request.email
    otp = generate_otp()
    expiry = time.time() + 300  # 5 min expiry
    otp_store[email] = {"otp": otp, "expiry": expiry}

    if sendmail(email, otp):
        return {"message": "OTP sent successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP"
        )

@router.post("/verify-otp")
async def verify_otp(otp_data: OTPVerification):
    """Verify OTP for email verification"""
    email = otp_data.email
    otp = otp_data.otp

    record = otp_store.get(email)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP not requested"
        )

    if time.time() > record["expiry"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired"
        )

    if otp != record["otp"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP"
        )

    otp_store[email]["verified"] = True
    return {"message": "OTP verified successfully"}

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserRegistration):
    """Register a new user"""
    email = user_data.email
    name = user_data.name
    password = user_data.password
    role = user_data.role
    degree = user_data.degree
    dob = user_data.dob
    mobileNumber = user_data.mobileNumber
    if email not in otp_store or not otp_store[email].get("verified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not verified"
        )

    # Get user collection
    user_collection = get_user_collection()
    
    # Check if user exists
    if user_collection.find_one({"email": email}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already exists"
        )

    user_credential = create_user_credential(name, password)

    new_user = {
        "email": email,
        "name": name,
        "password": user_credential,
        "role": role,
        "dob": dob,
        "degree": degree,
        "numberOfDevices": 0,  # keep for now, no implementation
        "subscription": "Basic",  # basic / pro
        "mobileNumber": mobileNumber if mobileNumber else None,
        "trail":10,
        "subscription_end_date": None,
        "payment_info": [],
        "test_id": [],  # will store the test id
        "dashboardAnalytics": {  # these data is shown in the dashboard
            "Accuracy": 0,
            "Avg. Time/Q": "0:00",
            "Questions Attempted": 0,
            "Tests Taken": 0,
            "Test Time": 0,
            "PerformanceTrend": {
                "VARC": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],  # used for line chart
                "DILR": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                "QA": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            },
            "Total Question Solved": {
                "DILR": {
                    "T_correct": 0,
                    "T_incorrect": 0,
                    "T_NA": 0,
                    "AvgTime": 0.0,
                    "AvgTime_C": 0.0,
                    "AvgTime_I": 0.0,
                    "AvgTime_NA": 0.0,
                    "section_breakdown": {
                        "Data Interpretation": {
                            "E": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "M": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "H": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "topic_breakdown": {}
                        },
                        "Logical Reasoning-1": {
                            "E": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "M": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "H": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "topic_breakdown": {}
                        },
                        "Logical Reasoning-2": {
                            "E": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "M": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "H": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "topic_breakdown": {}
                        },
                    }
                },
                "VARC": {
                    "T_correct": 0,
                    "T_incorrect": 0,
                    "T_NA": 0,
                    "AvgTime": 0.0,
                    "AvgTime_C": 0.0,
                    "AvgTime_I": 0.0,
                    "AvgTime_NA": 0.0,
                    "section_breakdown": {
                        "Reading Comprehension": {
                            "E": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "M": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "H": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "topic_breakdown": {}
                        },
                        "Verbal Ability": {
                            "E": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "M": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "H": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "topic_breakdown": {}
                        },
                    }
                },
                "QA": {
                    "T_correct": 0,
                    "T_incorrect": 0,
                    "T_NA": 0,
                    "AvgTime": 0.0,
                    "AvgTime_C": 0.0,
                    "AvgTime_I": 0.0,
                    "AvgTime_NA": 0.0,
                    "section_breakdown": {
                        "Arithmetic - Part 1": {
                            "E": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "M": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "H": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "topic_breakdown": {}
                        },
                        "Arithmetic - Part 2": {
                            "E": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "M": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "H": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "topic_breakdown": {}
                        },
                        "Algebra - Part 1": {
                            "E": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "M": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "H": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "topic_breakdown": {}
                        },
                        "Algebra - Part 2": {
                            "E": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "M": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "H": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "topic_breakdown": {}
                        },
                        "Geometry & Mensuration": {
                            "E": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "M": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "H": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "topic_breakdown": {}
                        },
                        "Number System": {
                            "E": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "M": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "H": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "topic_breakdown": {}
                        },
                        "Modern Mathematics": {
                            "E": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "M": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "H": {"C": [0, 0.0], "I": [0, 0.0], "NA": [0, 0.0]},
                            "topic_breakdown": {}
                        },
                    }
                }
            }
        },
        "created_at": time.time(),
        "last_login": None,
        "is_active": True,
    }

    # Insert user into database
    user_collection.insert_one(new_user)
    
    otp_store.pop(email, None)
    return {"message": "User registered successfully"}

@router.post("/login", response_model=Token)
async def login(user_credentials: UserLogin):
    """Login user and return JWT token"""
    email = user_credentials.email
    password = user_credentials.password
    print(email, password)
    # Get user collection
    user_collection = get_user_collection()
    
    # Find user in database
    found_user = user_collection.find_one({"email": email})
    if not found_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not verify_user_credential(found_user["name"], password, found_user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Update numberOfDevices and last_login
    user_collection.update_one(
        {"email": email}, 
        {"$inc": {"numberOfDevices": 1}, "$set": {"last_login": time.time()}}
    )

    # Create JWT token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": email}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
async def logout(current_user: str = Depends(verify_token)):
    """Logout user and revoke JWT token"""
    jwt_blacklist.add(current_user)
    return {"message": "Successfully logged out"}

@router.get("/dashboard")
async def get_dashboard_analytics(current_user: str = Depends(verify_token)):
    """Get dashboard analytics for the authenticated user"""
    user_collection = get_user_collection()
    
    # Find user in database
    found_user = user_collection.find_one({"email": current_user})
    if not found_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    if found_user.get("subscription") == "Pro":
        subscription_end_date = found_user.get("subscription_end_date")
        if subscription_end_date:
            if subscription_end_date < time.time():
                found_user["subscription"] = "Basic"
                found_user["subscription_end_date"] = None
                found_user["trail"] = 10
    # Return dashboard analytics
    user_collection.update_one({"email": current_user}, {"$set": found_user})
    dashboard_data = {
        "user_info": {
            "name": found_user.get("name"),
            "email": found_user.get("email"),
            "role": found_user.get("role"),
            "degree": found_user.get("degree"),
            "subscription": found_user.get("subscription"),
            "subscription_end_date": found_user.get("subscription_end_date"),
            "created_at": found_user.get("created_at"),
            "last_login": found_user.get("last_login"),
            "is_active": found_user.get("is_active", True),
            "mobileNumber": found_user.get("mobileNumber","+919369203455"),
            "trail": found_user.get("trail",-1)
        },
        "dashboardAnalytics": found_user.get("dashboardAnalytics", {}),
        "test_id": found_user.get("test_id", []),
    }
    
    # Convert ObjectId to string for JSON serialization
    return convert_objectid_to_str(dashboard_data)

@router.get("/profile")
async def get_user_profile(current_user: str = Depends(verify_token)):
    """Get complete user profile data"""
    user_collection = get_user_collection()
    
    # Find user in database
    found_user = user_collection.find_one({"email": current_user})
    if not found_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Remove password from response for security
    found_user.pop("password", None)
    
    # Convert ObjectId to string for JSON serialization
    return convert_objectid_to_str(found_user)

class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    degree: Optional[str] = None
    dob: Optional[str] = None
    role: Optional[str] = None

@router.put("/profile")
async def update_user_profile(
    profile_update: UserProfileUpdate = Body(...),
    current_user: str = Depends(verify_token)
):
    """Update user profile information"""
    user_collection = get_user_collection()
    
    # Build update dictionary with only provided fields
    update_data = {}
    if profile_update.name is not None:
        update_data["name"] = profile_update.name
    if profile_update.degree is not None:
        update_data["degree"] = profile_update.degree
    if profile_update.dob is not None:
        update_data["dob"] = profile_update.dob
    if profile_update.role is not None:
        update_data["role"] = profile_update.role
    
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
    
    return {"message": "Profile updated successfully", "updated_fields": list(update_data.keys())}

class AnalyticsUpdate(BaseModel):
    section: str  # VARC, DILR, QA
    subsection: Optional[str] = None  # e.g., "Reading Comprehension", "Data Interpretation"
    difficulty: Optional[str] = None  # E, M, H
    result_type: str  # correct, incorrect, NA
    time_taken: float  # time in minutes
    question_count: int = 1

@router.post("/analytics/update")
async def update_analytics(
    analytics_data: AnalyticsUpdate,
    current_user: str = Depends(verify_token)
):
    """Update user's dashboard analytics based on test performance"""
    user_collection = get_user_collection()
    
    # This is a placeholder for updating analytics
    # In a real implementation, you would:
    # 1. Calculate new averages
    # 2. Update performance trends
    # 3. Recalculate accuracy percentages
    # 4. Update section breakdowns
    
    # For now, just return success
    return {
        "message": "Analytics update endpoint ready",
        "note": "Full analytics calculation logic needs to be implemented"
    }

