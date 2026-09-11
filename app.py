from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, redirect, url_for, flash, session, has_request_context
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

import re
import json
import random
import string
from youtube_transcript_api import YouTubeTranscriptApi
from io import BytesIO
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import shutil
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import smtplib
from email.mime.text import MIMEText
from generate_dsa_questions import generate_questions_batch
from email.mime.multipart import MIMEMultipart
import certifi
import tempfile
import threading
import sys
import socket
import logging

def _ignore_win_socket_error(args):
    if issubclass(args.exc_type, OSError) and getattr(args.exc_value, 'winerror', None) == 10038:
        return
    sys.__excepthook__(args.exc_type, args.exc_value, args.exc_traceback)

threading.excepthook = _ignore_win_socket_error

import rag_utils
import pinecone_utils
import apify_utils

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

# Configure logging
# Configure logging
# Configure logging
handlers = [logging.StreamHandler()]
try:
    handlers.append(logging.FileHandler('otp_debug.log'))
except OSError:
    pass  # Read-only file system (e.g., Vercel)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=handlers
)

# Silence noisy third-party debug loggers (PyMongo heartbeats, urllib3, etc.)
for logger_name in ["pymongo", "pymongo.topology", "pymongo.serverSelection", "pymongo.command", "pymongo.connection", "urllib3", "google.generativeai"]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# Try to import reportlab for PDF generation
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Try to import pytube for video metadata fallback
try:
    from pytube import YouTube
    PYTUBE_AVAILABLE = True
except ImportError:
    PYTUBE_AVAILABLE = False

# Try to import requests for alternative metadata fetching
try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Try to import yt-dlp for robust metadata fetching
try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your-secret-key-change-this-in-production")

EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp-relay.brevo.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 2525))
# MongoDB connection
MONGODB_URI = "mongodb+srv://harikothapalli61_db_user:Kothapalli555@cluster0.5nukjmu.mongodb.net/"
DB_NAME = os.environ.get("DB_NAME", "videoquiz_db")

# Initialize collections to None to avoid NameError if connection fails
users_collection = None
quizzes_collection = None
quiz_scores_collection = None
chat_conversations_collection = None
user_quiz_history_collection = None
custom_quizzes_collection = None
custom_quiz_attempts_collection = None
aptitude_questions_collection = None
aptitude_attempts_collection = None
aptitude_practice_history_collection = None
chat_sessions_collection = None
resume_reviews_collection = None
virtual_placement_results_collection = None

try:
    if not MONGODB_URI:
        raise ValueError("MONGODB_URI environment variable not set")
        
    client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where(), tlsAllowInvalidCertificates=True)
    db = client[DB_NAME]
    users_collection = db.users
    quizzes_collection = db.quizzes  # Store generated quizzes
    quiz_scores_collection = db.quiz_scores  # Store user quiz attempts and scores
    chat_conversations_collection = db.chat_conversations  # Store chatbot conversations
    user_quiz_history_collection = db.user_quiz_history  # Track standard quiz generations
    custom_quizzes_collection = db.custom_quizzes  # Store custom shareable quizzes
    custom_quiz_attempts_collection = db.custom_quiz_attempts  # Store attempts for custom quizzes
    aptitude_questions_collection = db.aptitude_questions  # Store aptitude questions
    aptitude_attempts_collection = db.aptitude_attempts  # Store aptitude quiz attempts
    aptitude_practice_history_collection = db.aptitude_practice_history  # Store individual practice question attempts
    chat_sessions_collection = db.chat_sessions # Store persistent chat sessions
    resume_reviews_collection = db.resume_reviews # Store user resume reports
    virtual_placement_results_collection = db.virtual_placement_results # Store persistent placement assessment & jobs
    # Test connection
    client.admin.command('ping')
    MONGODB_AVAILABLE = True
except Exception as e:
    print(f"MongoDB connection error: {str(e)}")
    MONGODB_AVAILABLE = False

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_id, username, email, dsa_score=0, api_key=None):
        self.id = str(user_id)
        self.username = username
        self.email = email
        self.dsa_score = dsa_score
        self.api_key = api_key

@login_manager.user_loader
def load_user(user_id):
    if not MONGODB_AVAILABLE:
        return None
    try:
        user_data = users_collection.find_one({"_id": ObjectId(user_id)})
        if user_data:
            return User(
                user_data["_id"], 
                user_data["username"], 
                user_data["email"],
                user_data.get("dsa_score", 0),
                user_data.get("api_key")
            )
    except Exception as e:
        print(f"Error loading user: {str(e)}")
    return None

# Gemini API config
# Gemini API config
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_API_KEYS = os.environ.get("GEMINI_API_KEYS")

_api_key_lock = threading.Lock()
_api_key_counter = 0

def get_all_api_keys():
    """Extract and clean all available API keys from environment."""
    keys = []
    if GEMINI_API_KEYS:
        keys.extend([k.strip() for k in GEMINI_API_KEYS.split(',') if k.strip()])
    if GEMINI_API_KEY and GEMINI_API_KEY.strip() not in keys:
        keys.append(GEMINI_API_KEY.strip())
    return keys

def get_next_api_key():
    """
    Strict Round-Robin load balancer across all 9 API keys.
    Sequentially rotates key per request to balance traffic evenly.
    """
    global _api_key_counter
    if has_request_context() and current_user.is_authenticated and hasattr(current_user, 'api_key') and current_user.api_key:
        return current_user.api_key
        
    all_keys = get_all_api_keys()
    if not all_keys:
        return None
        
    with _api_key_lock:
        key = all_keys[_api_key_counter % len(all_keys)]
        _api_key_counter = (_api_key_counter + 1) % len(all_keys)
        return key

GEMINI_MODEL_STRICT = "gemini-2.5-flash"

def generate_content_with_fallback(content_parts, preferred_model=None, temperature=0.7):
    """
    Generate content using strictly 'gemini-2.5-flash'.
    Uses Round-Robin API key load balancing with feature-specific temperature configuration.
    """
    all_keys = get_all_api_keys()
    if not all_keys and (has_request_context() and current_user.is_authenticated and getattr(current_user, 'api_key', None)):
        all_keys = [current_user.api_key]
        
    if not all_keys:
        return None, "No valid GEMINI_API_KEY found."

    attempts = len(all_keys)
    last_error = None

    for _ in range(attempts):
        key = get_next_api_key()
        try:
            genai.configure(api_key=key)
            gen_config = genai.types.GenerationConfig(temperature=temperature) if temperature is not None else None
            model_inst = genai.GenerativeModel(GEMINI_MODEL_STRICT, generation_config=gen_config)
            response = model_inst.generate_content(content_parts)
            return response, None
        except Exception as e:
            last_error = e
            err_msg = str(e)
            print(f"[Gemini Round-Robin Key Balance] Key ending '...{key[-6:] if key else ''}' failed: {err_msg}")
            # If key rate limited or failed, rotate to next key in pool
            continue

    return None, str(last_error) if last_error else "All Gemini API keys failed."

def get_gemini_model(preferred_model=None, temperature=0.7):
    """
    Configures and returns a 'gemini-2.5-flash' model instance with specific temperature configuration.
    """
    key = get_next_api_key()
    if key:
        try:
            genai.configure(api_key=key)
            gen_config = genai.types.GenerationConfig(temperature=temperature) if temperature is not None else None
            return genai.GenerativeModel(GEMINI_MODEL_STRICT, generation_config=gen_config)
        except Exception as e:
            print(f"Error configuring Gemini: {e}")
            return None
    return None

# Initialize model instance for strict gemini-2.5-flash
model = get_gemini_model()

def _get_gemini_text(response):
    """
    Safely extract plain text from a Gemini generate_content response.
    Avoids using response.text quick accessor which can fail if no Parts exist.
    Returns an empty string if no usable text is found.
    """
    if not response:
        return ""
    try:
        # Newer SDKs expose candidates/content/parts
        if getattr(response, "candidates", None):
            for cand in response.candidates:
                content = getattr(cand, "content", None)
                if not content or not getattr(content, "parts", None):
                    continue
                texts = []
                for part in content.parts:
                    # part could be a dict-like or object with .text
                    text_val = getattr(part, "text", None)
                    if text_val:
                        texts.append(text_val)
                    elif isinstance(part, dict) and part.get("text"):
                        texts.append(part["text"])
                if texts:
                    return "\n".join(texts).strip()
        # Fallback: some SDK versions still provide .text as a best-effort
        if hasattr(response, "text") and response.text:
            return str(response.text).strip()
    except Exception as e:
        print(f"Error extracting Gemini text: {str(e)}")
        # Never crash caller because of parsing issues
        return ""
    return ""

def clean_json_text(text):
    """Clean JSON text from markdown blocks and common errors."""
    if not text:
        return ""
        
    # Remove markdown code blocks
    if "```" in text:
        start = text.find("```")
        end = text.rfind("```")
        if end > start:
            # Check if there's a language identifier like ```json
            first_line_end = text.find("\n", start)
            if first_line_end != -1 and first_line_end < end:
                text = text[first_line_end:end]
            else:
                text = text[start+3:end]
    
    text = text.strip()
    
    # Fix common JSON errors
    # 1. Remove trailing commas before closing braces/brackets
    # Matches , followed by whitespace and } or ]
    text = re.sub(r',\s*([\]}])', r'\1', text)
    
    # 2. Fix invalid escape sequences
    # We want to escape backslashes that are NOT part of a valid JSON escape sequence
    # Valid escapes: \", \\, \/, \b, \f, \n, \r, \t, \uXXXX
    text = re.sub(r'\\(?!(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))', r'\\\\', text)
    
    # 3. Remove control characters
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    
    # 4. Extract JSON object if it's embedded in other text
    # Find the first { and the last }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        text = text[start:end+1]
        
    return text

def ask_gemini(prompt, history=None, attachment_path=None):
    # Greeting/Non-technical detection
    greeting_keywords = {"hi", "hello", "welcome", "hey", "greetings"}
    cleaned = prompt.strip().lower()
    # Only consider it a greeting if it's an exact match or very short and starts with a greeting
    # AND there is no attachment (if user uploads a file and says "hi", they probably want analysis)
    is_greeting = (cleaned in greeting_keywords or (len(cleaned) < 10 and any(cleaned.startswith(w) for w in greeting_keywords))) and not attachment_path

    if is_greeting and not history: # Only return static greeting if it's the very first message
        html = "<b>Hi there! 👋</b><br>I am your Gemini chatbot. Ask me anything, request code, or type a command to get started!"
        return html

    # Build context from history
    context_str = ""
    
    # RAG Context Retrieval (with quick safety try/except)
    try:
        rag_context = rag_utils.get_relevant_context(prompt)
        if rag_context:
            context_str += f"Relevant information from Knowledge Base:\n{rag_context}\n\n"
    except Exception as rag_err:
        print(f"RAG Retrieval skipped: {rag_err}")

    if history:
        context_str += "Previous conversation history:\n"
        for msg in history:
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = msg.get("content", "")
            context_str += f"{role}: {content}\n"
        context_str += "\n"

    format_prompt = (
        "You are a helpful AI assistant. Respond to the user's request on ANY topic (coding, general knowledge, creative writing, etc.).\n\n"
        f"{context_str}"
        "Answer style:\n"
        "- Be helpful, friendly, and direct.\n"
        "- Keep answers concise and well-structured unless the user asks for a detailed explanation.\n"
        "- If the user says words like 'detailed', 'explain step by step', or 'in depth', then you may give a longer answer.\n\n"
        "Formatting rules:\n"
        "- Output ONLY a valid HTML fragment (no <!DOCTYPE>, <html>, <head>, or <body> tags).\n"
        "- Start with a concise 1–2 sentence summary of the answer.\n"
        "- For any code, ALWAYS wrap it in <pre><code>...</code></pre>.\n"
        "- For any console/sample output, wrap it in <pre>...</pre>.\n"
        "- Use <b>, <ul>, <ol>, <li>, <p>, and <br> for structure and readability.\n"
        "- Do NOT use Markdown code fences like ```; use HTML tags only.\n"
        "- Do NOT restate the user prompt; just answer it.\n"
        "- **Mathematical Formulas:**\n"
        "  - Use LaTeX for all mathematical formulas.\n"
        "  - Wrap block equations in double dollar signs: $$ ... $$\n"
        "  - Wrap inline equations in single dollar signs: $ ... $\n"
        "  - Example: The area of a circle is $ A = \\pi r^2 $.\n\n"
        "User request:\n"
        f"{prompt}"
    )
    
    model = get_gemini_model()
    if model is None:
        return "<p><b>AI Chatbot Unavailable.</b><br>Please configure the Gemini API key in settings.</p>"

    try:
        content_parts = [format_prompt]
        
        if attachment_path and os.path.exists(attachment_path):
            ext = os.path.splitext(attachment_path)[1].lower()
            if ext in ['.png', '.jpg', '.jpeg', '.webp'] and PIL_AVAILABLE:
                try:
                    img = Image.open(attachment_path)
                    content_parts.append(img)
                    print(f"Loaded image directly via PIL: {attachment_path}")
                except Exception as img_err:
                    print(f"Error reading image with PIL: {img_err}")
                    try:
                        uploaded_file = genai.upload_file(attachment_path)
                        content_parts.append(uploaded_file)
                    except Exception as u_err:
                        print(f"Error uploading file: {u_err}")
            elif ext == '.pdf' and PYPDF_AVAILABLE:
                try:
                    reader = PdfReader(attachment_path)
                    pdf_text = "\n".join([page.extract_text() or "" for page in reader.pages[:15]])
                    if pdf_text.strip():
                        filename = os.path.basename(attachment_path)
                        # Index document chunks into Pinecone Vector Database
                        pinecone_utils.index_document_text("chat_documents", filename, pdf_text)
                        
                        # Query Pinecone Vector Database for relevant chunks
                        pine_results = pinecone_utils.query_vectors("chat_documents", prompt, top_k=4)
                        if pine_results:
                            pine_context = "\n".join([f"- {r['text']}" for r in pine_results])
                            content_parts[0] += f"\n\n[Pinecone Vector DB Context ({filename})]:\n{pine_context}"
                        else:
                            content_parts[0] += f"\n\nAttached Document Content:\n{pdf_text[:5000]}"
                except Exception as pdf_err:
                    print(f"Error processing PDF with Pinecone: {pdf_err}")
            elif ext in ['.txt', '.py', '.js', '.html', '.css', '.json', '.c', '.java', '.cpp', '.md']:
                try:
                    with open(attachment_path, 'r', encoding='utf-8', errors='ignore') as f:
                        file_text = f.read()
                    filename = os.path.basename(attachment_path)
                    pinecone_utils.index_document_text("chat_documents", filename, file_text)
                    pine_results = pinecone_utils.query_vectors("chat_documents", prompt, top_k=4)
                    if pine_results:
                        pine_context = "\n".join([f"- {r['text']}" for r in pine_results])
                        content_parts[0] += f"\n\n[Pinecone Vector DB Context ({filename})]:\n{pine_context}"
                    else:
                        content_parts[0] += f"\n\nAttached Code/Text ({filename}):\n{file_text[:5000]}"
                except Exception as f_err:
                    print(f"Error processing text attachment with Pinecone: {f_err}")
            else:
                try:
                    uploaded_file = genai.upload_file(attachment_path)
                    content_parts.append(uploaded_file)
                except Exception as u_err:
                    print(f"Error uploading file: {u_err}")

        response, err = generate_content_with_fallback(content_parts)
        if err:
            return f"<p><b>Error processing request.</b><br>{err}</p>"
            
        answer = _get_gemini_text(response)
        
        if not answer:
            return "<p><b>Sorry, I couldn't generate a response right now.</b><br>Please try again in a moment.</p>"
        return answer
        
    except Exception as e:
        print(f"Error in ask_gemini: {str(e)}")
        return f"<p><b>Error processing request.</b><br>{str(e)}</p>"

def get_video_id(yt_url):
    match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", yt_url)
    return match.group(1) if match else None

def generate_otp(length=6):
    """Generate a random OTP."""
    return ''.join(random.choices(string.digits, k=length))

def _send_otp_email_thread(recipient_email, otp, purpose="signup"):
    """Internal function to send OTP email (runs in thread)."""
    try:
        logging.info(f"Starting email send to {recipient_email} for {purpose}")
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = recipient_email
        
        if purpose == "signup":
            msg['Subject'] = "Verify Your Email - LernyX"
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9;">
                    <h2 style="color: #2563eb;">Email Verification</h2>
                    <p>Hello,</p>
                    <p>Thank you for signing up for LernyX! Please use the following OTP to verify your email address and complete your account creation:</p>
                    <div style="background-color: #ffffff; border: 2px solid #2563eb; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0;">
                        <h1 style="color: #2563eb; font-size: 32px; margin: 0; letter-spacing: 5px;">{otp}</h1>
                    </div>
                    <p>This OTP is valid for 10 minutes. Do not share this code with anyone.</p>
                    <p>If you did not create an account, please ignore this email.</p>
                    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                    <p style="color: #666; font-size: 12px;">This is an automated message from LernyX.</p>
                </div>
            </body>
            </html>
            """
        else:  # password reset
            msg['Subject'] = "Password Reset OTP - LernyX"
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9;">
                    <h2 style="color: #2563eb;">Password Reset Request</h2>
                    <p>Hello,</p>
                    <p>You have requested to reset your password for your LernyX account. Please use the following OTP to verify your identity:</p>
                    <div style="background-color: #ffffff; border: 2px solid #2563eb; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0;">
                        <h1 style="color: #2563eb; font-size: 32px; margin: 0; letter-spacing: 5px;">{otp}</h1>
                    </div>
                    <p>This OTP is valid for 10 minutes. Do not share this code with anyone.</p>
                    <p>If you did not request a password reset, please ignore this email and your password will remain unchanged.</p>
                    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                    <p style="color: #666; font-size: 12px;">This is an automated message from LernyX.</p>
                </div>
            </body>
            </html>
            """
        
        msg.attach(MIMEText(body, 'html'))
        text = msg.as_string()
        
        # Brevo uses port 587 with STARTTLS, but sometimes 2525 works better in cloud envs
        ports_to_try = [SMTP_PORT, 587]
        
        for port in ports_to_try:
            try:
                logging.info(f"Connecting to SMTP server {SMTP_SERVER}:{port}")
                print(f"Attempting to send email via STARTTLS (Port {port})...")
                
                server = smtplib.SMTP(SMTP_SERVER, port, timeout=20)
                server.set_debuglevel(1) 
                print(f"Connected to {SMTP_SERVER}:{port}")
                
                server.starttls()
                print("TLS started")
                
                server.login(SMTP_USERNAME, EMAIL_PASSWORD)
                print("Logged in successfully")
                
                server.sendmail(EMAIL_ADDRESS, recipient_email, text)
                server.quit()
                
                print(f"Email sent successfully to {recipient_email} via Port {port}")
                logging.info(f"Email sent successfully to {recipient_email} via Port {port}")
                return True
            except Exception as e:
                print(f"Failed to send email on port {port}: {str(e)}")
                logging.error(f"Failed to send email on port {port}: {str(e)}")
                # Continue to next port if available
                continue
        
        return False
    except Exception as e:
        print(f"Error preparing email: {str(e)}")
        logging.error(f"Error preparing email: {str(e)}")
        return False

