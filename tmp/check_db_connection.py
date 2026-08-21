import os
from dotenv import load_dotenv
from pymongo import MongoClient
import certifi
import sys

# Explicitly load .env
env_path = os.path.join(os.path.dirname(__file__), '.env')
print(f"DEBUG: Looking for .env at: {env_path}")
if os.path.exists(env_path):
    print("DEBUG: .env file found.")
    load_dotenv(env_path)
else:
    print("DEBUG: .env file NOT found.")

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME = os.environ.get("DB_NAME", "LernyXDB")

print(f"DEBUG: MONGODB_URI present: {bool(MONGODB_URI)}")
if MONGODB_URI:
    print(f"DEBUG: MONGODB_URI length: {len(MONGODB_URI)}")
print(f"DEBUG: DB_NAME: {DB_NAME}")

if not MONGODB_URI:
    print("Error: MONGODB_URI not found in environment or .env file")
    sys.exit(1)

try:
    client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where(), tlsAllowInvalidCertificates=True)
    db = client[DB_NAME]
    
    print("Attempting to ping database...")
    client.admin.command('ping')
    print("Database ping successful.")
    
    collections = db.list_collection_names()
    print(f"Collections: {collections}")
    
    if "chat_sessions" in collections:
        print("chat_sessions collection exists.")
        count = db.chat_sessions.count_documents({})
        print(f"chat_sessions document count: {count}")
    else:
        print("chat_sessions collection does NOT exist (will be created on first insert).")
        
    # Try a dummy insert
    print("Attempting dummy insert...")
    result = db.chat_sessions.insert_one({"test": "debug_entry"})
    print(f"Insert successful. ID: {result.inserted_id}")
    
    # Clean up
    db.chat_sessions.delete_one({"_id": result.inserted_id})
    print("Dummy entry deleted.")
    
except Exception as e:
    print(f"Database error: {e}")
    import traceback
    traceback.print_exc()
