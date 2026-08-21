import certifi
import json
from pymongo import MongoClient
from bson import ObjectId

MONGODB_URI = "mongodb+srv://harikothapalli61_db_user:Kothapalli555@cluster0.5nukjmu.mongodb.net/"
DB_NAME = "videoquiz_db"

def inspect_questions():
    client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where(), tlsAllowInvalidCertificates=True)
    db = client[DB_NAME]
    questions = list(db.aptitude_questions.find({}))
    print(f"Total aptitude questions found: {len(questions)}")
    
    formatted_questions = []
    for i, q in enumerate(questions):
        q_copy = dict(q)
        q_copy["_id"] = str(q_copy["_id"])
        formatted_questions.append(q_copy)
    
    with open("aptitude_questions_dump.json", "w", encoding="utf-8") as f:
        json.dump(formatted_questions, f, indent=2)
    print("Dumped questions to aptitude_questions_dump.json")

if __name__ == "__main__":
    inspect_questions()