def send_otp_email(recipient_email, otp, purpose="signup"):
    """Send OTP email synchronously (required for Vercel/Serverless)."""
    # In serverless environments like Vercel, background threads are killed
    # when the main request finishes. We must send synchronously.
    logging.info(f"Queueing email to {recipient_email}")
    return _send_otp_email_thread(recipient_email, otp, purpose)


def generate_quiz_code(length=6):
    """Generate a unique alphanumeric quiz code."""
    if not MONGODB_AVAILABLE:
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
        existing = custom_quizzes_collection.find_one({"code": code})
        if not existing:
            return code

def is_educational_content(content):
    """Check if the video content is educational using Gemini AI."""
    if not content or len(content.strip()) < 50:
        return False, "Insufficient content to determine if video is educational."
    
    # Sample first 2000 characters for quick analysis
    sample_content = content[:2000] if len(content) > 2000 else content
    
    educational_check_prompt = (
        "Analyze the following YouTube video content and determine if it is educational. "
        "Educational videos include: tutorials, lectures, courses, how-to guides, explanations, "
        "documentaries, science videos, history, language learning, programming tutorials, "
        "academic content, skill-building content, etc.\n\n"
        "Non-educational videos include: entertainment, music videos, vlogs, gaming streams, "
        "pranks, challenges, reaction videos, pure entertainment content, etc.\n\n"
        "Respond with ONLY a JSON object in this exact format:\n"
        '{"is_educational": true or false, "reason": "brief explanation"}\n\n'
        f"Video Content:\n{sample_content}\n\n"
        "Remember: Return ONLY the JSON object, nothing else."
    )
    
    try:
        response, err = generate_content_with_fallback(educational_check_prompt)
        if err:
            return True, "AI educational check temporarily unavailable; allowing video."
            
        response_text = _get_gemini_text(response)
        if not response_text:
            # If AI returned nothing usable, fall back to heuristic check
            raise json.JSONDecodeError("empty AI response", "", 0)
        
        # Clean up response if it has markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()
        elif response_text.startswith("```json"):
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        
        # Parse JSON response
        result = json.loads(response_text)
        is_educational = result.get("is_educational", False)
        reason = result.get("reason", "Unable to determine")
        
        return is_educational, reason
    except json.JSONDecodeError:
        # If JSON parsing fails, do a simple keyword check as fallback
        educational_keywords = [
            "tutorial", "learn", "course", "lesson", "explain", "how to", "guide",
            "education", "academic", "study", "teaching", "instruction", "lecture",
            "documentary", "science", "history", "mathematics", "programming", "coding",
            "skill", "knowledge", "concept", "theory", "practice", "training"
        ]
        content_lower = content.lower()
        has_educational_keywords = any(keyword in content_lower for keyword in educational_keywords)
        # Don't surface low-level errors to the user
        return has_educational_keywords, "Heuristic check based on keywords (AI analysis unavailable)."
    except Exception as e:
        error_text = str(e).lower()
        # If Gemini quota is exceeded or API unavailable, don't block the user
        if "quota" in error_text or "429" in error_text:
            # Allow the video and mark reason generically
            return True, "AI educational check temporarily unavailable due to rate limits; allowing video."

        # Generic fallback to keyword check on any other error
        educational_keywords = [
            "tutorial", "learn", "course", "lesson", "explain", "how to", "guide",
            "education", "academic", "study", "teaching", "instruction", "lecture",
            "documentary", "science", "history", "mathematics", "programming", "coding",
            "skill", "knowledge", "concept", "theory", "practice", "training"
        ]
        content_lower = content.lower()
        has_educational_keywords = any(keyword in content_lower for keyword in educational_keywords)
        return has_educational_keywords, "Heuristic check based on keywords (AI analysis unavailable)."

