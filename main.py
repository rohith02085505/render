
from dotenv import load_dotenv
load_dotenv()

import google.generativeai as genai
model = genai.GenerativeModel(model_name="models/gemini-1.5-flash")


from fastapi import FastAPI, UploadFile, File, Form, Depends , HTTPException,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from bson import ObjectId
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks

import os
import uuid

from auth import router as auth_router
from database import items_col,feedback_col
from ai_matcher import match_with_gemini , match_with_tfidf,generate_qr_for_item,run_matching_pipeline
from auth import get_current_user
from notif import send_email 





app = FastAPI()
os.makedirs("uploads", exist_ok=True)



# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static") ## contais css

app.mount("/img", StaticFiles(directory="img"), name="img")
# Serve uploaded files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


UPLOAD_DIR = "uploads"
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

@app.get("/")
def home():
    return FileResponse("html/index.html")

@app.post("/report_found")
async def report_found(
    background_tasks: BackgroundTasks,
    item_name: str = Form(...),
    description: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    location: str = Form(...),
    contact_info: str = Form(...),
    priority: bool = Form(False),
    image: UploadFile = File(...), # image upload
    user: dict = Depends(get_current_user) # this data will come from the token , using the function get_current_user
):
    ext = os.path.splitext(image.filename)[1].lower()

    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise HTTPException(status_code=400, detail="Unsupported file type.")
    

    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as f:
        while chunk := await image.read(1024 * 1024):
            f.write(chunk)

    image_url = f"/uploads/{filename}"

    item = {
        "item_name": item_name,
        "description": description,
        "date": date,
        "time": time,
        "location": location,
        "contact_info": contact_info,
        "priority": priority,
        "image_url": image_url,
        "type": "found",
        "is_claimed": False,
        "email": user["email"] 
    }
    result = items_col.insert_one(item)
    item_id = str(result.inserted_id)
# enqueue id (safer, avoids serializing ObjectId / stale copy)
    background_tasks.add_task(run_matching_pipeline, item_id)

    return {"message": "Found item reported successfully"}

@app.get("/stats")
def get_stats():
    total = items_col.count_documents({})
    found = items_col.count_documents({"type": "found"})
    lost = items_col.count_documents({"type": "lost"})
    return {
        "total_items": total,
        "found_items": found,
        "lost_items": lost
    }

from fastapi import BackgroundTasks

@app.post("/report_lost")
async def report_lost(
    background_tasks: BackgroundTasks,
    item_name: str = Form(...),
    description: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    location: str = Form(...),
    contact_info: str = Form(...),
    priority: bool = Form(False),
    image: UploadFile = File(...),
    wants_call: bool = Form(False),
    user: dict = Depends(get_current_user)  
):
    
    ext = os.path.splitext(image.filename)[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise HTTPException(status_code=400, detail="Unsupported file type.")

    filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as f:
        while chunk := await image.read(1024 * 1024):
            f.write(chunk)

    image_url = f"/uploads/{filename}"



    item = {
        "item_name": item_name,
        "description": description,
        "date": date,
        "time": time,
        "location": location,
        "contact_info": contact_info,
        "priority": priority,
        "wants_call": wants_call,
        "image_url": image_url,
        "type": "lost",
        "is_claimed": False,
        "email": user["email"] 
    }

    result = items_col.insert_one(item)
    item_id = str(result.inserted_id)

# enqueue item_id for matching pipeline (function expects item_id)
    background_tasks.add_task(run_matching_pipeline, item_id)

    return {
        "message": "Lost item reported successfully.",
        "item_id": item_id,
        "wants_call": wants_call,
        "generate_qr": generate_qr_for_item(item_id)
    }




from fastapi import Query
from typing import Optional
@app.get("/browse")
def get_unclaimed_found_items(user_email: Optional[str] = Query(None)):
    query = {"type": "found", "is_claimed": False}
    
    if user_email:
        query["email"] = {"$ne": user_email}

    items = list(items_col.find(query))
    for item in items:
        item["_id"] = str(item["_id"])
    return items



from bson import ObjectId
def sanitize_item(item):
    item["_id"] = str(item["_id"])
    return item

# at top of file (after load_dotenv())
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "rohith02aug@gmail.com")

