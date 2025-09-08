from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

# MongoDB connection
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:2017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "examino")
# Create MongoDB client
client = MongoClient(MONGODB_URL)
examinodb = client[DATABASE_NAME]

# Collections
user = examinodb['user']
test = examinodb['test']
passage = examinodb['passage']
DILRquestion = examinodb['DILRquestion']
VARCquestion = examinodb['VARCquestion']
QAquestion = examinodb['QAquestion']

# Dependency to get database
def get_db():
    return examinodb

# Dependency to get user collection
def get_user_collection():
    return user
