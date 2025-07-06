from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from database import users_col
from jose import jwt, JWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta
import os

router = APIRouter()

# JWT settings
SECRET = os.getenv("JWT_SECRET", "secret123")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MIN = 60 * 24

# Password hashing setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Auth scheme
security = HTTPBearer()

# User model
class User(BaseModel):
    name: str
    email: str
    password: str


# Token creation
def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MIN)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET, algorithm=ALGORITHM)

# Token validation
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        email = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"email": email}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Signup route (with password hashing)
@router.post("/signup")
def signup(user: User):
    if users_col.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_pw = pwd_context.hash(user.password)
    users_col.insert_one({
    "name": user.name,
    "email": user.email,
    "password": hashed_pw
})
    return {"message": "User created successfully"}

# Login route (with password verification)


from fastapi import Request

@router.post("/login")
async def login(request: Request):
    data = await request.json()
    email = data.get("email")
    password = data.get("password")

    found = users_col.find_one({"email": email})
    if not found or not pwd_context.verify(password, found["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"sub": email})
    return {"access_token": token}

