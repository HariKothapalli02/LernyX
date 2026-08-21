from app import app, chat_sessions_collection
from bson import ObjectId
import json

def inspect():
    print("Dumping last 5 sessions...")
    with app.app_context():
        sessions = list(chat_sessions_collection.find().sort("updated_at", -1).limit(5))
        
        with open("db_dump.txt", "w") as f:
            for s in sessions:
                data = {
                    "_id": str(s.get("_id")),
                    "title": s.get("title"),
                    "user_id": str(s.get("user_id")),
                    "message_count": len(s.get("messages", [])),
                    "first_msg": s.get("messages", [])[0].get("content") if s.get("messages") else None
                }
                f.write(json.dumps(data, indent=2) + "\n")
                print(f"Dumped session {data['_id']}")

if __name__ == "__main__":
    inspect()
