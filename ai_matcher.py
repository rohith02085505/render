import os
import google.generativeai as genai
from database import items_col
from notif import send_email, speak_message, make_phone_call

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(model_name="models/gemini-1.5-flash")

def match_with_gemini(new_item):
    # Find opposite type (lost ↔ found) and unclaimed
    other_items = items_col.find({
        "type": {"$ne": new_item["type"]},
        "is_claimed": False
    })

    matched_contacts = set()  # To avoid duplicate alerts

    for existing in other_items:
        prompt = f"""
Compare these two item reports and determine if they describe the same lost item.

Item A Description:
{existing['description']}

Item B Description:
{new_item['description']}

Respond with only: yes or no.
"""
        try:
            response = model.generate_content(prompt)
            decision = response.text.strip().lower()
        except Exception as e:
            print(f"❌ Error from Gemini model: {e}")
            continue

        if decision.startswith("yes"):
            if existing["contact_info"] in matched_contacts:
                continue  # avoid duplicate emails/calls

            print("✅ Match found")
            ai_agent_notify(existing, new_item)
            matched_contacts.add(existing["contact_info"])
            break  # comment this line if you want to allow multiple matches

import re

def is_valid_email(address):
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", address))

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def match_with_tfidf(new_item):
    all_items = list(items_col.find({"type": "found", "is_claimed": False}))
    if not all_items:
        print("No found items to match against.")
        return

    descriptions = [item["description"] for item in all_items]
    descriptions.append(new_item["description"])

    # TF-IDF Vectorization
    vectorizer = TfidfVectorizer().fit_transform(descriptions)
    vectors = vectorizer.toarray()

    # Compare new item to all others
    similarities = cosine_similarity([vectors[-1]], vectors[:-1])[0]

    best_index = similarities.argmax()
    best_score = similarities[best_index]

    if best_score > 0.75:  # You can lower threshold if needed
        best_match = all_items[best_index]
        print(f"🔍 TF-IDF Match Found: {best_match['item_name']} (Score: {best_score:.2f})")
        # Optional: send email, log match, etc.
    else:
        print("❌ No strong TF-IDF match found.")


import qrcode
from io import BytesIO
import base64

def generate_qr_for_item(item_id: str):
    # The URL that QR should encode
    qr_text = f"https://lostlink.ai/qr/{item_id}"  # Replace with real domain

    qr = qrcode.make(qr_text)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    base64_qr = base64.b64encode(buffer.getvalue()).decode()

    return f"data:image/png;base64,{base64_qr}"


def ai_agent_notify(lost_item, found_item):
    contact = lost_item["contact_info"]
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

    print(f"📧 Notifying {contact} about match with {found_item['item_name']}")

    # Send email only if the contact is an email
    if is_valid_email(contact):
        send_email(to=contact, subject=subject, body=body)
        print(f"✅ Email sent to {contact}")
    else:
        print(f"⚠️ Skipping email: {contact} is not a valid email.")

    speak_message(
        f"A potential match has been found for lost item: {lost_item['item_name']} at {found_item['location']}."
    )

    if lost_item.get("wants_call") and contact.startswith("+"):
        make_phone_call(
            to_number=contact,
            message=f"Hello! A match is found for your lost item: {lost_item['item_name']} at {found_item['location']}. Please check LostLink AI. Thank you."
        )