def get_video_metadata(video_id, yt_url):
    """Get video metadata (title, description) as fallback when transcript is not available."""
    metadata = None
    error_log = []
    print(f"get_video_metadata called for {video_id}")
    
    # Method 1: Try requests + BeautifulSoup first (more reliable, doesn't have API issues)
    if REQUESTS_AVAILABLE:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            response = requests.get(yt_url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Try to get title
                title = ""
                title_tag = soup.find('meta', property='og:title')
                if title_tag:
                    title = title_tag.get('content', '').strip()
                if not title:
                    title_tag = soup.find('title')
                    if title_tag:
                        title = title_tag.text.replace(' - YouTube', '').strip()
                
                # Try to get description - multiple methods
                description = ""
                # Method 1: og:description meta tag
                desc_tag = soup.find('meta', property='og:description')
                if desc_tag:
                    description = desc_tag.get('content', '').strip()
                
                # Method 2: Find in script tags (YouTube stores it in JSON-LD or ytInitialData)
                if not description:
                    scripts = soup.find_all('script')
                    for script in scripts:
                        if script.string:
                            script_text = script.string
                            # Try to find shortDescription
                            if 'shortDescription' in script_text:
                                # Try multiple regex patterns
                                patterns = [
                                    r'"shortDescription":"([^"]+)"',
                                    r'"shortDescription":"(.*?)"',
                                    r'shortDescription["\']?\s*:\s*["\']([^"\']+)["\']',
                                ]
                                for pattern in patterns:
                                    match = re.search(pattern, script_text, re.DOTALL)
                                    if match:
                                        desc_text = match.group(1)
                                        # Unescape common escape sequences
                                        desc_text = desc_text.replace('\\n', '\n').replace('\\"', '"').replace("\\'", "'")
                                        if len(desc_text) > 20:  # Only use if substantial
                                            description = desc_text
                                            break
                                if description:
                                    break
                            
                            # Try to find description in ytInitialData
                            if not description and 'ytInitialData' in script_text:
                                try:
                                    # Extract the JSON part
                                    start = script_text.find('var ytInitialData = ') + len('var ytInitialData = ')
                                    end = script_text.find('};', start) + 1
                                    if end > start:
                                        json_str = script_text[start:end]
                                        data = json.loads(json_str)
                                        # Navigate through the nested structure to find description
                                        if 'contents' in data:
                                            contents = data['contents']
                                            if 'twoColumnWatchNextResults' in contents:
                                                results = contents['twoColumnWatchNextResults']
                                                if 'results' in results and 'results' in results['results']:
                                                    results2 = results['results']['results']
                                                    if 'contents' in results2:
                                                        for item in results2['contents']:
                                                            if 'videoSecondaryInfoRenderer' in item:
                                                                renderer = item['videoSecondaryInfoRenderer']
                                                                if 'description' in renderer:
                                                                    desc_renderer = renderer['description']
                                                                    if 'runs' in desc_renderer:
                                                                        desc_parts = []
                                                                        for run in desc_renderer['runs']:
                                                                            if 'text' in run:
                                                                                desc_parts.append(run['text'])
                                                                        if desc_parts:
                                                                            description = '\n'.join(desc_parts)
                                                                            break
                                except:
                                    pass
                
                if title or description:
                    metadata = {
                        "title": title,
                        "description": description,
                        "length": None
                    }
            else:
                error_log.append(f"Requests: Status code {response.status_code}")
        except Exception as e:
            error_log.append(f"Requests error: {str(e)}")
            pass
    
    # Method 1.2: Try YouTube oEmbed (Very reliable for Title)
    if not metadata and REQUESTS_AVAILABLE:
        try:
            oembed_url = f"https://www.youtube.com/oembed?url={yt_url}&format=json"
            response = requests.get(oembed_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                title = data.get("title", "")
                if title:
                    metadata = {
                        "title": title,
                        "description": "Description unavailable (fetched via oEmbed)",
                        "length": None
                    }
        except Exception as e:
            error_log.append(f"oEmbed error: {str(e)}")
            pass

    # Method 1.5: Try Invidious API (good for bypassing IP blocks)
    if not metadata and REQUESTS_AVAILABLE:
        invidious_instances = [
            "https://inv.nadeko.net",
            "https://invidious.jing.rocks",
            "https://invidious.nerdvpn.de",
            "https://yt.artemislena.eu",
            "https://invidious.privacyredirect.com",
            "https://inv.tux.pizza",
            "https://vid.puffyan.us",
        ]
        for instance in invidious_instances:
            try:
                api_url = f"{instance}/api/v1/videos/{video_id}"
                response = requests.get(api_url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    title = data.get("title", "")
                    description = data.get("description", "")
                    if title or description:
                        metadata = {
                            "title": title,
                            "description": description,
                            "length": data.get("lengthSeconds")
                        }
                        break
            except Exception as e:
                error_log.append(f"Invidious ({instance}) error: {str(e)}")
                continue
        if not metadata:
            error_log.append("All Invidious instances failed")

    # Method 2: Try yt-dlp (most robust)
    if not metadata and YT_DLP_AVAILABLE:
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'ignoreerrors': True,  # Don't stop on error
                'extract_flat': True,  # Faster, just get metadata
                'socket_timeout': 10,  # Prevent hanging
            }
            
            # Check for cookies env var to bypass bot detection
            cookies_content = os.environ.get("YOUTUBE_COOKIES_CONTENT")
            cookies_file = None
            if cookies_content:
                # Create a temporary file for cookies
                cookies_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt')
                cookies_file.write(cookies_content)
                cookies_file.close()
                ydl_opts['cookiefile'] = cookies_file.name
                
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(yt_url, download=False)
                if info:
                    title = info.get('title', '')
                    description = info.get('description', '')
                    if title or description:
                        metadata = {
                            "title": title,
                            "description": description,
                            "length": info.get('duration')
                        }
                else:
                    error_log.append("yt-dlp returned no info")
            
            # Clean up temp cookies file
            if cookies_file and os.path.exists(cookies_file.name):
                os.unlink(cookies_file.name)
                
        except Exception as e:
            error_log.append(f"yt-dlp error: {str(e)}")
            # Clean up temp cookies file in case of error
            if 'cookies_file' in locals() and cookies_file and os.path.exists(cookies_file.name):
                os.unlink(cookies_file.name)
            pass

    # Method 3: Try pytube as fallback (may have API issues but worth trying)
    if not metadata and PYTUBE_AVAILABLE:
        try:
            yt = YouTube(yt_url)
            title = yt.title or ""
            description = yt.description or ""
            if title or description:
                metadata = {
                    "title": title,
                    "description": description,
                    "length": yt.length if hasattr(yt, 'length') else None
                }
        except Exception as e:
            error_log.append(f"Pytube error: {str(e)}")
            pass
    
    return metadata, error_log

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return render_template('landing.html')

@app.route('/sw.js')
def service_worker():
    response = send_file('static/sw.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/google10c68f1d7dfe2f5f.html')
def google_verification():
    return "google-site-verification: google10c68f1d7dfe2f5f.html", 200, {'Content-Type': 'text/html'}

@app.route('/sitemap.xml')
def sitemap():
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <!-- Landing Page -->
  <url>
    <loc>https://lernyx.vercel.app/</loc>
    <lastmod>2026-01-02</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  
  <!-- Login -->
  <url>
    <loc>https://lernyx.vercel.app/login</loc>
    <lastmod>2026-01-02</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.9</priority>
  </url>
  
  <!-- AI Chatbot -->
  <url>
    <loc>https://lernyx.vercel.app/chat</loc>
    <lastmod>2026-01-02</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
  </url>
  
  <!-- Video Quiz Generator -->
  <url>
    <loc>https://lernyx.vercel.app/videoquiz</loc>
    <lastmod>2026-01-02</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
  </url>
  
  <!-- Aptitude Practice -->
  <url>
    <loc>https://lernyx.vercel.app/aptitude-quiz</loc>
    <lastmod>2026-01-02</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
  </url>
  
  <!-- Code Compiler -->
  <url>
    <loc>https://lernyx.vercel.app/compiler</loc>
    <lastmod>2026-01-02</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
  </url>
</urlset>"""
    return sitemap_xml, 200, {'Content-Type': 'application/xml'}

@app.route('/robots.txt')
def robots():
    robots_txt = "User-agent: *\nAllow: /\n\n# Sitemaps\nSitemap: https://lernyx.vercel.app/sitemap.xml"
    return robots_txt, 200, {'Content-Type': 'text/plain'}

@app.route("/compiler")
@login_required
def compiler():
    return render_template("compiler.html")

def execute_code_engine(language, source_code, stdin=""):
    """
    Executes code using Piston v2 API (primary), Wandbox API (secondary),
    Judge0 CE API (tertiary), or Local Subprocess execution (fallback).
    Returns dict: {"stdout": str, "stderr": str, "compile_output": str, "success": bool, "error": str}
    """
    lang_lower = str(language).lower().strip()

    # 1. Primary Execution Engine: Piston v2 API (Free, high-speed public code runner)
    piston_map = {
        "python": ("python", "main.py"),
        "java": ("java", "Main.java"),
        "c": ("c", "main.c"),
        "cpp": ("c++", "main.cpp"),
        "c++": ("c++", "main.cpp")
    }

    if lang_lower in piston_map:
        p_lang, p_filename = piston_map[lang_lower]
        try:
            piston_payload = {
                "language": p_lang,
                "version": "*",
                "files": [{"name": p_filename, "content": source_code}],
                "stdin": stdin
            }
            resp = requests.post("https://emkc.org/api/v2/piston/execute", json=piston_payload, timeout=10)
            if resp.status_code == 200:
                res_data = resp.json()
                run_stage = res_data.get("run", {})
                compile_stage = res_data.get("compile", {})
                
                stdout = run_stage.get("stdout", "")
                stderr = run_stage.get("stderr", "")
                compile_err = compile_stage.get("output", "") or compile_stage.get("stderr", "")
                
                run_code = run_stage.get("code", 0) if run_stage else 0
                compile_code = compile_stage.get("code", 0) if compile_stage else 0
                
                is_success = (compile_code == 0) and (run_code == 0)
                
                return {
                    "stdout": stdout,
                    "stderr": stderr,
                    "compile_output": compile_err,
                    "success": is_success,
                    "error": None if is_success else (compile_err or stderr or "Execution failed")
                }
        except Exception as p_err:
            print(f"Piston API execution error: {p_err}")

    # 2. Secondary Execution Engine: Wandbox API
    wandbox_compiler_map = {
        "python": "cpython-head",
        "java": "openjdk-head",
        "c": "gcc-head-c",
        "cpp": "gcc-head",
        "c++": "gcc-head"
    }
    compiler = wandbox_compiler_map.get(lang_lower, "cpython-head")
    try:
        payload = {
            "compiler": compiler,
            "code": source_code,
            "stdin": stdin
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Learnex-App"
        }
        response = requests.post("https://wandbox.org/api/compile.json", json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            res = response.json()
            status_code = str(res.get("status", "1"))
            stdout = res.get("program_output", "")
            stderr = res.get("program_error", "")
            compile_err = res.get("compiler_error", "") or res.get("compiler_output", "")
            
            is_success = (status_code == "0")
            return {
                "stdout": stdout,
                "stderr": stderr,
                "compile_output": compile_err,
                "success": is_success,
                "error": None if is_success else (compile_err or stderr or "Execution failed")
            }
    except Exception as e:
        print(f"Wandbox API execution error: {e}")

    # 3. Tertiary Execution Engine: Judge0 CE Public API
    judge0_map = {
        "c": 50,
        "cpp": 54,
        "c++": 54,
        "java": 62,
        "python": 71
    }
    if lang_lower in judge0_map:
        try:
            j_lang_id = judge0_map[lang_lower]
            j_payload = {
                "source_code": source_code,
                "language_id": j_lang_id,
                "stdin": stdin
            }
            j_resp = requests.post("https://ce.judge0.com/submissions?wait=true", json=j_payload, timeout=10)
            if j_resp.status_code in [200, 201]:
                j_data = j_resp.json()
                stdout = j_data.get("stdout") or ""
                stderr = j_data.get("stderr") or ""
                compile_output = j_data.get("compile_output") or ""
                status_id = j_data.get("status", {}).get("id", 0)
                is_success = (status_id == 3)
                return {
                    "stdout": stdout,
                    "stderr": stderr,
                    "compile_output": compile_output,
                    "success": is_success,
                    "error": None if is_success else j_data.get("status", {}).get("description", "Error")
                }
        except Exception as j_err:
            print(f"Judge0 API execution error: {j_err}")

    # 4. Local Subprocess Fallback (Local execution)
    import subprocess
    import tempfile
    import shutil
    
    if lang_lower == "python":
        import sys
        try:
            proc = subprocess.run(
                [sys.executable, "-c", source_code],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=5
            )
            return {
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "compile_output": "",
                "success": proc.returncode == 0,
                "error": None if proc.returncode == 0 else proc.stderr
            }
        except Exception as py_err:
            print(f"Local python execution error: {py_err}")

    elif lang_lower == "java":
        try:
            match = re.search(r'public\s+class\s+([A-Za-z0-9_]+)', source_code)
            class_name = match.group(1) if match else "Main"
            
            with tempfile.TemporaryDirectory() as temp_dir:
                java_file = os.path.join(temp_dir, f"{class_name}.java")
                with open(java_file, "w", encoding="utf-8") as f:
                    f.write(source_code)
                
                compile_proc = subprocess.run(
                    ["javac", java_file],
                    capture_output=True,
                    text=True,
                    timeout=8
                )
                if compile_proc.returncode != 0:
                    return {
                        "stdout": "",
                        "stderr": compile_proc.stderr,
                        "compile_output": compile_proc.stderr,
                        "success": False,
                        "error": "Java Compilation Error"
                    }
                
                run_proc = subprocess.run(
                    ["java", "-cp", temp_dir, class_name],
                    input=stdin,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                return {
                    "stdout": run_proc.stdout,
                    "stderr": run_proc.stderr,
                    "compile_output": "",
                    "success": run_proc.returncode == 0,
                    "error": None if run_proc.returncode == 0 else run_proc.stderr
                }
        except Exception as java_err:
            print(f"Local Java execution error: {java_err}")

    elif lang_lower in ["c", "cpp"]:
        try:
            compiler_cmd = "gcc" if lang_lower == "c" else "g++"
            if not shutil.which(compiler_cmd):
                compiler_cmd = "clang" if lang_lower == "c" else "clang++"
                
            if shutil.which(compiler_cmd):
                with tempfile.TemporaryDirectory() as temp_dir:
                    src_file = os.path.join(temp_dir, f"main.{lang_lower}")
                    exe_file = os.path.join(temp_dir, "program.exe" if os.name == "nt" else "program")
                    with open(src_file, "w", encoding="utf-8") as f:
                        f.write(source_code)
                    
                    compile_proc = subprocess.run(
                        [compiler_cmd, src_file, "-o", exe_file],
                        capture_output=True,
                        text=True,
                        timeout=8
                    )
                    if compile_proc.returncode != 0:
                        return {
                            "stdout": "",
                            "stderr": compile_proc.stderr,
                            "compile_output": compile_proc.stderr,
                            "success": False,
                            "error": "C/C++ Compilation Error"
                        }
                    
                    run_proc = subprocess.run(
                        [exe_file],
                        input=stdin,
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    return {
                        "stdout": run_proc.stdout,
                        "stderr": run_proc.stderr,
                        "compile_output": "",
                        "success": run_proc.returncode == 0,
                        "error": None if run_proc.returncode == 0 else run_proc.stderr
                    }
        except Exception as c_err:
            print(f"Local C execution error: {c_err}")

    return {
        "stdout": "",
        "stderr": "Remote code execution service unavailable. Please check your network connection.",
        "compile_output": "",
        "success": False,
        "error": "Execution service unavailable"
    }

@app.route("/api/execute_code", methods=["POST"])
@login_required
def execute_code():
    if not REQUESTS_AVAILABLE:
        return jsonify({"error": "Requests library not available"}), 500
        
    data = request.json
    source_code = data.get("source_code", "")
    language = data.get("language", "java")
    stdin = data.get("stdin", "")
    
    if not source_code:
        return jsonify({"error": "Source code is required"}), 400

    result = execute_code_engine(language, source_code, stdin)
    
    return jsonify({
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "compile_output": result["compile_output"],
        "status": {"description": "Accepted" if result["success"] else "Error"}
    })

@app.route("/api/submit_code", methods=["POST"])
@login_required
def submit_code():
    """Validate solution against test cases and award points."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
        
    data = request.json
    source_code = data.get("source_code", "")
    language = data.get("language", "java")
    question_id = data.get("question_id")
    
    if not source_code or not question_id:
        return jsonify({"error": "Missing code or question ID"}), 400
        
    # Check if already solved
    user_data = users_collection.find_one({"_id": ObjectId(current_user.id)})
    solved_questions = [str(qid) for qid in user_data.get("solved_questions", [])] if user_data else []
    
    if str(question_id) in solved_questions:
        return jsonify({"error": "You have already solved this question."}), 400
        
    try:
        # Fetch question
        question = db.dsa_questions.find_one({"_id": ObjectId(question_id)})
        if not question:
            return jsonify({"error": "Question not found"}), 404
            
        test_cases = question.get("test_cases", [])
        if not test_cases:
            return jsonify({"error": "No test cases found"}), 400
            
        final_source_code = source_code
        
        results = []
        all_passed = True
        
        for i, case in enumerate(test_cases):
            res = execute_code_engine(language, final_source_code, case["input"])
            stdout = res["stdout"].strip()
            expected = case["output"].strip()
            
            passed = (stdout == expected)
            if not passed:
                all_passed = False
                
            results.append({
                "case_index": i + 1,
                "passed": passed,
                "input": case["input"] if not case.get("hidden") else "Hidden",
                "expected": expected if not case.get("hidden") else "Hidden",
                "actual": stdout if not case.get("hidden") else "Hidden Output",
                "hidden": case.get("hidden", False)
            })
            
        points_awarded = 0
        new_total_score = current_user.dsa_score
        
        if all_passed:
            # Check if already solved
            user_data = users_collection.find_one({"_id": ObjectId(current_user.id)})
            solved_questions = user_data.get("solved_questions", [])
            
            if ObjectId(question_id) not in solved_questions:
                # Award points
                points = 1 if question.get("difficulty") == "Easy" else 4
                print(f"DEBUG: Awarding {points} points to {current_user.username} for question {question_id}")
                
                users_collection.update_one(
                    {"_id": ObjectId(current_user.id)},
                    {
                        "$inc": {"dsa_score": points},
                        "$push": {"solved_questions": ObjectId(question_id)}
                    }
                )
                points_awarded = points
                new_total_score += points
            else:
                print(f"DEBUG: User {current_user.username} already solved question {question_id}")
                
        return jsonify({
            "all_passed": all_passed,
            "results": results,
            "points_awarded": points_awarded,
            "new_total_score": new_total_score
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/api/questions", methods=["GET"])
@login_required
def get_questions():
    """Fetch all generated DSA questions."""
    if not MONGODB_AVAILABLE:
        return jsonify([]), 200
        
    try:
        # Fetch all questions including _id
        questions = list(db.dsa_questions.find({}).sort("created_at", -1))
        
        # Get user's solved questions
        user_data = users_collection.find_one({"_id": ObjectId(current_user.id)})
        solved_ids = [str(qid) for qid in user_data.get("solved_questions", [])] if user_data else []
        
        # Convert ObjectId to string for JSON serialization and add solved status
        for q in questions:
            q["_id"] = str(q["_id"])
            q["solved"] = q["_id"] in solved_ids
            
        return jsonify(questions)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/login", methods=["GET", "POST"])
def login():
    if not MONGODB_AVAILABLE:
        flash("Database connection unavailable. Please check MongoDB.", "error")
        return render_template("login.html")
    
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        if not username or not password:
            flash("Please fill in all fields.", "error")
            return render_template("login.html")
        
        # Find user by username or email (case-insensitive for email)
        user_data = users_collection.find_one({
            "$or": [
                {"username": username},
                {"email": {"$regex": f"^{re.escape(username)}$", "$options": "i"}}
            ]
        })
        
        if user_data and check_password_hash(user_data["password"], password):
            user = User(user_data["_id"], user_data["username"], user_data["email"])
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash("Invalid username/email or password.", "error")
    
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if not MONGODB_AVAILABLE:
        flash("Database connection unavailable. Please check MongoDB.", "error")
        return render_template("signup.html")
    
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        # Validation
        if not username or not email or not password:
            flash("Please fill in all fields.", "error")
            return render_template("signup.html")
        
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")
        
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_template("signup.html")
        
        # Check if user already exists
        existing_user = users_collection.find_one({
            "$or": [
                {"username": username},
                {"email": email}
            ]
        })
        
        if existing_user:
            if existing_user.get("username") == username:
                flash("Username already exists.", "error")
            else:
                flash("Email already registered.", "error")
            return render_template("signup.html")
        
        # Generate OTP and store in session
        otp = generate_otp()
        hashed_password = generate_password_hash(password)
        
        session['signup_data'] = {
            "username": username,
            "email": email,
            "password": hashed_password,
            "otp": otp,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Send OTP
        if send_otp_email(email, otp, purpose="signup"):
            flash("OTP sent to your email. Please verify to complete signup.", "info")
            return redirect(url_for('verify_signup'))
        else:
            flash("Failed to send OTP email. Please try again later.", "error")
            return render_template("signup.html")
    
    return render_template("signup.html")

@app.route("/verify-signup", methods=["GET", "POST"])
def verify_signup():
    if "signup_data" not in session:
        flash("Session expired. Please sign up again.", "error")
        return redirect(url_for('signup'))
    
    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()
        signup_data = session.get("signup_data")
        
        if entered_otp == signup_data.get("otp"):
            # Create user
            user_data = {
                "username": signup_data["username"],
                "email": signup_data["email"],
                "password": signup_data["password"],
                "created_at": datetime.now(timezone.utc)
            }
            users_collection.insert_one(user_data)
            
            # Clear session
            session.pop("signup_data", None)
            
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for('login'))
        else:
            flash("Invalid OTP. Please try again.", "error")
            
    return render_template("verify_signup.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for('index'))

@app.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    """Delete user account and all associated data."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    
    try:
        # Get user ID (handle both ObjectId and string)
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
        
        user_id_str = str(current_user.id)
        
        # Delete all user data from all collections
        # 1. Delete user account
        users_collection.delete_one({"_id": user_id_obj})
        
        # 2. Delete chat conversations
        chat_conversations_collection.delete_many({
            "$or": [
                {"user_id": user_id_obj},
                {"user_id": user_id_str}
            ]
        })
        
        # 3. Delete quiz scores
        quiz_scores_collection.delete_many({
            "$or": [
                {"user_id": user_id_obj},
                {"user_id": user_id_str}
            ]
        })
        
        # 4. Delete user quiz history
        user_quiz_history_collection.delete_many({
            "$or": [
                {"user_id": user_id_obj},
                {"user_id": user_id_str}
            ]
        })
        
        # 5. Delete custom quiz attempts
        custom_quiz_attempts_collection.delete_many({
            "$or": [
                {"user_id": user_id_obj},
                {"user_id": user_id_str}
            ]
        })
        
        # 6. Delete custom quizzes owned by user
        custom_quizzes_collection.delete_many({
            "$or": [
                {"owner_id": user_id_obj},
                {"owner_id": user_id_str}
            ]
        })
        
        # 7. Delete quizzes created by user (optional - you may want to keep these)
        quizzes_collection.delete_many({
            "$or": [
                {"created_by": user_id_obj},
                {"created_by": user_id_str}
            ]
        })

        # 8. Delete aptitude attempts
        aptitude_attempts_collection.delete_many({
            "$or": [
                {"user_id": user_id_obj},
                {"user_id": user_id_str}
            ]
        })
        
        # Logout user
        logout_user()
        
        return jsonify({
            "success": True,
            "message": "Account and all associated data have been deleted successfully."
        })
    except Exception as e:
        print(f"Error deleting account: {str(e)}")
        return jsonify({"error": f"Error deleting account: {str(e)}"}), 500

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Password reset request - send OTP to email."""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        
        if not email:
            flash("Please enter your email address.", "error")
            return render_template("forgot_password.html")
        
        # Check if user exists
        if not MONGODB_AVAILABLE or users_collection is None:
            flash("Database unavailable. Cannot reset password.", "error")
            return render_template("forgot_password.html")

        user_data = users_collection.find_one({"email": email})
        
        if not user_data:
            # Don't reveal if email exists or not for security
            flash("If an account exists with this email, you can reset your password.", "info")
            return render_template("forgot_password.html")
        
        # Generate OTP
        otp = generate_otp()
        
        # Store email and OTP in session
        session["reset_data"] = {
            "email": email,
            "otp": otp,
            "verified": False
        }
        
        # Send OTP
        if send_otp_email(email, otp, purpose="reset"):
            flash("OTP sent to your email. Please verify to reset password.", "info")
            return redirect(url_for('verify_reset_otp'))
        else:
            flash("Failed to send OTP email. Please try again later.", "error")
            return render_template("forgot_password.html")
    
    return render_template("forgot_password.html")

@app.route("/verify-reset-otp", methods=["GET", "POST"])
def verify_reset_otp():
    if "reset_data" not in session:
        flash("Session expired. Please request password reset again.", "error")
        return redirect(url_for('forgot_password'))
    
    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()
        reset_data = session.get("reset_data")
        
        if entered_otp == reset_data.get("otp"):
            # Mark as verified
            reset_data["verified"] = True
            session["reset_data"] = reset_data
            
            flash("OTP verified. Please set your new password.", "success")
            return redirect(url_for('reset_password'))
        else:
            flash("Invalid OTP. Please try again.", "error")
            
    return render_template("verify_reset_otp.html")

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Password reset - allow password change directly."""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    # Check if user has requested password reset
    # Check if user has requested password reset and verified OTP
    if "reset_data" not in session or not session["reset_data"].get("verified"):
        flash("Please verify OTP first.", "error")
        return redirect(url_for('forgot_password'))
    
    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        email = session["reset_data"]["email"]
        
        if not new_password or not confirm_password:
            flash("Please fill in all fields.", "error")
            return render_template("reset_password.html")
        
        # Verify passwords match
        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html")
        
        if len(new_password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_template("reset_password.html")
        
        # Update password
        hashed_password = generate_password_hash(new_password)
        users_collection.update_one(
            {"email": email},
            {"$set": {"password": hashed_password}}
        )
        
        # Clear session
        # Clear session
        session.pop("reset_data", None)
        
        flash("Password has been reset successfully! Please login with your new password.", "success")
        return redirect(url_for('login'))
    
    return render_template("reset_password.html")

@app.route("/update_api_key", methods=["POST"])
@login_required
def update_api_key():
    if not MONGODB_AVAILABLE:
        flash("Database unavailable.", "error")
        return redirect(url_for('dashboard'))
        
    api_key = request.form.get("api_key", "").strip()
    
    try:
        # Update user in database
        users_collection.update_one(
            {"_id": ObjectId(current_user.id)},
            {"$set": {"api_key": api_key}}
        )
        flash("API Key updated successfully.", "success")
    except Exception as e:
        print(f"Error updating API key: {str(e)}")
        flash("Failed to update API key.", "error")
        
    return redirect(url_for('dashboard'))

@app.route("/home")
@login_required
def home():
    return render_template("home.html")

@app.route("/dashboard")
@login_required
def dashboard():
    """Display user's past chats and quiz history."""
    if not MONGODB_AVAILABLE:
        flash("Database unavailable. Dashboard may be empty.", "error")
        return render_template("dashboard.html")

    return render_template("dashboard.html")

@app.route("/api/analyze-resume", methods=["POST"])
@login_required
def analyze_resume():
    if 'file' not in request.files:
        return jsonify({"error": "No resume file uploaded"}), 400
        
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"error": "Selected file is empty"}), 400
        
    target_role = request.form.get("target_role", "Software Engineer").strip()
    filename = secure_filename(file.filename).lower()
    
    extracted_text = ""
    image_obj = None
    
    try:
        if filename.endswith(".pdf"):
            if PYPDF_AVAILABLE:
                reader = PdfReader(file)
                for page in reader.pages:
                    txt = page.extract_text()
                    if txt:
                        extracted_text += txt + "\n"
            else:
                return jsonify({"error": "PDF processing engine unavailable"}), 500
        elif filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
            if PIL_AVAILABLE:
                image_obj = Image.open(file.stream)
            else:
                return jsonify({"error": "Image processing engine unavailable"}), 500
        elif filename.endswith((".txt", ".md")):
            extracted_text = file.read().decode('utf-8', errors='ignore')
        elif filename.endswith(".docx"):
            try:
                import docx
                doc = docx.Document(file)
                extracted_text = "\n".join([p.text for p in doc.paragraphs if p.text])
            except Exception:
                file.seek(0)
                extracted_text = file.read().decode('utf-8', errors='ignore')
        else:
            extracted_text = file.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return jsonify({"error": f"Failed to parse resume file: {str(e)}"}), 500

    if not extracted_text and not image_obj:
        return jsonify({"error": "Could not extract readable text from the uploaded resume file"}), 400

    # Index resume chunks into Pinecone Vector DB
    pinecone_context = ""
    if extracted_text:
        try:
            namespace = f"resume_{current_user.id}"
            pinecone_utils.index_document_text(namespace, filename, extracted_text)
            
            # Query Pinecone for relevant vector search chunks based on target role
            pine_matches = pinecone_utils.query_vectors(namespace, target_role, top_k=5)
            if pine_matches:
                pinecone_context = "\n".join([f"- {m['text']}" for m in pine_matches])
        except Exception as p_err:
            print(f"Pinecone resume indexing warning: {p_err}")

    model = get_gemini_model()
    if not model:
        return jsonify({"error": "AI model unavailable"}), 500

    prompt = f"""
You are an expert HR Executive, ATS (Applicant Tracking System) Specialist, and Senior Tech Recruiter.
Analyze the following resume for the target role: "{target_role}".

Provide a comprehensive, professional, highly actionable Resume Audit Report formatted in clean Markdown with emojis and GitHub alert boxes where appropriate.

Include the following sections clearly:

1. **Overall Resume Score**: Provide a numerical score out of 100 (e.g. **85 / 100**) with a 1-sentence executive verdict.
2. **Executive Summary**: High-level candidate impression and alignment for the role of "{target_role}".
3. **Key Strengths**: 3-5 major highlights that stand out positively.
4. **ATS & Formatting Audit**: Keyword optimization, formatting structure, impact metrics, readability.
5. **Critical Red Flags & Missing Elements**: Passive language, missing skills, unquantified achievements, formatting issues.
6. **Specific Step-by-Step Recommended Changes**:
   - Section-by-section improvements (Summary, Experience, Projects, Skills, Education).
   - "Before" vs "After" examples of how to rewrite weak bullet points using action verbs and measurable metrics.
7. **Tailored Interview Preparation**: 3 specific interview questions to prepare for based on this resume's project and experience details.

{"Pinecone Vector Database Top Matches:" + "\n" + pinecone_context if pinecone_context else ""}

Resume Document Content:
{extracted_text if extracted_text else "[Resume provided as attached image/document]"}
"""
    try:
        content_parts = [prompt, image_obj] if image_obj else prompt
        response, err = generate_content_with_fallback(content_parts, temperature=0.4)
        if err:
            return jsonify({"error": f"AI Generation Error: {err}"}), 500
            
        report = _get_gemini_text(response)

        # Store persistent resume review in MongoDB
        if MONGODB_AVAILABLE and resume_reviews_collection is not None:
            try:
                resume_reviews_collection.update_one(
                    {"user_id": str(current_user.id)},
                    {
                        "$set": {
                            "user_id": str(current_user.id),
                            "filename": file.filename,
                            "target_role": target_role,
                            "extracted_text": extracted_text,
                            "report": report,
                            "updated_at": datetime.now(timezone.utc)
                        }
                    },
                    upsert=True
                )
            except Exception as db_err:
                print(f"Error persisting resume review to MongoDB: {db_err}")

        return jsonify({"report": report, "filename": file.filename, "target_role": target_role})
    except Exception as e:
        return jsonify({"error": f"AI Resume Analysis failed: {str(e)}"}), 500

@app.route("/api/latest-resume-review", methods=["GET"])
@login_required
def get_latest_resume_review():
    if not MONGODB_AVAILABLE or resume_reviews_collection is None:
        return jsonify({"review": None})
    try:
        review = resume_reviews_collection.find_one({"user_id": str(current_user.id)})
        if not review:
            return jsonify({"review": None})
            
        return jsonify({
            "review": {
                "filename": review.get("filename"),
                "target_role": review.get("target_role"),
                "report": review.get("report"),
                "updated_at": review.get("updated_at").isoformat() if review.get("updated_at") else None
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def generate_resume_docx(data, template_id="classic_navy"):
    """
    Generates an ATS-friendly, professional Word (.docx) resume using python-docx with 5 selectable templates.
    """
    import io
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import parse_xml

    doc = docx.Document()

    # Template style configurations
    templates_config = {
        "classic_navy": {
            "primary": RGBColor(30, 58, 138),     # Navy #1E3A8A
            "secondary": RGBColor(59, 130, 246),  # Blue #3B82F6
            "dark": RGBColor(17, 24, 39),         # Charcoal #111827
            "muted": RGBColor(75, 85, 99),        # Gray #4B5563
            "border_color": "1E3A8A",
            "border_size": "12",
            "font_name": "Arial",
            "align_header": WD_ALIGN_PARAGRAPH.LEFT,
            "name_size": 22,
            "header_size": 12,
            "margin": 0.75
        },
        "minimal_executive": {
            "primary": RGBColor(31, 41, 55),      # Slate #1F2937
            "secondary": RGBColor(107, 114, 128), # Muted #6B7280
            "dark": RGBColor(17, 24, 39),         # Charcoal #111827
            "muted": RGBColor(107, 114, 128),     # Gray #6B7280
            "border_color": "D1D5DB",
            "border_size": "8",
            "font_name": "Georgia",
            "align_header": WD_ALIGN_PARAGRAPH.CENTER,
            "name_size": 24,
            "header_size": 12,
            "margin": 0.75
        },
        "tech_teal": {
            "primary": RGBColor(13, 148, 136),    # Teal #0D9488
            "secondary": RGBColor(20, 184, 166),  # Light Teal #14B8A6
            "dark": RGBColor(17, 24, 39),         # Dark Gray #111827
            "muted": RGBColor(75, 85, 99),        # Gray #4B5563
            "border_color": "0D9488",
            "border_size": "14",
            "font_name": "Segoe UI",
            "align_header": WD_ALIGN_PARAGRAPH.LEFT,
            "name_size": 22,
            "header_size": 12,
            "margin": 0.65
        },
        "creative_burgundy": {
            "primary": RGBColor(136, 19, 55),     # Burgundy #881337
            "secondary": RGBColor(159, 18, 57),   # Rose #9F1239
            "dark": RGBColor(24, 24, 27),         # Off Black #18181B
            "muted": RGBColor(82, 82, 91),        # Neutral Gray #52525B
            "border_color": "881337",
            "border_size": "12",
            "font_name": "Calibri",
            "align_header": WD_ALIGN_PARAGRAPH.LEFT,
            "name_size": 23,
            "header_size": 12,
            "margin": 0.7
        },
        "ats_standard": {
            "primary": RGBColor(0, 0, 0),         # Pure Black #000000
            "secondary": RGBColor(51, 51, 51),    # Dark Gray #333333
            "dark": RGBColor(0, 0, 0),            # Black #000000
            "muted": RGBColor(75, 75, 75),        # Gray #4B4B4B
            "border_color": "000000",
            "border_size": "8",
            "font_name": "Times New Roman",
            "align_header": WD_ALIGN_PARAGRAPH.LEFT,
            "name_size": 20,
            "header_size": 11.5,
            "margin": 0.75
        }
    }

    cfg = templates_config.get(template_id, templates_config["classic_navy"])

    # Set page margins
    for section in doc.sections:
        section.top_margin = Inches(cfg["margin"])
        section.bottom_margin = Inches(cfg["margin"])
        section.left_margin = Inches(cfg["margin"])
        section.right_margin = Inches(cfg["margin"])

    PRIMARY_COLOR = cfg["primary"]
    TEXT_DARK = cfg["dark"]
    TEXT_MUTED = cfg["muted"]
    FONT_NAME = cfg["font_name"]

    def add_section_header(title):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(title.upper())
        run.bold = True
        run.font.size = Pt(cfg["header_size"])
        run.font.color.rgb = PRIMARY_COLOR
        run.font.name = FONT_NAME
        
        # Add bottom border under heading XML
        pPr = p._p.get_or_add_pPr()
        pBdr = parse_xml(f'<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                         f'<w:bottom w:val="single" w:sz="{cfg["border_size"]}" w:space="4" w:color="{cfg["border_color"]}"/>'
                         f'</w:pBdr>')
        pPr.append(pBdr)

    # 1. Header Section (Name & Target Role & Contact)
    name = data.get("full_name") or data.get("name") or "Candidate Name"
    target_role = data.get("target_role") or "Software Engineer"
    contact_info = data.get("contact", {})

    p_name = doc.add_paragraph()
    p_name.paragraph_format.space_before = Pt(0)
    p_name.paragraph_format.space_after = Pt(2)
    p_name.alignment = cfg["align_header"]
    run_name = p_name.add_run(name)
    run_name.bold = True
    run_name.font.size = Pt(cfg["name_size"])
    run_name.font.color.rgb = PRIMARY_COLOR
    run_name.font.name = FONT_NAME

    p_role = doc.add_paragraph()
    p_role.paragraph_format.space_after = Pt(4)
    p_role.alignment = cfg["align_header"]
    run_role = p_role.add_run(target_role)
    run_role.bold = True
    run_role.font.size = Pt(12)
    run_role.font.color.rgb = TEXT_MUTED
    run_role.font.name = FONT_NAME

    # Contact Info Line
    contact_parts = []
    if isinstance(contact_info, dict):
        for k in ["email", "phone", "location", "linkedin", "github"]:
            if contact_info.get(k):
                contact_parts.append(str(contact_info[k]))
    elif isinstance(contact_info, list):
        contact_parts = [str(x) for x in contact_info]
    elif isinstance(contact_info, str) and contact_info:
        contact_parts = [contact_info]

    if contact_parts:
        p_contact = doc.add_paragraph()
        p_contact.paragraph_format.space_after = Pt(8)
        p_contact.alignment = cfg["align_header"]
        run_contact = p_contact.add_run(" | ".join(contact_parts))
        run_contact.font.size = Pt(9.5)
        run_contact.font.color.rgb = TEXT_MUTED
        run_contact.font.name = FONT_NAME

    # 2. Professional Summary
    summary = data.get("summary")
    if summary:
        add_section_header("Professional Summary")
        p_sum = doc.add_paragraph()
        p_sum.paragraph_format.space_after = Pt(6)
        r_sum = p_sum.add_run(str(summary))
        r_sum.font.size = Pt(10)
        r_sum.font.color.rgb = TEXT_DARK
        r_sum.font.name = FONT_NAME

    # 3. Work Experience
    experience = data.get("experience", [])
    if experience:
        add_section_header("Work Experience")
        for exp in experience:
            p_exp = doc.add_paragraph()
            p_exp.paragraph_format.space_before = Pt(4)
            p_exp.paragraph_format.space_after = Pt(2)
            
            title = exp.get("title", "")
            company = exp.get("company", "")
            dates = exp.get("dates", "")
            location = exp.get("location", "")
            
            r_title = p_exp.add_run(title)
            r_title.bold = True
            r_title.font.size = Pt(11)
            r_title.font.color.rgb = TEXT_DARK
            r_title.font.name = FONT_NAME
            
            if company:
                r_comp = p_exp.add_run(f" — {company}")
                r_comp.italic = True
                r_comp.font.size = Pt(10.5)
                r_comp.font.color.rgb = TEXT_MUTED
                r_comp.font.name = FONT_NAME
                
            if dates or location:
                meta_str = " | ".join([x for x in [dates, location] if x])
                r_meta = p_exp.add_run(f"\n{meta_str}")
                r_meta.font.size = Pt(9)
                r_meta.font.color.rgb = TEXT_MUTED
                r_meta.font.name = FONT_NAME
                
            bullets = exp.get("bullets", [])
            for b in bullets:
                p_b = doc.add_paragraph(style='List Bullet')
                p_b.paragraph_format.space_after = Pt(2)
                p_b.paragraph_format.space_before = Pt(0)
                r_b = p_b.add_run(str(b))
                r_b.font.size = Pt(10)
                r_b.font.color.rgb = TEXT_DARK
                r_b.font.name = FONT_NAME

    # 4. Key Projects
    projects = data.get("projects", [])
    if projects:
        add_section_header("Key Projects")
        for proj in projects:
            p_p = doc.add_paragraph()
            p_p.paragraph_format.space_before = Pt(4)
            p_p.paragraph_format.space_after = Pt(2)
            
            p_name = proj.get("name", "")
            tech_stack = proj.get("tech_stack", "")
            
            r_pname = p_p.add_run(p_name)
            r_pname.bold = True
            r_pname.font.size = Pt(11)
            r_pname.font.color.rgb = TEXT_DARK
            r_pname.font.name = FONT_NAME
            
            if tech_stack:
                r_tech = p_p.add_run(f" ({tech_stack})")
                r_tech.italic = True
                r_tech.font.size = Pt(9.5)
                r_tech.font.color.rgb = PRIMARY_COLOR
                r_tech.font.name = FONT_NAME
                
            bullets = proj.get("bullets", [])
            for b in bullets:
                p_b = doc.add_paragraph(style='List Bullet')
                p_b.paragraph_format.space_after = Pt(2)
                p_b.paragraph_format.space_before = Pt(0)
                r_b = p_b.add_run(str(b))
                r_b.font.size = Pt(10)
                r_b.font.color.rgb = TEXT_DARK
                r_b.font.name = FONT_NAME

    # 5. Technical Skills
    skills = data.get("skills")
    if skills:
        add_section_header("Technical Skills")
        if isinstance(skills, dict):
            for cat, item_list in skills.items():
                p_sk = doc.add_paragraph()
                p_sk.paragraph_format.space_after = Pt(2)
                r_cat = p_sk.add_run(f"• {cat}: ")
                r_cat.bold = True
                r_cat.font.size = Pt(10)
                r_cat.font.color.rgb = TEXT_DARK
                r_cat.font.name = FONT_NAME
                
                items_str = ", ".join(item_list) if isinstance(item_list, list) else str(item_list)
                r_val = p_sk.add_run(items_str)
                r_val.font.size = Pt(10)
                r_val.font.color.rgb = TEXT_DARK
                r_val.font.name = FONT_NAME
        elif isinstance(skills, list):
            p_sk = doc.add_paragraph()
            p_sk.paragraph_format.space_after = Pt(4)
            r_sk = p_sk.add_run(", ".join([str(s) for s in skills]))
            r_sk.font.size = Pt(10)
            r_sk.font.color.rgb = TEXT_DARK
            r_sk.font.name = FONT_NAME

    # 6. Education & Certifications
    education = data.get("education", [])
    if education:
        add_section_header("Education & Certifications")
        for edu in education:
            p_e = doc.add_paragraph()
            p_e.paragraph_format.space_after = Pt(2)
            deg = edu.get("degree", "")
            inst = edu.get("institution", "")
            year = edu.get("year", "")
            score = edu.get("score", "")
            
            r_deg = p_e.add_run(deg)
            r_deg.bold = True
            r_deg.font.size = Pt(10.5)
            r_deg.font.color.rgb = TEXT_DARK
            r_deg.font.name = FONT_NAME
            
            if inst:
                r_inst = p_e.add_run(f" — {inst}")
                r_inst.font.size = Pt(10)
                r_inst.font.color.rgb = TEXT_MUTED
                r_inst.font.name = FONT_NAME
                
            if year or score:
                meta = " | ".join([x for x in [year, score] if x])
                r_m = p_e.add_run(f" ({meta})")
                r_m.font.size = Pt(9.5)
                r_m.font.color.rgb = TEXT_MUTED
                r_m.font.name = FONT_NAME

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

@app.route("/api/export-improved-resume-docx", methods=["POST", "GET"])
@login_required
def export_improved_resume_docx():
    """Generates and downloads a styled, ATS-optimized Word (.docx) resume preserving actual candidate details."""
    try:
        import io
        review = None
        if MONGODB_AVAILABLE and resume_reviews_collection is not None:
            review = resume_reviews_collection.find_one({"user_id": str(current_user.id)})
            
        target_role = "Software Engineer"
        report = ""
        extracted_text = ""
        
        if review:
            target_role = review.get("target_role", "Software Engineer")
            report = review.get("report", "")
            extracted_text = review.get("extracted_text", "")

        template_id = request.args.get("template")

        # Allow request JSON payload to override if provided
        if request.is_json and request.get_json():
            req_data = request.get_json()
            if req_data.get("resume_text"):
                extracted_text = req_data.get("resume_text")
            if req_data.get("target_role"):
                target_role = req_data.get("target_role")
            if req_data.get("report"):
                report = req_data.get("report")
            if req_data.get("template"):
                template_id = req_data.get("template")

        if not template_id and request.form:
            template_id = request.form.get("template")
            
        if not template_id:
            template_id = "classic_navy"

        if not extracted_text and not report:
            return jsonify({"error": "No saved resume text found. Please upload your resume first!"}), 400

        prompt = f"""
You are an expert ATS Resume Designer & Senior Tech Recruiter.
Generate a 100% complete, professionally rewritten, ATS-friendly resume JSON for the target role of "{target_role}".

STRICT MANDATORY RULES:
1. CANDIDATE DETAILS: Extract and preserve the candidate's EXACT REAL full name, REAL email, REAL phone number, REAL location, REAL LinkedIn URL, and REAL GitHub URL from the candidate's Original Resume Text below.
   - DO NOT use dummy placeholders like "Candidate Name", "John Doe", "email@example.com", or fake phone numbers.
2. PROJECTS & EXPERIENCE: Preserve ALL real project names (e.g. "Nyaya Vyavastha", "LernyX", "Fitness Tracking", "Automated Email Sender", "Real-time Weather Application") and companies from the original resume. Rewrite and enhance the bullet points using strong action verbs, quantifiable metrics (e.g., %, ms, ₹), and ATS keywords.
3. SKILLS & EDUCATION: Preserve candidate's exact real technical skills, degree, institution, years, and CGPA/score from the original resume.

RETURN ONLY A VALID JSON OBJECT (no markdown, no prose, just JSON) with this exact structure:
{{
  "full_name": "EXACT CANDIDATE REAL NAME FROM RESUME",
  "target_role": "{target_role}",
  "contact": {{
    "email": "exact candidate email from resume",
    "phone": "exact candidate phone number from resume",
    "location": "exact candidate location from resume",
    "linkedin": "exact candidate linkedin url from resume",
    "github": "exact candidate github url from resume"
  }},
  "summary": "3-4 sentence powerful executive summary tailored for {target_role}.",
  "experience": [
    {{
      "title": "Role Title",
      "company": "Company Name",
      "dates": "Dates",
      "location": "Location",
      "bullets": [
        "Enhanced bullet point with action verb and impact metric."
      ]
    }}
  ],
  "projects": [
    {{
      "name": "Exact Project Title from Resume",
      "tech_stack": "Exact Technologies Used",
      "bullets": [
        "Enhanced bullet point with action verb and impact metric."
      ]
    }}
  ],
  "skills": {{
    "Languages": ["..."],
    "Frameworks & Libraries": ["..."],
    "Databases & Cloud": ["..."],
    "Tools & Methodologies": ["..."]
  }},
  "education": [
    {{
      "degree": "Exact Degree Name",
      "institution": "Exact Institution / College Name",
      "year": "Years",
      "score": "CGPA / GPA / Percentage"
    }}
  ]
}}

Candidate Original Resume Text:
{extracted_text[:4500]}

AI Audit Report & Recommendations:
{report[:3500]}
"""
        response, err = generate_content_with_fallback(prompt, preferred_model="gemini-2.5-flash", temperature=0.1)
        if err or not response:
            return jsonify({"error": f"Failed to generate structured resume: {err}"}), 500
            
        txt = _get_gemini_text(response)
        clean_txt = clean_json_text(txt) if 'clean_json_text' in globals() else txt.replace("```json", "").replace("```", "").strip()
        resume_json = json.loads(clean_txt)
        
        docx_buffer = generate_resume_docx(resume_json, template_id=template_id)
        
        cand_name = resume_json.get("full_name", current_user.username).replace(" ", "_")
        safe_filename = f"Revised_Resume_{cand_name}_{template_id}.docx"
        return send_file(
            docx_buffer,
            as_attachment=True,
            download_name=safe_filename,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    except Exception as e:
        print(f"Error exporting improved resume DOCX: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to generate Word document: {str(e)}"}), 500

@app.route("/virtual-placement")
@login_required
def virtual_placement():
    """AI Virtual Placement Officer & LinkedIn Job Matcher page."""
    return render_template("virtual_placement.html")

@app.route("/api/career/virtual-assessment", methods=["POST"])
@login_required
def virtual_career_assessment():
    try:
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form

        target_role = data.get("target_role", "Software Engineer").strip()
        relocate = data.get("relocate", "Yes").strip()
        preferred_locations = data.get("preferred_locations", "Hyderabad").strip()
        work_mode = data.get("work_mode", "onsite").strip().lower()
        answers = data.get("answers", "")
        
        extracted_resume_text = ""
        image_obj = None

        # 1. Check if a fresh resume file is uploaded in the request
        if 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']
            filename = secure_filename(file.filename).lower()
            try:
                if filename.endswith(".pdf"):
                    if PYPDF_AVAILABLE:
                        reader = PdfReader(file)
                        for page in reader.pages:
                            txt = page.extract_text()
                            if txt:
                                extracted_resume_text += txt + "\n"
                elif filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
                    if PIL_AVAILABLE:
                        image_obj = Image.open(file.stream)
                elif filename.endswith((".txt", ".md")):
                    extracted_resume_text = file.read().decode('utf-8', errors='ignore')
                elif filename.endswith(".docx"):
                    try:
                        import docx
                        doc = docx.Document(file)
                        extracted_resume_text = "\n".join([p.text for p in doc.paragraphs if p.text])
                    except Exception:
                        file.seek(0)
                        extracted_resume_text = file.read().decode('utf-8', errors='ignore')
                else:
                    extracted_resume_text = file.read().decode('utf-8', errors='ignore')
                
                # Index into Pinecone Vector DB
                if extracted_resume_text:
                    try:
                        pinecone_utils.index_document_text(f"resume_{current_user.id}", filename, extracted_resume_text)
                    except Exception as p_err:
                        print(f"[Pinecone Resume Index Error]: {p_err}")
            except Exception as parse_err:
                print(f"[Resume File Parse Error]: {parse_err}")

        # 2. If no fresh file uploaded, retrieve saved resume from MongoDB
        if not extracted_resume_text and not image_obj:
            if MONGODB_AVAILABLE and resume_reviews_collection is not None:
                user_review = resume_reviews_collection.find_one({"user_id": str(current_user.id)})
                if user_review:
                    extracted_resume_text = user_review.get("report", "")

        # 3. Strictly require a resume before running the assessment!
        if not extracted_resume_text and not image_obj:
            return jsonify({
                "error": "No resume found. Please upload your resume file (PDF, DOCX, TXT, Image) first to start the Virtual Assessment!"
            }), 400

        prompt = f"""
You are a Senior Tech Recruiter and AI Virtual Placement Officer.
Carefully analyze the candidate's resume content below:

Resume Content:
{extracted_resume_text[:3500] if extracted_resume_text else "[Resume provided as attached image]"}

Target Role: "{target_role}"
Work Mode Preference: {work_mode.upper()}
Preferred Location: {preferred_locations}

INSTRUCTIONS:
1. Experience Level Detection:
   - Carefully count total full-time professional experience.
   - If total full-time experience is < 2 years (or student / intern / recent graduate), classify as "fresher".
   - If total full-time experience is >= 2 years, classify as "experienced".

2. Profile Score Evaluation:
   - Calculate candidate readiness score (0 to 100) for "{target_role}".

Return ONLY a valid JSON object strictly with these fields:
{{
  "score": 85,
  "experience_level": "fresher",
  "experience_label": "Fresher / Entry Level (0-2 Years)",
  "verdict": "string summary verdict",
  "feedback": "string detailed actionable feedback explaining key strengths or missing skills to improve"
}}
"""
        score = 80
        threshold_passed = True
        experience_level = "fresher"
        experience_label = "Fresher / Entry Level (0-2 Years)"
        verdict = "Strong alignment for the target role."
        feedback = "Candidate shows solid foundational skills."

        try:
            content_parts = [prompt, image_obj] if image_obj else prompt
            res, err = generate_content_with_fallback(content_parts, preferred_model="gemini-2.5-flash", temperature=0.3)
            if res:
                txt = _get_gemini_text(res)
                clean_txt = clean_json_text(txt) if 'clean_json_text' in globals() else txt.replace("```json", "").replace("```", "").strip()
                eval_data = json.loads(clean_txt)
                score = int(eval_data.get("score", 80))
                threshold_passed = score >= 60
                experience_level = str(eval_data.get("experience_level", "fresher")).strip().lower()
                experience_label = str(eval_data.get("experience_label", "Fresher / Entry Level" if experience_level == "fresher" else "Experienced Professional"))
                verdict = str(eval_data.get("verdict", verdict))
                feedback = str(eval_data.get("feedback", feedback))
        except Exception as eval_err:
            print(f"[Virtual Assessment Gemini Eval Error]: {eval_err}")

        # Check threshold requirement
        if score < 60:
            return jsonify({
                "score": score,
                "threshold_passed": False,
                "experience_level": experience_level,
                "experience_label": experience_label,
                "verdict": verdict,
                "message": f"⚠️ Profile Match Score: {score}%. Your profile does not meet the minimum 60% threshold for '{target_role}' positions in {preferred_locations} yet.",
                "feedback": feedback,
                "recommendation": "Improve your core technical skills, complete missing projects, and try the assessment again to unlock live job recommendations!",
                "jobs": []
            })

        # Threshold passed (>= 60%) -> Scrape/Fetch 21 fresh live LinkedIn job postings matching candidate experience level
        jobs = apify_utils.fetch_linkedin_jobs(
            role=target_role,
            location=preferred_locations,
            experience_level=experience_level,
            relocate=relocate,
            work_mode=work_mode,
            max_results=21,
            db=db if MONGODB_AVAILABLE else None
        )

        resp_payload = {
            "score": score,
            "threshold_passed": True,
            "experience_level": experience_level,
            "experience_label": experience_label,
            "verdict": verdict,
            "message": f"🎉 Profile Match Score: {score}%! [{experience_label}] You passed the Virtual Assessment threshold for '{target_role}'. Here are 21 fresh LinkedIn job postings filtered for your experience level ({experience_label}):",
            "feedback": feedback,
            "jobs": jobs
        }

        # Store persistent assessment and matched jobs in MongoDB
        if MONGODB_AVAILABLE and virtual_placement_results_collection is not None:
            try:
                virtual_placement_results_collection.update_one(
                    {"user_id": str(current_user.id)},
                    {
                        "$set": {
                            "user_id": str(current_user.id),
                            "target_role": target_role,
                            "work_mode": work_mode,
                            "preferred_locations": preferred_locations,
                            "relocate": relocate,
                            "score": score,
                            "threshold_passed": True,
                            "experience_level": experience_level,
                            "experience_label": experience_label,
                            "verdict": verdict,
                            "feedback": feedback,
                            "message": resp_payload["message"],
                            "jobs": jobs,
                            "updated_at": datetime.now(timezone.utc)
                        }
                    },
                    upsert=True
                )
            except Exception as db_err:
                print(f"[MongoDB Virtual Placement Save Error]: {db_err}")

        return jsonify(resp_payload)

    except Exception as e:
        print(f"Error in virtual career assessment: {e}")
        return jsonify({"error": f"Assessment server error: {str(e)}"}), 500

@app.route("/api/latest-virtual-placement", methods=["GET"])
@login_required
def get_latest_virtual_placement():
    """Retrieve saved virtual placement assessment results and matched jobs for current user."""
    if not MONGODB_AVAILABLE or virtual_placement_results_collection is None:
        return jsonify({"result": None})
    try:
        doc = virtual_placement_results_collection.find_one({"user_id": str(current_user.id)})
        if not doc:
            return jsonify({"result": None})
            
        return jsonify({
            "result": {
                "target_role": doc.get("target_role"),
                "work_mode": doc.get("work_mode"),
                "preferred_locations": doc.get("preferred_locations"),
                "score": doc.get("score"),
                "threshold_passed": doc.get("threshold_passed"),
                "experience_level": doc.get("experience_level"),
                "experience_label": doc.get("experience_label"),
                "verdict": doc.get("verdict"),
                "feedback": doc.get("feedback"),
                "message": doc.get("message"),
                "jobs": doc.get("jobs", []),
                "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/aptitude")
@login_required
def aptitude_quiz():
    """Aptitude quiz page."""
    return render_template("aptitude.html")

@app.route("/customquiz")
@login_required
def custom_quiz_builder():
    """Custom quiz builder page (manual or AI-assisted)."""
    return render_template("customquiz.html")

@app.route("/customexam")
@login_required
def custom_quiz_exam():
    """Custom quiz exam page for students (enter code and attempt in fullscreen)."""
    return render_template("custom_exam.html")



@app.route("/api/user-chats/<chat_id>", methods=["DELETE"])
@login_required
def delete_user_chat(chat_id):
    """Delete a single chat conversation for the current user."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        try:
            chat_obj_id = ObjectId(chat_id)
        except Exception:
            return jsonify({"error": "Invalid chat id"}), 400

        # Support both ObjectId and string user_id formats
        try:
            user_id_obj = ObjectId(current_user.id)
        except Exception:
            user_id_obj = current_user.id

        result = chat_conversations_collection.delete_one({
            "_id": chat_obj_id,
            "user_id": {"$in": [user_id_obj, current_user.id]}
        })

        if result.deleted_count == 0:
            return jsonify({"error": "Chat not found"}), 404

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user-quizzes", methods=["GET"])
@login_required
def get_user_quizzes():
    """Get user's generated quiz history."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    
    try:
        limit = int(request.args.get("limit", 50))
        # Try both ObjectId and string format for user_id
        try:
            user_id_obj = ObjectId(current_user.id)
            history = list(user_quiz_history_collection.find(
                {"user_id": user_id_obj}
            ).sort("generated_at", -1).limit(limit))
        except:
            # Fallback to string if ObjectId conversion fails
            history = list(user_quiz_history_collection.find(
                {"user_id": current_user.id}
            ).sort("generated_at", -1).limit(limit))
        
        # Convert ObjectId to string and format dates
        for item in history:
            item["_id"] = str(item["_id"])
            if "quiz_id" in item:
                item["quiz_id"] = str(item["quiz_id"])
            if "user_id" in item:
                item["user_id"] = str(item["user_id"])
            if isinstance(item.get("generated_at"), datetime):
                item["generated_at"] = item["generated_at"].isoformat()
            
            # Get score if available
            try:
                user_id_obj = ObjectId(current_user.id)
                score_data = quiz_scores_collection.find_one({
                    "user_id": user_id_obj,
                    "video_id": item["video_id"],
                    "num_questions": item["num_questions"],
                    "difficulty": item["difficulty"]
                })
            except:
                score_data = quiz_scores_collection.find_one({
                    "user_id": current_user.id,
                    "video_id": item["video_id"],
                    "num_questions": item["num_questions"],
                    "difficulty": item["difficulty"]
                })
            if score_data:
                item["score"] = score_data.get("score")
                item["total_questions"] = score_data.get("total_questions")
                item["percentage"] = score_data.get("percentage")
                item["completed_at"] = score_data.get("completed_at").isoformat() if isinstance(score_data.get("completed_at"), datetime) else None
            else:
                item["score"] = None
                item["completed"] = False
        
        print(f"Found {len(history)} quizzes for user {current_user.id}")
        return jsonify({"quizzes": history})
    except Exception as e:
        print(f"Error getting user quizzes: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/user-custom-attempts", methods=["GET"])
@login_required
def get_user_custom_attempts():
    """Get custom quiz exam attempts made by the current user."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        try:
            user_id = ObjectId(current_user.id)
        except Exception:
            user_id = current_user.id

        attempts = list(custom_quiz_attempts_collection.find(
            {"user_id": user_id}
        ).sort("submitted_at", -1))

        payload = []
        for att in attempts:
            # Lookup quiz for title if needed
            quiz_code = att.get("quiz_code")
            quiz_title = None
            if quiz_code:
                quiz = custom_quizzes_collection.find_one({"code": quiz_code})
                if quiz:
                    quiz_title = quiz.get("title")

            submitted_at = att.get("submitted_at")
            if isinstance(submitted_at, datetime):
                submitted_at = submitted_at.isoformat()

            payload.append({
                "quiz_code": quiz_code,
                "title": quiz_title,
                "score": att.get("score"),
                "total_questions": att.get("total_questions"),
                "percentage": att.get("percentage"),
                "submitted_at": submitted_at
            })

        return jsonify({"attempts": payload})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/custom-quizzes", methods=["POST"])
@login_required
def create_custom_quiz():
    """Create a shareable custom quiz from existing quiz data or manually defined questions."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500

    data = request.get_json()
    quiz_data = data.get("quiz_data")
    title = data.get("title") or "Custom Quiz"
    video_url = data.get("video_url")
    num_questions = data.get("num_questions")
    difficulty = data.get("difficulty")

    if not quiz_data or not quiz_data.get("questions"):
        return jsonify({"error": "No quiz data provided"}), 400

    code = generate_quiz_code()
    try:
        owner_id = ObjectId(current_user.id)
    except Exception:
        owner_id = current_user.id

    doc = {
        "code": code,
        "owner_id": owner_id,
        "owner_username": current_user.username,
        "title": title,
        "video_url": video_url,
        "num_questions": num_questions or len(quiz_data.get("questions", [])),
        "difficulty": difficulty or "custom",
        "quiz_data": quiz_data,
        "created_at": datetime.now(timezone.utc),
        "active": True,
        "source": "custom"  # manual or AI topic based
    }
    custom_quizzes_collection.insert_one(doc)
    return jsonify({"code": code})

@app.route("/api/customquiz/generate", methods=["POST"])
@login_required
def ai_generate_custom_quiz():
    """Use Gemini to generate quiz questions for a given topic and count."""
    data = request.get_json()
    topic = data.get("topic", "").strip()
    num_questions = data.get("num_questions", 5)
    difficulty = data.get("difficulty", "medium")

    if not topic:
        return jsonify({"error": "Please provide a topic for the quiz."}), 400

    try:
        num_questions = int(num_questions)
        if num_questions < 3 or num_questions > 20:
            return jsonify({"error": "Number of questions must be between 3 and 20."}), 400
    except (ValueError, TypeError):
        num_questions = 5

    difficulty_descriptions = {
        "easy": "Easy: Simple questions focusing on basic facts and definitions.",
        "medium": "Medium: Mix of factual and conceptual questions requiring understanding.",
        "hard": "Hard: Challenging questions requiring deep understanding and application."
    }
    difficulty_instruction = difficulty_descriptions.get(difficulty, difficulty_descriptions["medium"])

    prompt = (
        f"Create a multiple-choice quiz on the topic: '{topic}'. "
        f"Generate exactly {num_questions} questions.\n\n"
        f"Difficulty Level: {difficulty_instruction}\n\n"
        "Return ONLY valid JSON (no markdown, no prose, just JSON) in this exact format:\n"
        "{\n"
        '  "questions": [\n'
        "    {\n"
        '      "question": "Question text",\n'
        '      "options": ["Option A", "Option B", "Option C", "Option D"],\n'
        '      "correct": 0,\n'
        '      "explanation": "Short explanation of the correct answer"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        f"- Create exactly {num_questions} questions.\n"
        "- Each question MUST have 4 options.\n"
        "- 'correct' must be the index (0-3) of the correct option.\n"
        "- Questions must be directly relevant to the topic.\n"
        "- Use clear, simple language.\n"
    )

    try:
        quiz_model = get_gemini_model(temperature=0.2) or model
        response = quiz_model.generate_content(prompt)
        response_text = _get_gemini_text(response)
        if not response_text:
            raise json.JSONDecodeError("empty AI response", "", 0)

        response_text = clean_json_text(response_text)

        quiz_data = json.loads(response_text)
        if "questions" not in quiz_data or not quiz_data["questions"]:
            return jsonify({"error": "AI did not return any questions."}), 500

        # Trim to num_questions if extra
        quiz_data["questions"] = quiz_data["questions"][:num_questions]
        return jsonify({"quiz_data": quiz_data})
    except json.JSONDecodeError as e:
        return jsonify({
            "error": f"Failed to parse AI-generated quiz JSON: {str(e)}",
        }), 500
    except Exception as e:
        error_text = str(e)
        # If quota or similar error, surface a friendly message
        if "quota" in error_text.lower() or "429" in error_text:
            return jsonify({
                "error": "AI generation is temporarily unavailable due to rate limits. Please try again later."
            }), 503
        return jsonify({"error": str(e)}), 500

@app.route("/api/custom-quizzes/<code>", methods=["GET"])
@login_required
def fetch_custom_quiz(code):
    """Retrieve a custom quiz by code for attempting."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500

    quiz = custom_quizzes_collection.find_one({"code": code.upper()})
    if not quiz:
        return jsonify({"error": "Quiz code not found"}), 404

    # Only owner can access inactive quizzes
    if not quiz.get("active", True):
        try:
            owner_id = ObjectId(current_user.id)
        except Exception:
            owner_id = current_user.id
        if quiz["owner_id"] != owner_id and str(quiz["owner_id"]) != str(owner_id):
            return jsonify({"error": "This quiz is no longer accepting attempts."}), 403

    # Check if user has already attempted this quiz
    try:
        user_id = ObjectId(current_user.id)
    except Exception:
        user_id = current_user.id

    existing_attempt = custom_quiz_attempts_collection.find_one({
        "quiz_code": quiz["code"],
        "user_id": user_id
    })
    
    if existing_attempt:
        return jsonify({"error": "You have already attempted this quiz. Please ask the creator to reset your attempt if you wish to try again."}), 403

    # Return quiz data; include full questions so UI can highlight correct answers
    response = {
        "code": quiz["code"],
        "title": quiz.get("title"),
        "video_url": quiz.get("video_url"),
        "num_questions": quiz.get("num_questions"),
        "difficulty": quiz.get("difficulty"),
        "quiz_data": quiz.get("quiz_data", {}),
        "active": quiz.get("active", True)
    }
    return jsonify(response)

@app.route("/api/custom-quizzes/<code>/submit", methods=["POST"])
@login_required
def submit_custom_quiz(code):
    """Submit answers for a custom quiz attempt."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500

    quiz = custom_quizzes_collection.find_one({"code": code.upper()})
    if not quiz:
        return jsonify({"error": "Quiz code not found"}), 404

    # Check if quiz is active
    # Check if quiz is active (allow owner to submit for testing)
    if not quiz.get("active", True):
        try:
            owner_id = ObjectId(current_user.id)
        except Exception:
            owner_id = current_user.id
        
        if quiz["owner_id"] != owner_id and str(quiz["owner_id"]) != str(owner_id):
            return jsonify({"error": "This quiz is not currently accepting attempts."}), 403

    data = request.get_json()
    user_answers = data.get("user_answers", {})

    questions = quiz.get("quiz_data", {}).get("questions", [])
    total_questions = len(questions)
    score = 0
    correct_answers = {}
    for idx, question in enumerate(questions):
        correct_index = question.get("correct", 0)
        correct_answers[str(idx)] = correct_index
        chosen = user_answers.get(str(idx))
        if chosen is not None and int(chosen) == int(correct_index):
            score += 1

    try:
        user_id = ObjectId(current_user.id)
    except Exception:
        user_id = current_user.id

    # Enforce single attempt per user per quiz
    existing_attempt = custom_quiz_attempts_collection.find_one({
        "quiz_code": quiz["code"],
        "user_id": user_id
    })
    if existing_attempt:
        return jsonify({"error": "You have already attempted this quiz. Only one attempt is allowed."}), 403

    attempt = {
        "quiz_code": quiz["code"],
        "quiz_id": quiz["_id"],
        "owner_id": quiz["owner_id"],
        "owner_username": quiz.get("owner_username"),
        "user_id": user_id,
        "username": current_user.username,
        "score": score,
        "total_questions": total_questions,
        "percentage": round((score / total_questions) * 100, 2) if total_questions else 0,
        "user_answers": user_answers,
        "correct_answers": correct_answers,
        "submitted_at": datetime.now(timezone.utc)
    }
    custom_quiz_attempts_collection.insert_one(attempt)

    return jsonify({
        "score": score,
        "total_questions": total_questions,
        "percentage": attempt["percentage"]
    })

@app.route("/api/custom-quizzes/<code>/attempts", methods=["GET"])
@login_required
def get_custom_quiz_attempts(code):
    """Get attempts for a custom quiz (owner only)."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500

    quiz = custom_quizzes_collection.find_one({"code": code.upper()})
    if not quiz:
        return jsonify({"error": "Quiz code not found"}), 404

    try:
        owner_id = ObjectId(current_user.id)
    except Exception:
        owner_id = current_user.id

    if quiz["owner_id"] != owner_id:
        # Compare stringified ObjectIds
        if str(quiz["owner_id"]) != str(owner_id):
            return jsonify({"error": "Not authorized to view attempts"}), 403

    attempts = list(custom_quiz_attempts_collection.find({"quiz_code": quiz["code"]}).sort("submitted_at", -1))
    for attempt in attempts:
        attempt["_id"] = str(attempt["_id"])
        if isinstance(attempt.get("submitted_at"), datetime):
            attempt["submitted_at"] = attempt["submitted_at"].isoformat()
        if "user_id" in attempt:
            attempt["user_id"] = str(attempt["user_id"])
    return jsonify({"attempts": attempts})

@app.route("/api/my-custom-quizzes", methods=["GET"])
@login_required
def get_my_custom_quizzes():
    """List custom quizzes created by the current user with summary stats."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        owner_id = ObjectId(current_user.id)
    except Exception:
        owner_id = current_user.id

    quizzes = list(custom_quizzes_collection.find({"owner_id": owner_id}).sort("created_at", -1))
    for quiz in quizzes:
        quiz["_id"] = str(quiz["_id"])
        quiz["owner_id"] = str(quiz["owner_id"])
        if isinstance(quiz.get("created_at"), datetime):
            quiz["created_at"] = quiz["created_at"].isoformat()
        quiz["active"] = quiz.get("active", True)

        attempts = list(custom_quiz_attempts_collection.find({"quiz_code": quiz["code"]}).sort("submitted_at", -1))
        quiz["attempts_count"] = len(attempts)
        quiz_attempts_payload = []
        for attempt in attempts[:25]:
            quiz_attempts_payload.append({
                "attempt_id": str(attempt.get("_id")),
                "username": attempt.get("username"),
                "score": attempt.get("score"),
                "total_questions": attempt.get("total_questions"),
                "percentage": attempt.get("percentage"),
                "submitted_at": attempt.get("submitted_at").isoformat() if isinstance(attempt.get("submitted_at"), datetime) else attempt.get("submitted_at")
            })
        quiz["attempts"] = quiz_attempts_payload

    return jsonify({"quizzes": quizzes})

@app.route("/api/custom-quizzes/<code>/attempts/<attempt_id>", methods=["DELETE"])
@login_required
def delete_custom_quiz_attempt(code, attempt_id):
    """Allow quiz owner to delete a student's attempt so they can re-attempt."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500

    quiz = custom_quizzes_collection.find_one({"code": code.upper()})
    if not quiz:
        return jsonify({"error": "Quiz code not found"}), 404

    # Only the owner of the quiz can delete attempts
    try:
        owner_id = ObjectId(current_user.id)
    except Exception:
        owner_id = current_user.id

    if quiz["owner_id"] != owner_id and str(quiz["owner_id"]) != str(owner_id):
        return jsonify({"error": "Not authorized to modify attempts for this quiz"}), 403

    # Validate attempt_id and delete the attempt
    try:
        attempt_obj_id = ObjectId(attempt_id)
    except Exception:
        return jsonify({"error": "Invalid attempt id"}), 400

    result = custom_quiz_attempts_collection.delete_one({
        "_id": attempt_obj_id,
        "quiz_code": quiz["code"]
    })

    if result.deleted_count == 0:
        return jsonify({"error": "Attempt not found"}), 404

    return jsonify({"success": True})


def _api_videoquiz_logic():
    data = request.get_json()
    yt_url = data.get("yt_url", "").strip()
    num_questions = data.get("num_questions", 5)
    difficulty = data.get("difficulty", "medium")
    
    if not yt_url.startswith("https://www.youtube.com/watch?v=") and not yt_url.startswith("https://youtu.be/"):
        return jsonify({"error": "Please paste a full, valid YouTube video link."}), 400

    # Validate num_questions
    try:
        num_questions = int(num_questions)
        if num_questions < 3 or num_questions > 20:
            return jsonify({"error": "Number of questions must be between 3 and 20."}), 400
    except (ValueError, TypeError):
        num_questions = 5
    
    # Validate difficulty
    if difficulty not in ["easy", "medium", "hard"]:
        difficulty = "medium"

    video_id = get_video_id(yt_url)
    if not video_id:
        return jsonify({"error": "Could not extract video ID from the URL."}), 400

    # Try to get transcript first
    transcript = None
    content_source = "transcript"
    
    print(f"Attempting to fetch transcript for video_id: {video_id}")
    try:
        # Try standard static method first
        if hasattr(YouTubeTranscriptApi, 'get_transcript'):
            fetched_transcript = YouTubeTranscriptApi.get_transcript(video_id)
        else:
            # Fallback for non-standard/older versions that require instantiation
            print("YouTubeTranscriptApi.get_transcript not found. Trying instantiation...")
            yt = YouTubeTranscriptApi()
            if hasattr(yt, 'fetch'):
                fetched_transcript = yt.fetch(video_id)
            elif hasattr(yt, 'list'):
                # If list returns a TranscriptList, we might need to iterate. 
                # But based on tests, let's try to use it if fetch is missing.
                # However, fetch is more likely to be the direct equivalent.
                fetched_transcript = yt.list(video_id)
            else:
                raise ImportError("YouTubeTranscriptApi has no get_transcript, fetch, or list methods.")

        # Extract text from snippets (returns list of dicts with 'text' key)
        # Check if it's a list of dicts or something else
        if isinstance(fetched_transcript, list):
             transcript = "\n".join([item['text'] for item in fetched_transcript if 'text' in item])
        else:
             # If it's not a list of dicts, maybe it's already text or a different object?
             # Let's assume it behaves like the standard one if it returned a list
             print(f"Unexpected transcript format: {type(fetched_transcript)}")
             transcript = str(fetched_transcript)

        if transcript and transcript.strip():
            content_source = "transcript"
            print("Transcript fetched successfully.")
    except ImportError as e:
        print(f"ImportError: {str(e)}")
        # Fallthrough to metadata fallback
    except Exception as e:
        error_msg = str(e)
        print(f"Transcript fetch failed: {error_msg}")
        # Fallthrough to metadata fallback
        if "No transcripts were found" in error_msg or "TranscriptsDisabled" in error_msg or "Could not retrieve a transcript" in error_msg:
            # Fallback to video metadata
            print("Falling back to video metadata...")
            metadata, error_log = get_video_metadata(video_id, yt_url)
            if metadata and metadata.get("description"):
                # Use description and title as content
                transcript = f"Video Title: {metadata.get('title', '')}\n\nVideo Description:\n{metadata.get('description', '')}"
                content_source = "metadata"
                print("Metadata fallback successful.")
            else:
                print("Metadata fallback failed.")
                if not YT_DLP_AVAILABLE and not PYTUBE_AVAILABLE:
                    return jsonify({
                        "error": "No transcript/captions found for this video. To use videos without subtitles, please install yt-dlp or pytube."
                    }), 404
                
                # Format error log for display
                error_details = "<br>".join(error_log) if error_log else "Unknown error"
                return jsonify({
                    "error": f"No transcript/captions found, and unable to retrieve video metadata.<br>Debug details:<br>{error_details}"
                }), 404
        else:
            # Other errors - try metadata fallback
            metadata, error_log = get_video_metadata(video_id, yt_url)
            if metadata and (metadata.get("description") or metadata.get("title")):
                title = metadata.get('title', 'Video')
                description = metadata.get('description', '')
                transcript = f"Video Title: {title}\n\nVideo Description:\n{description}" if description else f"Video Title: {title}"
                content_source = "metadata"
            else:
                # Try one more time with a different approach
                metadata = get_video_metadata(video_id, yt_url)
                if metadata and (metadata.get("description") or metadata.get("title")):
                    title = metadata.get('title', 'Video')
                    description = metadata.get('description', '')
                    transcript = f"Video Title: {title}\n\nVideo Description:\n{description}" if description else f"Video Title: {title}"
                    content_source = "metadata"
                else:
                    return jsonify({
                        "error": f"Error processing video: {error_msg}<br>Unable to retrieve transcript or video metadata. Please ensure the video is public, not age-restricted, and accessible. You can try a different video or check if the video has captions enabled."
                    }), 500
    # Final check - if we still don't have content
    if not transcript or transcript.strip() == "":
        print("Transcript still empty, trying metadata again...")
        metadata, error_log = get_video_metadata(video_id, yt_url)
        if metadata and (metadata.get("description") or metadata.get("title")):
            title = metadata.get('title', 'Video')
            description = metadata.get('description', '')
            transcript = f"Video Title: {title}\n\nVideo Description:\n{description}" if description else f"Video Title: {title}"
            content_source = "metadata"
        else:
            return jsonify({
                "error": "Unable to retrieve video content. The video may be private, age-restricted, or have no available information. Please try a different video or ensure the video is public and accessible."
            }), 404

    # Check if the video is educational
    print("Checking if content is educational...")
    is_educational, reason = is_educational_content(transcript)
    if not is_educational:
        print(f"Video rejected: {reason}")
        return jsonify({
            "error": f"This video does not appear to be educational content. {reason}<br><br>Please use educational videos such as tutorials, courses, lectures, how-to guides, documentaries, or academic content."
        }), 400

    # Check if quiz already exists in MongoDB (caching)
    if MONGODB_AVAILABLE:
        cached_quiz = quizzes_collection.find_one({
            "video_id": video_id,
            "num_questions": num_questions,
            "difficulty": difficulty
        })
        if cached_quiz:
            # Return cached quiz
            quiz_data = {
                "questions": cached_quiz.get("questions", []),
                "notes": cached_quiz.get("notes", "")
            }
            return jsonify({"response": quiz_data, "cached": True})

    # Difficulty level descriptions
    difficulty_descriptions = {
        "easy": "Easy: Create simple, straightforward questions that test basic understanding and recall of key facts from the video. Use simple language and focus on main concepts.",
        "medium": "Medium: Create moderately challenging questions that require understanding of concepts, relationships, and some analysis. Mix factual recall with conceptual understanding.",
        "hard": "Hard: Create challenging questions that require deep understanding, critical thinking, analysis, and application of concepts. Include questions that test synthesis and evaluation skills."
    }
    
    difficulty_instruction = difficulty_descriptions.get(difficulty, difficulty_descriptions["medium"])
    
    # Adjust prompt based on content source
    content_description = "transcript/subtitles" if content_source == "transcript" else "video title and description"
    
    quiz_prompt = (
        f"The following is content from an educational YouTube video ({content_description}). Create a quiz with exactly {num_questions} multiple choice questions."
        f"\n\nDifficulty Level: {difficulty_instruction}"
        "\n\nIMPORTANT: Return ONLY valid JSON in this exact format (no markdown, no code blocks, just pure JSON):"
        "\n{"
        '\n  "questions": ['
        '\n    {'
        '\n      "question": "Question text here",'
        '\n      "options": ["Option A", "Option B", "Option C", "Option D"],'
        '\n      "correct": 0,'
        '\n      "explanation": "Explanation of why this answer is correct"'
        '\n    }'
        '\n  ],'
        '\n  "notes": "Study notes content (can include HTML formatting for clarity)"'
        '\n}'
        "\n\nRequirements for Questions:"
        f"\n- Create exactly {num_questions} multiple choice questions (no more, no less)"
        "\n- Each question must have exactly 4 options (A, B, C, D)"
        "\n- 'correct' is the index (0-3) of the correct option in the options array"
        "\n- Provide clear, detailed explanations for each correct answer"
        "\n- Base questions on the actual content provided below"
        "\n- Match the difficulty level specified above"
        "\n\nRequirements for Study Notes (VERY IMPORTANT - Make them EXTREMELY CLEAR):"
        "\n- The 'notes' field should contain well-organized, clear study notes"
        "\n- Use HTML formatting for better structure: <b>bold</b>, <ul><li>bullet points</li></ul>, <h3>headings</h3>, <br> for line breaks"
        "\n- Organize notes into clear sections with headings"
        "\n- Use bullet points or numbered lists for key concepts"
        "\n- Highlight important terms and definitions"
        "\n- Make it easy to scan and understand quickly"
        "\n- Include all major topics covered in the video"
        "\n- Use clear, concise language"
        "\n- Structure: Main Topic → Key Points → Important Details"
        "\n- Example structure: '<h3>Topic Name</h3><ul><li><b>Key Point:</b> Explanation</li></ul>'"
        "\n- Return ONLY the JSON object, nothing else"
        f"\n\n--- Video Content Start ---\n{transcript[:15000]}\n--- Video Content End ---"
    )
    try:
        print("Sending prompt to Gemini...")
        quiz_model = get_gemini_model(temperature=0.2) or model
        response = quiz_model.generate_content(quiz_prompt)
        print("Gemini response received.")
        response_text = _get_gemini_text(response)
        if not response_text:
            raise json.JSONDecodeError("empty AI response", "", 0)

        response_text = clean_json_text(response_text)
        
        # Parse JSON to validate it
        try:
            quiz_data = json.loads(response_text)
        except json.JSONDecodeError:
            # Iterative repair for "Invalid \escape" errors
            print("Initial JSON parse failed. Attempting iterative repair...")
            current_text = response_text
            repaired = False
            for attempt in range(5): # Try up to 5 repairs
                try:
                    quiz_data = json.loads(current_text)
                    repaired = True
                    print(f"JSON repaired successfully on attempt {attempt+1}")
                    break
                except json.JSONDecodeError as e:
                    if "Invalid \\escape" in str(e):
                        # e.pos points to the invalid char (e.g. 'z' in '\z')
                        # We need to escape the backslash before it (at e.pos-1)
                        # Check if e.pos-1 is indeed a backslash
                        if e.pos > 0 and current_text[e.pos-1] == '\\':
                            print(f"Repairing invalid escape at pos {e.pos-1}")
                            # Replace \ with \\
                            current_text = current_text[:e.pos-1] + "\\\\" + current_text[e.pos:]
                        else:
                            print(f"Cannot repair: char at {e.pos-1} is not backslash. Char is '{current_text[e.pos-1]}'")
                            break
                    else:
                        print(f"Cannot repair: Error is not invalid escape. {str(e)}")
                        break
            
            if not repaired:
                # One last try: just load it to raise the error for the outer block
                quiz_data = json.loads(current_text)
        
        # Store quiz in MongoDB for caching
        if MONGODB_AVAILABLE:
            try:
                quiz_doc = {
                    "video_id": video_id,
                    "video_url": yt_url,
                    "num_questions": num_questions,
                    "difficulty": difficulty,
                    "questions": quiz_data.get("questions", []),
                    "notes": quiz_data.get("notes", ""),
                    "created_at": datetime.now(timezone.utc),
                    "created_by": current_user.id
                }
                result = quizzes_collection.insert_one(quiz_doc)
                quiz_id = result.inserted_id
                
                # Also store in user quiz history
                # Store user_id as ObjectId for consistency
                try:
                    user_id_obj = ObjectId(current_user.id)
                except:
                    user_id_obj = current_user.id
                
                history_doc = {
                    "user_id": user_id_obj,
                    "username": current_user.username,
                    "quiz_id": quiz_id,
                    "video_id": video_id,
                    "video_url": yt_url,
                    "num_questions": num_questions,
                    "difficulty": difficulty,
                    "generated_at": datetime.now(timezone.utc)
                }
                result = user_quiz_history_collection.insert_one(history_doc)
                print(f"Stored quiz history for user {current_user.id}, inserted_id: {result.inserted_id}")
            except Exception as e:
                print(f"Error storing quiz in MongoDB: {str(e)}")
        
        return jsonify({"response": quiz_data, "cached": False})
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {str(e)}")
        print(f"Raw Response Text: {response_text if 'response_text' in locals() else 'None'}")
        # If JSON parsing fails, return error with the raw response for debugging
        return jsonify({
            "error": f"Failed to parse quiz JSON. The AI response was not in valid JSON format. Error: {str(e)}",
            "raw_response": response_text[:500] if 'response_text' in locals() else "No response"
        }), 500
    except Exception as e:
        print(f"General Error in _api_videoquiz_logic: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/videoquiz", methods=["POST"])
@login_required
def api_videoquiz():
    """Wrapper for video quiz generation to ensure JSON response on crash."""
    try:
        print("Starting video quiz generation...")
        return _api_videoquiz_logic()
    except Exception as e:
        print(f"CRITICAL ERROR in api_videoquiz: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": f"Unexpected server error: {str(e)}",
            "details": "The server encountered a crash while processing the video."
        }), 500

def generate_quiz_pdf(quiz_data, video_title=None):
    """Generate a PDF with questions first, then answers and explanations at the end."""
    if not REPORTLAB_AVAILABLE:
        raise Exception("reportlab is not installed. Please install it with: pip install reportlab")
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.75*inch, bottomMargin=0.75*inch)
    
    # Container for the 'Flowable' objects
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#19977e'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#19977e'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    question_style = ParagraphStyle(
        'QuestionStyle',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=8,
        spaceBefore=8,
        leftIndent=0,
        textColor=colors.black
    )
    
    option_style = ParagraphStyle(
        'OptionStyle',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=4,
        leftIndent=20,
        textColor=colors.black
    )
    
    answer_style = ParagraphStyle(
        'AnswerStyle',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        leftIndent=0,
        textColor=colors.black
    )
    
    # Title
    title_text = video_title if video_title else "Quiz Questions"
    elements.append(Paragraph(title_text, title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Questions Section
    elements.append(Paragraph("QUESTIONS", heading_style))
    elements.append(Spacer(1, 0.1*inch))
    
    questions = quiz_data.get('questions', [])
    for i, q in enumerate(questions, 1):
        # Question text
        question_text = f"<b>Question {i}:</b> {q.get('question', '')}"
        elements.append(Paragraph(question_text, question_style))
        
        # Options
        options = q.get('options', [])
        for j, option in enumerate(options):
            option_letter = chr(65 + j)  # A, B, C, D
            option_text = f"{option_letter}. {option}"
            elements.append(Paragraph(option_text, option_style))
        
        elements.append(Spacer(1, 0.15*inch))
    
    # Page break before answers
    elements.append(PageBreak())
    
    # Answers and Explanations Section
    elements.append(Paragraph("ANSWERS AND EXPLANATIONS", heading_style))
    elements.append(Spacer(1, 0.1*inch))
    
    for i, q in enumerate(questions, 1):
        correct_index = q.get('correct', 0)
        correct_option = chr(65 + correct_index)
        correct_answer = q.get('options', [])[correct_index] if correct_index < len(q.get('options', [])) else ""
        explanation = q.get('explanation', '')
        
        # Answer
        answer_text = f"<b>Question {i}:</b> {q.get('question', '')}"
        elements.append(Paragraph(answer_text, question_style))
        
        answer_option_text = f"<b>Correct Answer: {correct_option}. {correct_answer}</b>"
        elements.append(Paragraph(answer_option_text, answer_style))
        
        # Explanation
        if explanation:
            explanation_text = f"<b>Explanation:</b> {explanation}"
            elements.append(Paragraph(explanation_text, answer_style))
        
        elements.append(Spacer(1, 0.15*inch))
    
    # Study Notes (if available)
    notes = quiz_data.get('notes', '')
    if notes:
        elements.append(PageBreak())
        elements.append(Paragraph("STUDY NOTES", heading_style))
        elements.append(Spacer(1, 0.1*inch))
        
        # Convert HTML to plain text for PDF
        import re
        from html import unescape
        
        # Remove HTML tags but preserve structure
        notes_clean = re.sub(r'<br\s*/?>', '\n', notes, flags=re.IGNORECASE)  # Convert <br> to newlines
        notes_clean = re.sub(r'</(p|div|h[1-6])>', '\n', notes_clean, flags=re.IGNORECASE)  # Convert closing tags to newlines
        notes_clean = re.sub(r'<[^>]+>', '', notes_clean)  # Remove remaining HTML tags
        notes_clean = unescape(notes_clean)  # Decode HTML entities
        notes_clean = re.sub(r'\n{3,}', '\n\n', notes_clean)  # Remove excessive newlines
        
        # Split by lines and add as paragraphs
        for line in notes_clean.split('\n'):
            if line.strip():
                # Handle bullet points
                if line.strip().startswith('•') or line.strip().startswith('-') or line.strip().startswith('*'):
                    line = '  ' + line.strip()
                elements.append(Paragraph(line.strip(), answer_style))
                elements.append(Spacer(1, 0.05*inch))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

@app.route("/api/save-quiz-score", methods=["POST"])
@login_required
def save_quiz_score():
    """Save user's quiz score and answers to MongoDB."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    
    try:
        data = request.get_json()
        video_id = data.get("video_id")
        video_url = data.get("video_url")
        num_questions = data.get("num_questions")
        difficulty = data.get("difficulty")
        score = data.get("score")
        total_questions = data.get("total_questions")
        user_answers = data.get("user_answers", {})  # {question_index: selected_option_index}
        
        if not all([video_id, num_questions, difficulty, score is not None, total_questions]):
            return jsonify({"error": "Missing required fields"}), 400
        
        # Find the quiz to get question details
        quiz = quizzes_collection.find_one({
            "video_id": video_id,
            "num_questions": num_questions,
            "difficulty": difficulty
        })
        
        if not quiz:
            return jsonify({"error": "Quiz not found"}), 404
        
        # Calculate which questions were answered correctly
        questions = quiz.get("questions", [])
        correct_answers = {}
        for idx, q in enumerate(questions):
            correct_answers[str(idx)] = q.get("correct", 0)
        
        # Save score to database
        score_doc = {
            "user_id": ObjectId(current_user.id),
            "username": current_user.username,
            "video_id": video_id,
            "video_url": video_url,
            "num_questions": num_questions,
            "difficulty": difficulty,
            "score": score,
            "total_questions": total_questions,
            "percentage": round((score / total_questions) * 100, 2) if total_questions > 0 else 0,
            "user_answers": user_answers,
            "correct_answers": correct_answers,
            "completed_at": datetime.now(timezone.utc)
        }
        
        quiz_scores_collection.insert_one(score_doc)
        
        return jsonify({
            "success": True,
            "message": "Score saved successfully",
            "score": score,
            "total": total_questions,
            "percentage": score_doc["percentage"]
        })
    except Exception as e:
        return jsonify({"error": f"Error saving score: {str(e)}"}), 500

@app.route("/api/download-quiz-pdf", methods=["POST"])
@login_required
def download_quiz_pdf():
    """Generate and download quiz as PDF."""
    if not REPORTLAB_AVAILABLE:
        return jsonify({"error": "PDF generation is not available. Please install reportlab: pip install reportlab"}), 500
    
    try:
        data = request.get_json()
        quiz_data = data.get("quiz_data")
        video_title = data.get("video_title", "Quiz")
        
        if not quiz_data or not quiz_data.get('questions'):
            return jsonify({"error": "No quiz data provided"}), 400
        
        # Generate PDF
        pdf_buffer = generate_quiz_pdf(quiz_data, video_title)
        
        # Return PDF as response
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'quiz_{video_title.replace(" ", "_")[:50]}.pdf'
        )
    except Exception as e:
        return jsonify({"error": f"Error generating PDF: {str(e)}"}), 500

@app.route("/api/aptitude/questions", methods=["GET"])
@login_required
def get_aptitude_questions():
    """Get aptitude questions by difficulty level."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    
    try:
        difficulty = request.args.get("difficulty", "easy")
        num_questions = int(request.args.get("num_questions", 10))
        
        if difficulty not in ["easy", "medium"]:
            difficulty = "easy"
        
        if num_questions < 1 or num_questions > 50:
            num_questions = 10
        
        # Get random questions of specified difficulty
        questions = list(aptitude_questions_collection.aggregate([
            {"$match": {"difficulty": difficulty}},
            {"$sample": {"size": num_questions}}
        ]))
        
        if not questions:
            return jsonify({
                "error": f"No {difficulty} questions available. Please generate questions first.",
                "questions": []
            }), 404
        
        # Convert ObjectId to string
        for q in questions:
            q["_id"] = str(q["_id"])
        
        return jsonify({
            "questions": questions,
            "difficulty": difficulty,
            "count": len(questions)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/aptitude/attempts", methods=["GET"])
@login_required
def get_aptitude_attempts():
    """Get user's aptitude quiz attempts."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    
    try:
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
        
        attempts = list(aptitude_attempts_collection.find({
            "$or": [
                {"user_id": user_id_obj},
                {"user_id": current_user.id}
            ]
        }).sort("completed_at", -1).limit(50))
        
        for att in attempts:
            att["_id"] = str(att["_id"])
            if "user_id" in att:
                att["user_id"] = str(att["user_id"])
            if isinstance(att.get("completed_at"), datetime):
                att["completed_at"] = att["completed_at"].isoformat()
        
        return jsonify({"attempts": attempts})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/aptitude/stats", methods=["GET"])
@login_required
def get_aptitude_stats():
    """Get user's aptitude quiz statistics."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    
    try:
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
        
        # Get all practice attempts
        attempts = list(aptitude_practice_history_collection.find({
            "$or": [
                {"user_id": user_id_obj},
                {"user_id": current_user.id}
            ]
        }))
        
        # Calculate stats
        total_attempts = len(attempts) # Each attempt is one question
        total_questions_answered = total_attempts
        total_correct = sum(1 for att in attempts if att.get("is_correct"))
        
        # Stats by difficulty
        easy_attempts = [a for a in attempts if a.get("difficulty") == "easy"]
        medium_attempts = [a for a in attempts if a.get("difficulty") == "medium"]
        
        easy_correct = sum(1 for a in easy_attempts if a.get("is_correct"))
        easy_total = len(easy_attempts)
        easy_avg = (easy_correct / easy_total * 100) if easy_total > 0 else 0
        
        medium_correct = sum(1 for a in medium_attempts if a.get("is_correct"))
        medium_total = len(medium_attempts)
        medium_avg = (medium_correct / medium_total * 100) if medium_total > 0 else 0
        
        overall_avg = (total_correct / total_questions_answered * 100) if total_questions_answered > 0 else 0
        
        # Get total questions available
        total_questions = aptitude_questions_collection.count_documents({})
        easy_count = aptitude_questions_collection.count_documents({"difficulty": "easy"})
        medium_count = aptitude_questions_collection.count_documents({"difficulty": "medium"})
        
        # Get user data for DSA stats
        user_data = users_collection.find_one({"_id": user_id_obj})
        dsa_score = user_data.get("dsa_score", 0) if user_data else 0
        solved_questions = user_data.get("solved_questions", []) if user_data else []
        dsa_solved_count = len(solved_questions)

        return jsonify({
            "total_attempts": total_attempts,
            "total_questions_answered": total_questions_answered,
            "total_correct": total_correct,
            "overall_average": round(overall_avg, 2),
            "easy": {
                "attempts": easy_total,
                "correct": easy_correct,
                "total": easy_total,
                "average": round(easy_avg, 2),
                "available": easy_count
            },
            "medium": {
                "attempts": medium_total,
                "correct": medium_correct,
                "total": medium_total,
                "average": round(medium_avg, 2),
                "available": medium_count
            },
            "total_available": total_questions,
            "dsa_score": dsa_score,
            "dsa_solved_count": dsa_solved_count
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/aptitude/submit", methods=["POST"])
@login_required
def submit_aptitude_quiz():
    """Submit aptitude quiz attempt."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    
    try:
        data = request.get_json()
        difficulty = data.get("difficulty")
        user_answers = data.get("user_answers", {})
        question_ids = data.get("question_ids", [])
        
        if not difficulty or difficulty not in ["easy", "medium", "hard"]:
            return jsonify({"error": "Invalid difficulty level"}), 400
        
        # Get questions to verify answers
        questions = list(aptitude_questions_collection.find({
            "_id": {"$in": [ObjectId(qid) for qid in question_ids]}
        }))
        
        if len(questions) != len(question_ids):
            return jsonify({"error": "Some questions not found"}), 404
        
        # Calculate score
        score = 0
        total_questions = len(questions)
        correct_answers = {}
        
        for q in questions:
            qid = str(q["_id"])
            correct_index = q.get("correct", 0)
            correct_answers[qid] = correct_index
            user_answer = user_answers.get(qid)
            if user_answer is not None and int(user_answer) == int(correct_index):
                score += 1
        
        percentage = round((score / total_questions) * 100, 2) if total_questions > 0 else 0
        
        # Save attempt
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
        
        attempt = {
            "user_id": user_id_obj,
            "username": current_user.username,
            "difficulty": difficulty,
            "score": score,
            "total_questions": total_questions,
            "percentage": percentage,
            "user_answers": user_answers,
            "correct_answers": correct_answers,
            "question_ids": question_ids,
            "completed_at": datetime.now(timezone.utc)
        }
        
        aptitude_attempts_collection.insert_one(attempt)
        
        return jsonify({
            "score": score,
            "total_questions": total_questions,
            "percentage": percentage
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/aptitude/generate-questions", methods=["POST"])
@login_required
def generate_aptitude_questions():
    """Generate aptitude questions using AI (admin function to seed database)."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    
    try:
        data = request.get_json()
        count = int(data.get("count", 100))
        difficulty = data.get("difficulty", "easy")
        
        if difficulty not in ["easy", "medium"]:
            return jsonify({"error": "Invalid difficulty"}), 400
        
        if count < 1 or count > 1000:
            return jsonify({"error": "Count must be between 1 and 1000"}), 400
        
        # Check existing count
        existing = aptitude_questions_collection.count_documents({"difficulty": difficulty})
        if existing >= 10000:
            return jsonify({"error": f"Already have {existing} {difficulty} questions. Maximum is 10000."}), 400
        
        # Generate questions in batches
        generated = []
        batch_size = 10
        
        for i in range(0, count, batch_size):
            current_batch = min(batch_size, count - i)
            
            difficulty_prompt = {
                "easy": "Easy: Simple arithmetic, basic logic, straightforward reasoning questions suitable for beginners.",
                "medium": "Medium: Moderate complexity involving problem-solving, data interpretation, and analytical thinking.",
                "hard": "Hard: Complex problems requiring advanced reasoning, multiple steps, and deep analytical skills."
            }
            
            prompt = (
                f"Generate {current_batch} aptitude test questions. "
                f"Difficulty: {difficulty_prompt.get(difficulty, difficulty_prompt['easy'])}\n\n"
                "Return ONLY valid JSON (no markdown, no prose) in this exact format:\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
                '      "question": "Question text here",\n'
                '      "options": ["Option A", "Option B", "Option C", "Option D"],\n'
                '      "correct": 0,\n'
                '      "explanation": "Brief explanation"\n'
                "    }\n"
                "  ]\n"
                "}\n\n"
                "Rules:\n"
                f"- Generate exactly {current_batch} questions.\n"
                "- Each question must have exactly 4 distinct options.\n"
                "- 'correct' must be the exact 0-based index (0, 1, 2, or 3) of the mathematically and logically correct option.\n"
                "- Double-check all mathematical calculations, equations, and logic to guarantee 100% precision.\n"
                "- Include a clear, step-by-step explanation showing the exact calculations or logic in 'explanation'.\n"
                "- Questions should cover: quantitative aptitude, logical reasoning, verbal ability, data interpretation.\n"
            )
            
            try:
                quiz_model = get_gemini_model(temperature=0.2) or model
                response = quiz_model.generate_content(prompt)
                response_text = _get_gemini_text(response)
                
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                    response_text = response_text.strip()
                elif response_text.startswith("```json"):
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                
                quiz_data = json.loads(response_text)
                questions = quiz_data.get("questions", [])
                
                for q in questions:
                    q["difficulty"] = difficulty
                    q["created_at"] = datetime.now(timezone.utc)
                
                if questions:
                    aptitude_questions_collection.insert_many(questions)
                    generated.extend(questions)
                
            except Exception as e:
                print(f"Error generating batch: {str(e)}")
                continue
        
        return jsonify({
            "success": True,
            "generated": len(generated),
            "difficulty": difficulty,
            "total_in_db": aptitude_questions_collection.count_documents({"difficulty": difficulty})
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/aptitude/submit-answer", methods=["POST"])
@login_required
def submit_aptitude_answer():
    """Submit a single aptitude answer."""
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    
    try:
        data = request.get_json()
        question_id = data.get("question_id")
        selected_option = data.get("selected_option")
        
        if not question_id or selected_option is None:
            return jsonify({"error": "Missing data"}), 400
            
        question = aptitude_questions_collection.find_one({"_id": ObjectId(question_id)})
        if not question:
            return jsonify({"error": "Question not found"}), 404
            
        correct_option = question.get("correct", 0)
        is_correct = int(selected_option) == int(correct_option)
        
        # Save attempt
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
            
        attempt = {
            "user_id": user_id_obj,
            "username": current_user.username,
            "question_id": ObjectId(question_id),
            "difficulty": question.get("difficulty", "easy"),
            "selected_option": int(selected_option),
            "correct_option": int(correct_option),
            "is_correct": is_correct,
            "timestamp": datetime.now(timezone.utc)
        }
        
        aptitude_practice_history_collection.insert_one(attempt)
        
        return jsonify({
            "success": True,
            "is_correct": is_correct,
            "correct_option": correct_option,
            "explanation": question.get("explanation", "")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user-chats")
@login_required
def api_user_chats():
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    
    try:
        # robust user_id handling
        user_id = current_user.id
        user_id_obj = None
        try:
            user_id_obj = ObjectId(user_id)
        except:
            pass
            
        # Query for both string and ObjectId versions of user_id to be safe
        query_conditions = [{"user_id": str(user_id)}]
        if user_id_obj:
            query_conditions.append({"user_id": user_id_obj})
            
        query = {"$or": query_conditions}
        
        # DEBUG LOGGING
        print(f"API_USER_CHATS: UserID={user_id} (Type: {type(user_id)})")
        print(f"API_USER_CHATS: Query={query}")
        
        # Fetch sessions, sorted by newest first
        sessions = list(chat_sessions_collection.find(query).sort("updated_at", -1).limit(50))
        
        print(f"API_USER_CHATS: Found {len(sessions)} sessions")
        
        formatted_sessions = []
        for s in sessions:
            # Safely get title, defaulting to "New Chat"
            title = s.get("title")
            if not title or title == "(no title)":
                title = "New Chat"
                
            formatted_sessions.append({
                "_id": str(s["_id"]),
                "title": title,
                "timestamp": s.get("updated_at")
            })
            
        return jsonify({"conversations": formatted_sessions})
    except Exception as e:
        print(f"Error in api_user_chats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/get_chat/<chat_id>")
@login_required
def api_get_chat(chat_id):
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
        user_id_str = str(current_user.id)
        
        chat = chat_sessions_collection.find_one({
            "_id": ObjectId(chat_id),
            "user_id": {"$in": [user_id_obj, user_id_str]}
        })
        
        if not chat:
            return jsonify({"error": "Chat not found"}), 404
            
        return jsonify({
            "id": str(chat["_id"]),
            "title": chat.get("title", "New Chat"),
            "messages": chat.get("messages", [])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user-chats/<chat_id>", methods=["DELETE"])
@login_required
def api_delete_chat(chat_id):
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
        user_id_str = str(current_user.id)
        
        result = chat_sessions_collection.delete_one({
            "_id": ObjectId(chat_id),
            "user_id": {"$in": [user_id_obj, user_id_str]}
        })
        
        if result.deleted_count > 0:
            return jsonify({"success": True})
        return jsonify({"error": "Chat not found or unauthorized"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user-quizzes")
@login_required
def api_user_quizzes():
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
        user_id_str = str(current_user.id)
        
        quizzes = list(quiz_scores_collection.find(
            {"user_id": {"$in": [user_id_obj, user_id_str]}}
        ).sort("completed_at", -1))
        
        for q in quizzes:
            q["_id"] = str(q["_id"])
            q["user_id"] = str(q["user_id"])
            
        return jsonify({"quizzes": quizzes})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user-custom-attempts")
@login_required
def api_user_custom_attempts():
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
        user_id_str = str(current_user.id)
        
        attempts = list(custom_quiz_attempts_collection.find(
            {"user_id": {"$in": [user_id_obj, user_id_str]}}
        ).sort("submitted_at", -1))
        
        for a in attempts:
            a["_id"] = str(a["_id"])
            if "user_id" in a: a["user_id"] = str(a["user_id"])
            
        return jsonify({"attempts": attempts})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/my-custom-quizzes")
@login_required
def api_my_custom_quizzes():
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
        user_id_str = str(current_user.id)
        
        quizzes = list(custom_quizzes_collection.find(
            {"owner_id": {"$in": [user_id_obj, user_id_str]}}
        ).sort("created_at", -1))
        
        for q in quizzes:
            q["_id"] = str(q["_id"])
            q["owner_id"] = str(q["owner_id"])
            
            attempts = list(custom_quiz_attempts_collection.find({"quiz_code": q["code"]}))
            q["attempts_count"] = len(attempts)
            
            formatted_attempts = []
            for att in attempts:
                att["_id"] = str(att["_id"])
                formatted_attempts.append({
                    "attempt_id": str(att["_id"]),
                    "username": att.get("username", "Anonymous"),
                    "score": att.get("score", 0),
                    "total_questions": att.get("total_questions", 0),
                    "percentage": att.get("percentage", 0)
                })
            q["attempts"] = formatted_attempts
            
        return jsonify({"quizzes": quizzes})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/custom-quizzes/<code_val>/toggle-active", methods=["POST"])
@login_required
def api_toggle_quiz_active(code_val):
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
        user_id_str = str(current_user.id)
        
        quiz = custom_quizzes_collection.find_one({
            "code": code_val,
            "owner_id": {"$in": [user_id_obj, user_id_str]}
        })
        
        if not quiz:
            return jsonify({"error": "Quiz not found or unauthorized"}), 404
            
        new_status = not quiz.get("active", True)
        custom_quizzes_collection.update_one(
            {"_id": quiz["_id"]},
            {"$set": {"active": new_status}}
        )
        
        return jsonify({"success": True, "active": new_status})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/custom-quizzes/<code_val>/attempts/<attempt_id>", methods=["DELETE"])
@login_required
def api_delete_custom_attempt(code_val, attempt_id):
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
        user_id_str = str(current_user.id)
        
        quiz = custom_quizzes_collection.find_one({
            "code": code_val,
            "owner_id": {"$in": [user_id_obj, user_id_str]}
        })
        
        if not quiz:
            return jsonify({"error": "Quiz not found or unauthorized"}), 404
            
        result = custom_quiz_attempts_collection.delete_one({"_id": ObjectId(attempt_id)})
        
        if result.deleted_count > 0:
            return jsonify({"success": True})
        return jsonify({"error": "Attempt not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/aptitude/stats")
@login_required
def api_aptitude_stats():
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
        user_id_str = str(current_user.id)
        
        # Get user data for DSA stats
        try:
            uid = ObjectId(current_user.id)
            user_data = users_collection.find_one({"_id": uid})
        except Exception:
            user_data = None

        solved_questions = user_data.get("solved_questions", []) if user_data else []
        
        # Get all practice attempts
        attempts = list(aptitude_practice_history_collection.find({
            "$or": [
                {"user_id": user_id_obj},
                {"user_id": current_user.id}
            ]
        }))
        
        # Calculate stats
        total_attempts = len(attempts) # Each attempt is one question
        total_questions_answered = total_attempts
        total_correct = sum(1 for att in attempts if att.get("is_correct"))
        
        # Stats by difficulty
        easy_attempts = [a for a in attempts if a.get("difficulty") == "easy"]
        medium_attempts = [a for a in attempts if a.get("difficulty") == "medium"]
        
        easy_correct = sum(1 for a in easy_attempts if a.get("is_correct"))
        easy_total = len(easy_attempts)
        easy_avg = (easy_correct / easy_total * 100) if easy_total > 0 else 0
        
        medium_correct = sum(1 for a in medium_attempts if a.get("is_correct"))
        medium_total = len(medium_attempts)
        medium_avg = (medium_correct / medium_total * 100) if medium_total > 0 else 0
        
        overall_avg = (total_correct / total_questions_answered * 100) if total_questions_answered > 0 else 0
        
        # Get total questions available
        total_questions = aptitude_questions_collection.count_documents({})
        easy_count = aptitude_questions_collection.count_documents({"difficulty": "easy"})
        medium_count = aptitude_questions_collection.count_documents({"difficulty": "medium"})
        
        print(f"DEBUG: User {current_user.username} DSA Score: {current_user.dsa_score}")
        print(f"DEBUG: User {current_user.username} Solved Questions: {solved_questions}")
        
        return jsonify({
            "total_attempts": total_attempts,
            "total_questions_answered": total_questions_answered,
            "total_correct": total_correct,
            "overall_average": round(overall_avg, 2),
            "easy": {
                "attempts": easy_total,
                "correct": easy_correct,
                "total": easy_total,
                "average": round(easy_avg, 2),
                "available": easy_count
            },
            "medium": {
                "attempts": medium_total,
                "correct": medium_correct,
                "total": medium_total,
                "average": round(medium_avg, 2),
                "available": medium_count
            },
            "total_available": total_questions,
            "dsa_score": user_data.get("dsa_score", 0) if user_data else 0,
            "dsa_solved_count": len(solved_questions)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/aptitude/attempts")
@login_required
def api_aptitude_attempts():
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
        user_id_str = str(current_user.id)
        
        attempts = list(aptitude_attempts_collection.find(
            {"user_id": {"$in": [user_id_obj, user_id_str]}}
        ).sort("completed_at", -1))
        
        for a in attempts:
            a["_id"] = str(a["_id"])
            a["user_id"] = str(a["user_id"])
            
        return jsonify({"attempts": attempts})
    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route("/test-email")
def test_email():
    """Debug route to test email sending synchronously with network diagnostics."""
    recipient_email = request.args.get("email")
    if not recipient_email:
        if current_user.is_authenticated:
            recipient_email = current_user.email
        else:
            return "Please provide email parameter: /test-email?email=your@email.com"
    
    diagnostics = {}
    
    # 1. DNS Resolution Check
    try:
        ip_list = socket.getaddrinfo(SMTP_SERVER, None)
        diagnostics["dns_resolution"] = [ip[4][0] for ip in ip_list]
    except Exception as e:
        diagnostics["dns_resolution"] = f"Failed: {str(e)}"

    # 2. Connectivity Check (Raw Socket)
    for port in [465, 587]:
        try:
            sock = socket.create_connection((SMTP_SERVER, port), timeout=5)
            diagnostics[f"port_{port}_connectivity"] = "Success"
            sock.close()
        except Exception as e:
            diagnostics[f"port_{port}_connectivity"] = f"Failed: {str(e)}"

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = recipient_email
        msg['Subject'] = "Test Email - LernyX Debug"
        body = f"This is a test email to verify SMTP configuration.\n\nDiagnostics:\n{json.dumps(diagnostics, indent=2)}"
        msg.attach(MIMEText(body, 'plain'))
        text = msg.as_string()
        
        # Attempt 1: Try SMTP_SSL on port 465
        try:
            server = smtplib.SMTP_SSL(SMTP_SERVER, 465, timeout=10)
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, recipient_email, text)
            server.quit()
            return jsonify({
                "success": True, 
                "message": f"Email sent successfully via Port 465 to {recipient_email}",
                "diagnostics": diagnostics
            })
        except Exception as e1:
            error1 = str(e1)
            
            # Attempt 2: Fallback to STARTTLS on port 587
            try:
                server = smtplib.SMTP(SMTP_SERVER, 587, timeout=10)
                server.starttls()
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(EMAIL_ADDRESS, recipient_email, text)
                server.quit()
                return jsonify({
                    "success": True, 
                    "message": f"Email sent successfully via Port 587 (Fallback) to {recipient_email}. Error on 465: {error1}",
                    "diagnostics": diagnostics
                })
            except Exception as e2:
                return jsonify({
                    "success": False, 
                    "error": f"Failed on both ports. Port 465 error: {error1}. Port 587 error: {str(e2)}",
                    "diagnostics": diagnostics
                }), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Setup error: {str(e)}", "diagnostics": diagnostics}), 500



@app.route("/api/generate_questions", methods=["POST"])
@login_required
def generate_questions():
    try:
        # Generate a small batch of 3 questions
        questions = generate_questions_batch(batch_size=3)
        
        if not questions:
            return jsonify({"error": "Failed to generate questions. API quota might be exceeded."}), 500
            
        count = 0
        for q in questions:
            # Check for duplicates
            if not db.dsa_questions.find_one({"title": q["title"]}):
                q["created_at"] = datetime.now(timezone.utc)
                db.dsa_questions.insert_one(q)
                count += 1
                
        return jsonify({"count": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/chat")
@app.route("/chat/<chat_id>")
@login_required
def chat_main(chat_id=None):
    return render_template("index.html")

@app.route("/videoquiz")
@login_required
def videoquiz():
    return render_template("videoquiz.html")

@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    # Handle both JSON and Multipart/Form-Data
    if request.is_json:
        data = request.get_json()
        user_message = data.get("message", "")
        conversation_id = data.get("conversation_id") or data.get("chat_id")
        file = None
    else:
        user_message = request.form.get("message", "")
        conversation_id = request.form.get("conversation_id") or request.form.get("chat_id")
        file = request.files.get("file")

    if not user_message and not file:
        return jsonify({"error": "No message or file provided"}), 400
        
    # Handle file upload
    attachment_path = None
    attachment_info = None
    
    if file and file.filename:
        try:
            # Create temp directory if not exists
            temp_dir = tempfile.mkdtemp()
            filename = file.filename
            # Sanitize filename
            filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in "._- "])
            attachment_path = os.path.join(temp_dir, filename)
            file.save(attachment_path)
            
            attachment_info = {
                "filename": filename,
                "type": "image" if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) else "pdf" if filename.lower().endswith('.pdf') else "file"
            }
            
            # Index for RAG if it's a PDF or Text
            if filename.lower().endswith(('.pdf', '.txt')):
                print(f"Indexing {filename} for RAG...")
                rag_utils.process_document(attachment_path)
        except Exception as e:
            print(f"Error saving uploaded file: {str(e)}")
            return jsonify({"error": f"Failed to process file: {str(e)}"}), 500

    try:
        # Fetch history if conversation_id exists
        history = []
        if conversation_id and MONGODB_AVAILABLE:
            try:
                session = chat_sessions_collection.find_one({
                    "_id": ObjectId(conversation_id),
                    "user_id": {"$in": [ObjectId(current_user.id), str(current_user.id)]}
                })
                print(f"FETCH_HISTORY: ID={conversation_id}, User={current_user.id}, Found={bool(session)}")
                if session:
                    history = session.get("messages", [])[-10:] # Limit context to last 10 messages
            except Exception as e:
                print(f"Error fetching history: {e}")
        
        # Call Gemini
        answer = ask_gemini(user_message, history, attachment_path)
        
        # Clean up temp file
        if attachment_path and os.path.exists(attachment_path):
            try:
                os.remove(attachment_path)
                os.rmdir(os.path.dirname(attachment_path))
            except Exception as e:
                print(f"Error cleaning up temp file: {e}")
        
        # Store conversation in MongoDB
        if MONGODB_AVAILABLE:
            try:
                # Store user_id as ObjectId for consistency
                try:
                    user_id_obj = ObjectId(current_user.id)
                except:
                    user_id_obj = current_user.id
                
                timestamp = datetime.now(timezone.utc)
                
                user_msg_obj = {
                    "role": "user", 
                    "content": user_message, 
                    "timestamp": timestamp
                }
                if attachment_info:
                    user_msg_obj["attachment"] = attachment_info
                
                new_messages = [
                    user_msg_obj,
                    {"role": "assistant", "content": answer, "timestamp": timestamp}
                ]
                
                if conversation_id:
                    # Update existing session
                    chat_sessions_collection.update_one(
                        {"_id": ObjectId(conversation_id)},
                        {
                            "$push": {"messages": {"$each": new_messages}},
                            "$set": {"updated_at": timestamp}
                        }
                    )
                    chat_id = conversation_id
                else:
                    # Create new session
                    # Generate a title from the first message
                    title_text = user_message.strip() if user_message and user_message.strip() else (f"Analysis of {attachment_info['filename']}" if attachment_info else "New Chat")
                    title = title_text[:50] + "..." if len(title_text) > 50 else title_text
                    
                    session = {
                        "user_id": user_id_obj,
                        "username": current_user.username,
                        "title": title,
                        "messages": new_messages,
                        "created_at": timestamp,
                        "updated_at": timestamp
                    }
                    result = chat_sessions_collection.insert_one(session)
                    chat_id = str(result.inserted_id)
                    print(f"INSERT_CHAT: NewID={chat_id}, UserID={user_id_obj}, Type={type(user_id_obj)}, Title={title}")
                    
            except Exception as e:
                print(f"Error storing conversation: {str(e)}")
                print(f"{datetime.now()}: Error storing conversation: {str(e)}")
                chat_id = None
        else:
            print("DEBUG: MONGODB_AVAILABLE is False")
            chat_id = None
        
        return jsonify({"response": answer, "conversation_id": chat_id})
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

@app.route("/api/chat/<chat_id>", methods=["GET"])
@login_required
def get_chat_history(chat_id):
    if not MONGODB_AVAILABLE:
        return jsonify({"error": "Database unavailable"}), 500
    try:
        try:
            user_id_obj = ObjectId(current_user.id)
        except:
            user_id_obj = current_user.id
            
        session = chat_sessions_collection.find_one({
            "_id": ObjectId(chat_id),
            "user_id": {"$in": [user_id_obj, str(current_user.id)]}
        })
        
        if not session:
            return jsonify({"error": "Chat not found"}), 404
            
        return jsonify({
            "conversation_id": str(session["_id"]),
            "title": session.get("title"),
            "messages": session.get("messages", [])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("---------------------------------------------------")
    print("   STARTING LEARNEX SERVER - VERSION: FIX_CHAT_TITLES_V2")
    print("---------------------------------------------------")
    app.run(debug=True)