# then in get_admin_items:
@app.get("/admin")
def get_admin_items(user: dict = Depends(get_current_user)):
    if user.get("email") != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin only")
    # return unclaimed items including qr_visits count
    items = []
    for item in items_col.find({"is_claimed": False}):
        item = sanitize_item(item)
        
        items.append(item)
    return items

from datetime import datetime



# POST: Collect feedback
@app.post("/feedback")
def submit_feedback(name: str = Form(...), email: str = Form(None), message: str = Form(...)):
    feedback = {
        "name": name,
        "email": email,
        "message": message,
        "date": datetime.utcnow()
    }
    feedback_col.insert_one(feedback)
    return {"message": "Thank you for your feedback!"}

# GET: Fetch all feedbacks
@app.get("/feedbacks")
def get_feedbacks():
    feedbacks = []
    for fb in feedback_col.find().sort("date", -1):
        feedbacks.append({
            "id": str(fb.get("_id")),
            "name": fb.get("name", "Anonymous"),
            "email": fb.get("email"),
            "message": fb.get("message"),
            "date": fb.get("date").strftime("%Y-%m-%d %H:%M:%S") if fb.get("date") else "Unknown"
        })
    return feedbacks


from bson.errors import InvalidId

@app.post("/agent_request")
def agent_assist(item_id: str, user: dict = Depends(get_current_user)):
    try:
        item = items_col.find_one({"_id": ObjectId(item_id)})
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid item ID format")

    description = item.get("description", "")
    if not description:
        return {"agent_response": "No description to analyze."}

    try:
        response = model.generate_content(f"""
You are an expert AI lost-and-found assistant. The user reported:
{description}

Based on this, suggest any additional details they could provide to improve matching.
""")
        text = getattr(response, "text", None) or response.get("candidates", [{}])[0].get("content", "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent failed: {e}")

    return {"agent_response": text.strip()}




from passlib.hash import bcrypt

from database import users_col

@app.get("/admin/users")
def get_admin_users(user: dict = Depends(get_current_user)):
    if user.get("email") != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin only")

    users = []
    for u in users_col.find({}, {"password": 0}):
        users.append({
            "name": u.get("name"),
            "email": u.get("email"),
            
        })
    return users




@app.get("/login")
def serve_login():
    return FileResponse("html/login.html")

@app.get("/signup")
def serve_signup():
    return FileResponse("html/signup.html")




@app.post("/claim/{item_id}")
async def claim_item(item_id: str, 
                     name: str = Form(...), 
                     contact: str = Form(...), 
                     proof: str = Form("")):
    try:
        item = items_col.find_one({"_id": ObjectId(item_id)})
        if not item:
            raise HTTPException(status_code=404, detail="Item not found.")
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid item ID.")

    found_user_email = item.get("email")
    if not found_user_email:
        raise HTTPException(status_code=400, detail="Reporter has no email.")

    subject = f"[LostLink AI] Claim Request for: {item['item_name']}"
    message = f"""
🔎 Someone has claimed the item you reported as FOUND!

🧑 Claimer Name: {name}
📞 Contact: {contact}
📄 Proof: {proof or 'Not provided'}

Please reach out to verify.
"""
    send_email(to=found_user_email, subject=subject, body=message)
    return {"message": "Claim sent to item reporter."}



@app.post("/admin/approve/{item_id}")
def approve_item(item_id: str):
    result = items_col.update_one(
        {"_id": ObjectId(item_id)},
        {"$set": {"is_claimed": True}}
    )
    if result.modified_count == 1:
        return {"msg": "Item marked as claimed"}
    raise HTTPException(status_code=404, detail="Item not found")

