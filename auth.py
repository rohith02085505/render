from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from database import users_col
from jose import jwt, JWTError
from datetime import datetime, timedelta
import os

router = APIRouter()

SECRET = os.getenv("JWT_SECRET", "secret123")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MIN = 60 * 24

class User(BaseModel):
    email: str
    password: str  # In production, hash this

security = HTTPBearer()

def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MIN)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        email = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"email": email}  # ✅ Fix: return a dict
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/signup")
def signup(user: User):
    if users_col.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    users_col.insert_one(user.dict())
    return {"message": "User created successfully"}

@router.post("/login")
def login(user: User):
    found = users_col.find_one({"email": user.email, "password": user.password})
    if not found:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token({"sub": user.email})
    return {"access_token": token}
