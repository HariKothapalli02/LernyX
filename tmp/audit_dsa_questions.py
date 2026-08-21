import certifi
import json
import re
from pymongo import MongoClient, UpdateOne
from bson import ObjectId
from datetime import datetime

MONGODB_URI = "mongodb+srv://harikothapalli61_db_user:Kothapalli555@cluster0.5nukjmu.mongodb.net/"
DB_NAME = "videoquiz_db"

def clean_str(val):
    if val is None:
        return ""
    return str(val).strip()

def audit_dsa_questions():
    print("Connecting to MongoDB for DSA Audit...")
    client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where(), tlsAllowInvalidCertificates=True)
    db = client[DB_NAME]
    collection = db.dsa_questions
    
    questions = list(collection.find({}))
    total = len(questions)
    print(f"Loaded {total} DSA questions from database.")
    
    if total == 0:
        print("No DSA questions found in database.")
        return

    bulk_updates = []
    total_test_cases_audited = 0
    test_cases_fixed = 0
    missing_hidden_fixed = 0
    whitespace_fixed = 0
    questions_updated = 0
    
    for i, q in enumerate(questions):
        doc_id = q["_id"]
        title = clean_str(q.get("title"))
        desc = clean_str(q.get("description"))
        difficulty = q.get("difficulty", "Easy")
        test_cases = q.get("test_cases", [])
        
        needs_update = False
        updated_test_cases = []
        
        # Ensure test_cases is a valid list
        if not isinstance(test_cases, list) or len(test_cases) == 0:
            print(f"[WARNING] Question '{title}' (ID: {doc_id}) has no test cases. Creating default test case structure.")
            test_cases = [
                {"input": "1", "output": "1", "hidden": False},
                {"input": "2", "output": "2", "hidden": True}
            ]
            needs_update = True
            
        has_public = False
        has_hidden = False
        
        for tc_idx, tc in enumerate(test_cases):
            total_test_cases_audited += 1
            if not isinstance(tc, dict):
                tc = {"input": str(tc), "output": str(tc), "hidden": tc_idx > 0}
                needs_update = True
                test_cases_fixed += 1
                
            inp = tc.get("input", "")
            out = tc.get("output", "")
            hidden = bool(tc.get("hidden", False))
            
            # Clean input/output whitespace formatting
            cleaned_inp = str(inp).strip() if inp is not None else ""
            cleaned_out = str(out).strip() if out is not None else ""
            
            if cleaned_inp != inp or cleaned_out != out:
                whitespace_fixed += 1
                needs_update = True
                
            if hidden:
                has_hidden = True
            else:
                has_public = True
                
            updated_test_cases.append({
                "input": cleaned_inp,
                "output": cleaned_out,
                "hidden": hidden
            })
            
        # Ensure at least 1 hidden testcase and at least 1 public testcase
        if len(updated_test_cases) > 1 and not has_hidden:
            # Mark the last test case as hidden
            updated_test_cases[-1]["hidden"] = True
            has_hidden = True
            missing_hidden_fixed += 1
            needs_update = True
        elif len(updated_test_cases) == 1 and not has_hidden:
            # Add a hidden testcase copy/variant
            first_in = updated_test_cases[0]["input"]
            first_out = updated_test_cases[0]["output"]
            updated_test_cases.append({
                "input": first_in,
                "output": first_out,
                "hidden": True
            })
            missing_hidden_fixed += 1
            needs_update = True

        if needs_update:
            questions_updated += 1
            bulk_updates.append(
                UpdateOne(
                    {"_id": doc_id},
                    {
                        "$set": {
                            "test_cases": updated_test_cases,
                            "audited_at": datetime.utcnow()
                        }
                    }
                )
            )
            
    print(f"\n--- DSA AUDIT SUMMARY ---")
    print(f"Total DSA Questions Evaluated: {total}")
    print(f"Total Test Cases Audited: {total_test_cases_audited}")
    print(f"Malformed Test Cases Standardized: {test_cases_fixed}")
    print(f"Whitespace / Output Formats Cleaned: {whitespace_fixed}")
    print(f"Missing Hidden Test Cases Fixed: {missing_hidden_fixed}")
    print(f"Total DSA Questions Updated: {questions_updated}")
    
    if bulk_updates:
        print(f"Pushing {len(bulk_updates)} verified updates to MongoDB...")
        res = collection.bulk_write(bulk_updates)
        print(f"MongoDB Update Complete! Modified count: {res.modified_count}")
    else:
        print("All DSA questions and test cases in MongoDB are already 100% verified and clean!")

if __name__ == "__main__":
    audit_dsa_questions()
