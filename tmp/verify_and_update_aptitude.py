import certifi
import json
import os
import re
import random
from pymongo import MongoClient
from bson import ObjectId
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = "mongodb+srv://harikothapalli61_db_user:Kothapalli555@cluster0.5nukjmu.mongodb.net/"
DB_NAME = "videoquiz_db"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_API_KEYS = os.environ.get("GEMINI_API_KEYS")

def get_ai_model():
    keys = []
    if GEMINI_API_KEYS:
        keys = [k.strip() for k in GEMINI_API_KEYS.split(',') if k.strip()]
    if not keys and GEMINI_API_KEY:
        keys = [GEMINI_API_KEY]
    
    if not keys:
        raise ValueError("No GEMINI_API_KEY found")
        
    api_key = random.choice(keys)
    genai.configure(api_key=api_key)
    for name in ['gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-flash-latest', 'gemini-pro']:
        try:
            return genai.GenerativeModel(name)
        except Exception:
            continue
    return genai.GenerativeModel('gemini-1.5-flash')

def verify_single_question(model, question_text, options, current_correct, current_explanation):
    prompt = f"""
You are a master mathematics and logical reasoning expert. Your job is to strictly verify the correct answer for an aptitude question.

Question:
{question_text}

Options:
0: {options[0] if len(options) > 0 else ""}
1: {options[1] if len(options) > 1 else ""}
2: {options[2] if len(options) > 2 else ""}
3: {options[3] if len(options) > 3 else ""}

Current stored correct option index: {current_correct}
Current explanation: {current_explanation}

Task:
1. Solve the question step-by-step with 100% mathematical and logical precision.
2. Determine which option index (0, 1, 2, or 3) is 100% correct.
3. Write a clear, step-by-step explanation.

Return ONLY a valid JSON object in this exact format:
{{
  "correct_index": 0,
  "explanation": "Step-by-step mathematical explanation..."
}}
"""
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "```" in text:
            text = re.sub(r'```(?:json)?\s*', '', text)
            text = text.replace('```', '').strip()
        data = json.loads(text)
        verified_index = int(data.get("correct_index"))
        explanation = str(data.get("explanation", "")).strip()
        if 0 <= verified_index < len(options):
            return verified_index, explanation
    except Exception as e:
        print(f"AI Verification error: {e}")
    return current_correct, current_explanation

def run_verification():
    print("Connecting to MongoDB...")
    client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where(), tlsAllowInvalidCertificates=True)
    db = client[DB_NAME]
    collection = db.aptitude_questions
    
    questions = list(collection.find({}))
    total = len(questions)
    print(f"Found {total} questions in database.")
    
    if total == 0:
        print("No questions found in MongoDB aptitude_questions collection.")
        return
        
    model = get_ai_model()
    updated_count = 0
    verified_count = 0
    
    for i, q in enumerate(questions):
        q_id = q["_id"]
        q_text = q.get("question", "")
        options = q.get("options", [])
        current_correct = q.get("correct", 0)
        current_exp = q.get("explanation", "")
        
        print(f"\n[{i+1}/{total}] Verifying Question ID: {q_id}")
        print(f"Q: {q_text}")
        print(f"Options: {options}")
        print(f"Current Correct: {current_correct} -> '{options[current_correct] if current_correct < len(options) else 'INVALID'}'")
        
        verified_index, verified_exp = verify_single_question(model, q_text, options, current_correct, current_exp)
        
        is_changed = (verified_index != current_correct) or (verified_exp != current_exp)
        
        if is_changed:
            print(f"--> FIX APPLIED! Changed index from {current_correct} to {verified_index} ('{options[verified_index]}')")
            collection.update_one(
                {"_id": q_id},
                {
                    "$set": {
                        "correct": verified_index,
                        "explanation": verified_exp
                    }
                }
            )
            updated_count += 1
        else:
            print(f"--> VERIFIED OK (Correct index remains {current_correct})")
        
        verified_count += 1

    print("\n" + "="*50)
    print(f"COMPLETE! Verified: {verified_count}/{total} questions. Fixed/Updated: {updated_count} questions.")
    print("="*50)

if __name__ == "__main__":
    run_verification()
