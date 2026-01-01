from app import app, chat_sessions_collection
from bson import ObjectId

def fix_titles():
    print("Starting chat title migration...")
    count = 0
    with app.app_context():
        # Find all sessions
        sessions = chat_sessions_collection.find({})
        
        for session in sessions:
            current_title = session.get("title")
            messages = session.get("messages", [])
            
            # Skip if title is already good (not None, not empty, not "New Chat")
            if current_title and current_title != "New Chat" and current_title != "(no title)":
                continue
                
            # Try to generate a better title
            new_title = "New Chat"
            
            # 1. Look for first user message
            for m in messages:
                if m.get("role") == "user":
                    content = m.get("content", "").strip()
                    if content:
                        new_title = content[:50] + "..." if len(content) > 50 else content
                        break
                    # If content is empty, check for attachment
                    if m.get("attachment"):
                        new_title = f"Analysis of {m['attachment']['filename']}"
                        break
            
            # Update if we found a better title
            if new_title != "New Chat":
                chat_sessions_collection.update_one(
                    {"_id": session["_id"]},
                    {"$set": {"title": new_title}}
                )
                print(f"Updated chat {session['_id']}: '{current_title}' -> '{new_title}'")
                count += 1
                
    print(f"Migration complete. Updated {count} chats.")

if __name__ == "__main__":
    fix_titles()
