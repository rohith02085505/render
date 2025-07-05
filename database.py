# backend/database.py
from pymongo import MongoClient
import os

# Replace with your MongoDB Atlas URI or use env variable
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)

db = client["lostlink_ai"]
items_col = db["items"]
users_col = db["users"]
feedback_col = db["feedback"]
