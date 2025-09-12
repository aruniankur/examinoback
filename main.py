from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import main as main_routes
from routes import users
from routes import health
from routes import auth
from routes import questions
from routes import settings
from routes import upload
from routes import payment
import os

app = FastAPI(
    title="Examino Backend API",
    description="FastAPI backend for Examino application",
    version="1.0.0"
)

# CORS Configuration - Allow all origins
origins = ["*"]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

# Include routers
app.include_router(main_routes.router)
app.include_router(users.router)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(questions.router)
app.include_router(settings.router)
app.include_router(upload.router)
app.include_router(payment.router)
