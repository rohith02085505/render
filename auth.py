# auth.py
import os
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from database import users_col
from jose import jwt, JWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("auth")
logger.setLevel(logging.INFO)

router = APIRouter()
security = HTTPBearer()

# config
SECRET = os.getenv("JWT_SECRET", "secret123")
ALGORITHM = os.getenv("JWT_ALGO", "HS256")
TOKEN_EXPIRE_MIN = int(os.getenv("TOKEN_EXPIRE_MIN", 60 * 24))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str

def create_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if "sub" not in to_encode:
        raise ValueError("JWT must include sub (user email)")
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=TOKEN_EXPIRE_MIN))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET, algorithm=ALGORITHM)



def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = users_col.find_one({"email": email}, {"password": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        # normalize user dict (remove Mongo _id ObjectId for safety)
        user["email"] = user.get("email")
        return user
    except JWTError as e:
        logger.exception("JWT decode error")
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/signup")
def signup(user: UserCreate):
    if users_col.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_pw = pwd_context.hash(user.password)
    users_col.insert_one({
        "name": user.name,
        "email": user.email,
        "password": hashed_pw,
        # optionally: "is_admin": False
    })
    return {"message": "User created successfully"}


@router.post("/login")
def login(payload: LoginIn):
    found = users_col.find_one({"email": payload.email})
    if not found or not pwd_context.verify(payload.password, found["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token({"sub": payload.email})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    return {
        "name": user.get("name"),
        "email": user.get("email")
    }


import logging

logger = logging.getLogger("notif")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