from database import users_col
@app.get("/me")
def get_user_info(user: dict = Depends(get_current_user)):
    db_user = users_col.find_one({"email": user["email"]})
    return {"name": db_user.get("name", "User")}

@app.get("/dashboard")
def serve_dashboard():
    return FileResponse("html/dashboard.html")


@app.get("/user/dashboard")
def get_dashboard(user: dict = Depends(get_current_user)):
    email = user["email"]
    print("📩 DASHBOARD for:", email)

    lost_reports = list(items_col.find({"email": email, "type": "lost"}))
    found_reports = list(items_col.find({"email": email, "type": "found"}))

    print("🔍 Lost found:", len(lost_reports))
    print("🔍 Found found:", len(found_reports))

    for r in lost_reports + found_reports:
        r["_id"] = str(r["_id"])

    return {
        "lost_reports": lost_reports,
        "found_reports": found_reports
    }



@app.delete("/items/{item_id}")
def delete_item(item_id: str, user: dict = Depends(get_current_user)):
    result = items_col.delete_one({
        "_id": ObjectId(item_id),
        "email": user["email"]  
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found or not authorized")

    return {"message": "Item deleted"}

from datetime import datetime

@app.get("/can_submit")
def can_submit(user: dict = Depends(get_current_user)):
    email = user["email"]

    # Get today’s date (only date part)
    today = datetime.now().strftime("%Y-%m-%d")

    # Count items reported by user today
    count = items_col.count_documents({
        "email": email,
        "date": today
    })

    if count >= 3:
        return {"can_submit": False, "message": "❌ You’ve reached today’s limit (3 reports). Try again tomorrow."}
    return {"can_submit": True}

# Returns base64 QR image for html
@app.get("/api/generate_qr/{item_id}")
def get_qr_api(item_id: str):
    from ai_matcher import generate_qr_for_item
    qr = generate_qr_for_item(item_id)
    return {"qr": qr}

# Serves the QR Page HTML
@app.get("/api/qr/{item_id}")
def api_qr_item(item_id: str, request: Request):
    try:
        item = items_col.find_one({"_id": ObjectId(item_id)})
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid item id format")

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Increment visits
    items_col.update_one({"_id": ObjectId(item_id)})
    # Sanitize copy for public display
    item = sanitize_item(item)
    item.pop("contact_info", None)
    item.pop("email", None)

    # Add a title based on type
    if item.get("type") == "lost":
        item["page_title"] = "📌 Lost Item"
    else:
        item["page_title"] = "📌 Found Item"

    return item

@app.get("/qr/{item_id}")
def serve_qr_page(item_id: str):
    return FileResponse("html/qr_item.html")

@app.get("/report_lost.html")
def serve_lost_page():
    return FileResponse("html/report_lost.html")


@app.get("/{page_name}", include_in_schema=False)
def serve_page(page_name: str):
    file_path = f"html/{page_name}"
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"detail": "Page not found"}, 404
import logging

logger = logging.getLogger("notif")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# --- add imports near top of main.py if not present ---
from bson.errors import InvalidId
from fastapi import Request

# --- new: public API for QR page (increments visits but hides contact) ---
@app.get("/api/qr/{item_id}")
def api_qr_item(item_id: str, request: Request):
    """
    Public API the QR page will call.
    - increments `qr_visits` on the item
    - returns sanitized item for display (does NOT include contact/email)
    """
    try:
        item = items_col.find_one({"_id": ObjectId(item_id)})
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid item id format")

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # increment visits (simple counter — can be extended to unique IP if needed)
    items_col.update_one({"_id": ObjectId(item_id)})

    # sanitize copy for public display
    item = sanitize_item(item)
    # remove contact info / emails for privacy
    item.pop("contact_info", None)
    item.pop("email", None)

    # make image URL absolute if you want (frontend can prepend base)
    # item["image_url"] = f"{os.getenv('BASE_URL', '')}{item.get('image_url')}"
    return item
