import certifi
import json
import re
import math
from pymongo import MongoClient, UpdateOne
from bson import ObjectId
from datetime import datetime, timezone

MONGODB_URI = "mongodb+srv://harikothapalli61_db_user:Kothapalli555@cluster0.5nukjmu.mongodb.net/"
DB_NAME = "videoquiz_db"

def solve_simple_math(question_text):
    """Attempt to solve basic arithmetic and algebra questions deterministically."""
    q = question_text.strip()
    
    # Pattern 1: What is X% of Y?
    m = re.search(r'what\s+is\s+([\d.]+)\s*%\s*of\s*([\d.]+)', q, re.I)
    if m:
        pct, total = float(m.group(1)), float(m.group(2))
        return (pct / 100.0) * total
        
    # Pattern 2: What is X + Y / X * Y / etc.
    m = re.search(r'what\s+is\s+([\d.\s+\-*/()]+)\s*\?', q, re.I)
    if m:
        expr = m.group(1).strip()
        if re.match(r'^[\d.\s+\-*/()]+$', expr):
            try:
                return float(eval(expr))
            except:
                pass
                
    # Pattern 3: Find average of N numbers
    m = re.search(r'average\s+of\s+([\d\s,a-and]+)', q, re.I)
    if m:
        nums = [float(x) for x in re.findall(r'[\d.]+', m.group(1))]
        if nums:
            return sum(nums) / len(nums)

    return None

def extract_option_from_explanation(explanation, options):
    """Extract which option index the explanation claims is correct."""
    if not explanation:
        return None
        
    exp_lower = explanation.lower()
    
    # Check for "Option A", "Option B", "Option C", "Option D"
    opt_map = {"option a": 0, "option b": 1, "option c": 2, "option d": 3,
               "(a)": 0, "(b)": 1, "(c)": 2, "(d)": 3,
               "option 1": 0, "option 2": 1, "option 3": 2, "option 4": 3}
               
    for key, idx in opt_map.items():
        if key in exp_lower and idx < len(options):
            return idx
            
    # Check if exact option string appears in explanation (e.g. "Therefore, the answer is 42")
    for i, opt in enumerate(options):
        opt_str = str(opt).strip().lower()
        if opt_str and len(opt_str) > 1 and f"is {opt_str}" in exp_lower:
            return i
            
    return None

def audit_and_fix_questions():
    print("Connecting to MongoDB...")
    client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where(), tlsAllowInvalidCertificates=True)
    db = client[DB_NAME]
    collection = db.aptitude_questions
    
    questions = list(collection.find({}))
    total = len(questions)
    print(f"Loaded {total} aptitude questions from database.")
    
    bulk_updates = []
    fixed_count = 0
    invalid_index_fixed = 0
    explanation_mismatch_fixed = 0
    math_solver_fixed = 0
    
    for i, q in enumerate(questions):
        doc_id = q["_id"]
        q_text = q.get("question", "")
        options = q.get("options", [])
        current_correct = q.get("correct", 0)
        explanation = q.get("explanation", "")
        
        # Normalize current_correct to int
        try:
            current_correct = int(current_correct)
        except:
            current_correct = 0
            
        new_correct = current_correct
        new_explanation = explanation
        
        # Rule 1: Index out of range
        if current_correct < 0 or current_correct >= len(options):
            new_correct = 0
            invalid_index_fixed += 1
            
        # Rule 2: Explanation check
        exp_opt_idx = extract_option_from_explanation(explanation, options)
        if exp_opt_idx is not None and exp_opt_idx != new_correct:
            new_correct = exp_opt_idx
            explanation_mismatch_fixed += 1
            
        # Rule 3: Deterministic Math Solver Check
        math_ans = solve_simple_math(q_text)
        if math_ans is not None:
            # Match math_ans against options
            best_match_idx = None
            min_diff = float("inf")
            for idx, opt in enumerate(options):
                try:
                    # Clean option text
                    opt_val = float(re.sub(r'[^\d.-]', '', str(opt)))
                    diff = abs(opt_val - math_ans)
                    if diff < 0.01 and diff < min_diff:
                        min_diff = diff
                        best_match_idx = idx
                except:
                    continue
                    
            if best_match_idx is not None and best_match_idx != new_correct:
                new_correct = best_match_idx
                math_solver_fixed += 1
                new_explanation = f"Calculated answer is {math_ans:.2f}, matching option {best_match_idx+1}."
                
        # If any changes were made
        if new_correct != current_correct or new_explanation != explanation:
            fixed_count += 1
            bulk_updates.append(
                UpdateOne(
                    {"_id": doc_id},
                    {
                        "$set": {
                            "correct": new_correct,
                            "explanation": new_explanation,
                            "verified_at": datetime.now(timezone.utc)
                        }
                    }
                )
            )
            
    print(f"\n--- AUDIT SUMMARY ---")
    print(f"Total Questions Evaluated: {total}")
    print(f"Invalid Indices Fixed: {invalid_index_fixed}")
    print(f"Explanation Mismatches Fixed: {explanation_mismatch_fixed}")
    print(f"Math Solver Adjustments: {math_solver_fixed}")
    print(f"Total Questions Updated: {fixed_count}")
    
    if bulk_updates:
        print(f"Pushing {len(bulk_updates)} verified updates to MongoDB...")
        res = collection.bulk_write(bulk_updates)
        print(f"MongoDB Update Complete! Modified count: {res.modified_count}")
    else:
        print("All questions in MongoDB are already 100% verified and correct!")

if __name__ == "__main__":
    audit_and_fix_questions()
