from pydantic import BaseModel, Field
from typing import Optional

# Used for authentication
class User(BaseModel):
    name: str 
    email: str
    password: str

# Used for reporting items
class Item(BaseModel):
    item_name: str
    description: str
    date: str
    time: str
    location: str
    image_url: str
    contact_info: str
    priority: Optional[bool] = False
    type: str  # "lost" or "found"
    is_claimed: Optional[bool] = False

# Feedback model
class Feedback(BaseModel):
    text: str
