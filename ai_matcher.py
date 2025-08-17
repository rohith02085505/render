import os
import re
import base64
import logging
from io import BytesIO

import qrcode
import google.generativeai as genai
from bson import ObjectId
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from database import items_col
from notif import send_email, make_phone_call

# === Configure Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LostLinkAgent")

# === Configure Gemini ===
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(model_name="models/gemini-1.5-flash")

# === Email Validator ===
def is_valid_email(address):
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", address))

# === Notification Function ===
def ai_agent_notify(lost_item, found_item):
    contact = lost_item.get("contact_info")
    subject = "🎯 Possible Match for Your Lost Item!"
    body = f"""
Hi,

We may have found a match for your lost item: {lost_item['item_name']}.

Matched with found item:
- {found_item['item_name']}
- Description: {found_item['description']}
- Location: {found_item['location']}
- Date: {found_item['date']} at {found_item['time']}

Please log in to LostLink AI to view details and confirm.

– LostLink AI Agent 🤖

DO NOT REPLY. 
THIS IS AUTO-GENERATED.
"""

    logger.info(f"📧 Notifying {contact} about match with {found_item['item_name']}")

    if is_valid_email(contact):
        try:
            send_email(to=contact, subject=subject, body=body)
            logger.info(f"✅ Email sent to {contact}")
        except Exception as e:
            logger.error(f"❌ Email sending failed: {e}")
    else:
        logger.warning(f"⚠️ Invalid email: {contact}")


    if lost_item.get("wants_call") and contact.startswith("+"):
        try:
            make_phone_call(
                to_number=contact,
                message=f"Hello! A match is found for your lost item: {lost_item['item_name']} at {found_item['location']}. Please check LostLink AI."
            )
        except Exception as e:
            logger.error(f"📞 Call failed: {e}")

# === TF-IDF Matcher ===
def match_with_tfidf(new_item, threshold=0.75):
    other_type = "found" if new_item["type"] == "lost" else "lost"
    all_items = list(items_col.find({"type": other_type, "is_claimed": False}))

    if not all_items:
        logger.info("No opposite-type items to match against.")
        return []

    descriptions = [item.get("description", "") for item in all_items]
    descriptions.append(new_item.get("description", ""))

    try:
        vectors = TfidfVectorizer().fit_transform(descriptions).toarray()
        similarities = cosine_similarity([vectors[-1]], vectors[:-1])[0]
    except Exception as e:
        logger.error(f"❌ TF-IDF error: {e}")
        return []

    matches = []
    for idx, score in enumerate(similarities):
        if score >= threshold:
            matched_item = all_items[idx]
            logger.info(f"🔍 TF-IDF Match: {matched_item['item_name']} (Score: {score:.2f})")
            ai_agent_notify(matched_item, new_item)
            matches.append(matched_item)

    if not matches:
        logger.info("❌ No strong TF-IDF matches.")
    return matches

# === Gemini Matcher ===
def match_with_gemini(new_item):
    other_items = list(items_col.find({
        "type": {"$ne": new_item["type"]},
        "is_claimed": False
    }))

    contacted = set()
    matched_items = []

    for existing in other_items:
        prompt = f"""
Compare the following two items and determine if they describe the same lost/found item.

Item A Description:
{existing.get('description', '')}

Item B Description:
{new_item.get('description', '')}

Threshold: 0.75
If they are the same item, respond with exactly: YES
If not, respond with exactly: NO
"""

        try:
            response = model.generate_content(prompt)
            decision = (response.text or "").strip().lower()
        except Exception as e:
            logger.error(f"❌ Gemini model error: {e}")
            continue

        if decision == "yes":
            contact = existing.get("contact_info")
            if contact in contacted:
                continue
            logger.info("✅ Gemini Match Found")
            ai_agent_notify(existing, new_item)
            contacted.add(contact)
            matched_items.append(existing)
            break  # Remove this if you want multiple Gemini matches

    return matched_items

# === QR Code Generator ===
# ai_matcher.py
def generate_qr_for_item(item_id: str):
    import qrcode, base64
    from io import BytesIO
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000")
    url = f"{base_url}/qr/{item_id}"   # direct details page
    qr = qrcode.make(url)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

# === AI Matching Pipeline ===
def run_matching_pipeline(item_id: str):
    logger.info("🚀 Starting AI Matching Pipeline...")
    item = items_col.find_one({"_id": ObjectId(item_id)})

    if not item:
        logger.warning(f"Item not found in matching pipeline: {item_id}")
        return {"action": "item_not_found"}

    # Step 1: Try TF-IDF
    tfidf_matches = match_with_tfidf(item)
    if tfidf_matches:
        logger.info("✅ TF-IDF matched. No need for Gemini.")
        return {"method": "tfidf", "matches": tfidf_matches}

    # Step 2: Escalate to Gemini if priority
    if item.get("priority"):
        logger.info("⚠️ Escalating to Gemini due to priority.")
        gemini_matches = match_with_gemini(item)
        return {"method": "gemini", "matches": gemini_matches}

    # Step 3: No match
    logger.info("❌ No matches found. Not escalated to Gemini.")
    return {"method": "none", "matches": []}
import logging

logger = logging.getLogger("notif")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
