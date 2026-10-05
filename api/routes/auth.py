import time
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from passlib.context import CryptContext
from config import get_settings
from database.db_manager import DatabaseManager
from models.user import User

router = APIRouter()
settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")
db = DatabaseManager()

# Simple in-memory backoff tracking: (ip, username) -> (failures, unlock_time)
_failed_logins: dict[str, dict[str, float]] = {}

def check_backoff(ip: str, username: str):
    now = time.time()
    record = _failed_logins.get(ip, {}).get(username)
    if record and record["unlock_time"] > now:
        raise HTTPException(status_code=401, detail="Too many failed attempts. Try again later.")

def record_failure(ip: str, username: str):
    now = time.time()
    ip_records = _failed_logins.setdefault(ip, {})
    record = ip_records.setdefault(username, {"failures": 0, "unlock_time": 0})
    record["failures"] += 1
    if record["failures"] >= 3:
        record["unlock_time"] = now + 60 * (2 ** (record["failures"] - 3))  # Exponential backoff

def record_success(ip: str, username: str):
    if ip in _failed_logins and username in _failed_logins[ip]:
        del _failed_logins[ip][username]

class Token(BaseModel):
    access_token: str
    token_type: str

class UserCreate(BaseModel):
    username: str
    password: str
    
class UserResponse(BaseModel):
    id: int
    username: str
    role: str

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.token_expiry_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    user = db.get_user_by_username(username)
    if user is None:
        raise credentials_exception
    
    # check is_active
    if getattr(user, "is_active", True) is False:  # Assuming user has is_active, otherwise defaults to True
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
        
    return user

def _validate_password(password: str):
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

@router.post("/register", response_model=UserResponse)
def register(user_in: UserCreate):
    if not settings.open_registration:
        raise HTTPException(status_code=403, detail="Open registration is disabled")
        
    if db.get_user_by_username(user_in.username):
        raise HTTPException(status_code=400, detail="Username already registered")
        
    _validate_password(user_in.password)
        
    hashed_password = pwd_context.hash(user_in.password)
    user = db.create_user(user_in.username, hashed_password)
    return UserResponse(id=user.id, username=user.username, role=user.role)

@router.post("/login", response_model=Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    ip = request.client.host if request.client else "unknown"
    check_backoff(ip, form_data.username)
    
    user = db.get_user_by_username(form_data.username)
    if not user or not pwd_context.verify(form_data.password, user.password_hash):
        record_failure(ip, form_data.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
        
    if getattr(user, "is_active", True) is False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
        
    record_success(ip, form_data.username)
        
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id, "role": user.role}
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return UserResponse(id=current_user.id, username=current_user.username, role=current_user.role)
