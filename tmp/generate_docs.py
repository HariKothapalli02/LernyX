import sys
import subprocess
import os

try:
    import docx
except ImportError:
    print("Installing python-docx...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-docx"])
    import docx

from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

document = Document()

# Define styles and helpers
style = document.styles['Normal']
font = style.font
font.name = 'Arial'
font.size = Pt(11)

def add_h(text, level=1):
    return document.add_heading(text, level=level)

def add_p(text, style='Normal', bold=False):
    p = document.add_paragraph(style=style)
    run = p.add_run(text)
    run.bold = bold
    return p

def add_bullet(text):
    return document.add_paragraph(text, style='List Bullet')

def add_numbered(text):
    return document.add_paragraph(text, style='List Number')

# --- PAGE 1: TITLE PAGE ---
for _ in range(5):
    add_p("")
title = document.add_heading("LernyX: The Next Generation AI-Powered Educational Ecosystem", 0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
for _ in range(3):
    add_p("")
sub = document.add_paragraph("Comprehensive Project Documentation & Architecture Guide")
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
sub.runs[0].font.size = Pt(16)
for _ in range(10):
    add_p("")
add_p("Developed leveraging Python, Flask, MongoDB, and Google Gemini AI", 'Normal').alignment = WD_ALIGN_PARAGRAPH.CENTER
document.add_page_break()

# --- PAGE 2: ABSTRACT ---
add_h("ABSTRACT")
add_p("LernyX is an advanced, AI-driven educational platform designed to revolutionize coding education and interactive learning. Built with a robust backend using Python (Flask) and MongoDB, it features a highly interactive, 3D-enhanced frontend and integrates Google's Gemini AI models to serve as an intelligent, real-time virtual tutor. Traditional e-learning platforms often suffer from a lack of personalized guidance and static content. LernyX addresses these critical flaws by seamlessly combining intelligent real-time conversational agents, dynamic interactive assessments, and hands-on coding environments within the browser.")
add_p("Key innovations include 'Video Intelligence', which directly translates standard YouTube educational content into structured, interactive quizzes by combining transcript extraction and Large Language Models (LLMs). Furthermore, LernyX supports Retrieval-Augmented Generation (RAG) to ensure the AI's responses are context-aware and highly accurate. The inclusion of an in-browser web compiler for Python, Java, and Data Structures & Algorithms ensures that learners can practice instantaneously. Through the unification of secure authentication workflows, robust database schemas, and AI integrations, LernyX acts as a blueprint for the future of decentralized, AI-empowered education.")
document.add_page_break()

# --- PAGE 3: TABLE OF CONTENTS (Placeholder due to python-docx limits, manual indexing added) ---
add_h("TABLE OF CONTENTS")
add_p("1. Introduction")
add_p("2. Problem Statement & Motivation")
add_p("3. System Requirements")
add_p("4. Technology Stack")
add_p("5. System Architecture and Design")
add_p("6. Detailed Module Descriptions")
add_p("7. Database Design & Schemas")
add_p("8. Integrations & API Orchestration")
add_p("9. Security & Authentication Mechanisms")
add_p("10. Testing & Validation")
add_p("11. Conclusion & Future Enhancements")
document.add_page_break()

# --- PAGE 4: INTRODUCTION & PROBLEM STATEMENT ---
add_h("1. Introduction")
add_p("The rapid evolution of Artificial Intelligence, particularly Large Language Models (LLMs) like Google's Gemini, has paved the way for massive transformations in the educational technology sector. LernyX is conceived out of the necessity to integrate these powerful LLMs into a platform that caters specifically to students, developers, and continuous learners.")
add_p("LernyX operates as a multi-faceted web application. From the perspective of user interaction, it provides a deeply immersive UI designed with Three.js. However, functionally, it is a micro-services-inspired monolith handling background transcript generation, API calls to the Gemini models, OTP validation via specialized SMTP gateways, and persistent knowledge retrieval via Pinecone/FAISS indexing.")

add_h("2. Problem Statement & Motivation")
add_h("2.1 Existing Systems", level=2)
add_p("Many currently existing educational platforms present content in a highly read-only format. Users watch videos or read articles, but the interaction is highly decoupled from the learning source. Assessment generally occurs much later, leading to low retention rates.")
add_h("2.2 The Proposed Solution", level=2)
add_p("LernyX proposes an integrated learning loop. A user watches an educational video, and in real-time, the system can extract the knowledge using API scraping and generate an evaluation structure. Likewise, the user doesn't need to leave the environment to code, as the platform has integrated code compilation components.")
add_p("By significantly reducing the friction between learning, evaluating, and practicing, LernyX motivates learners to engage more deeply. Furthermore, providing a live AI Tutor acts as a 24/7 personalized teacher that can debug specific conceptual misunderstandings that traditional FAQs fail to answer.")

document.add_page_break()

# --- PAGE 5: SYSTEM REQUIREMENTS & TECH STACK ---
add_h("3. System Requirements")
add_h("3.1 Hardware Requirements", level=2)
add_bullet("Processor: Intel Core i5 or equivalent AMD Ryzen (for development), standard cloud instances (e.g., AWS t2.micro / Vercel Edge Networks) for deployment.")
add_bullet("Memory: 4 GB RAM minimum for local hosting.")
add_bullet("Storage: 200 MB disk space for the application, plus external high-availability database cluster (MongoDB Atlas).")

add_h("3.2 Software Requirements", level=2)
add_bullet("Operating System: Windows 10/11, macOS, or any Linux Distribution.")
add_bullet("Runtime Environment: Python 3.8 or higher.")
add_bullet("Web Browsers: Google Chrome, Mozilla Firefox, Safari, or Microsoft Edge (with JavaScript enabled).")

add_h("4. Technology Stack")
add_p("LernyX relies on a highly modernized technology stack. Each library and framework was carefully selected to optimize latency, scalability, and maintainability.")
add_h("4.1 Backend Framework", level=2)
add_p("Flask (Python): Flask was chosen due to its lightweight nature. As the project heavily relies on data processing, Web Scraping, and AI integration, passing instructions directly through Python via Flask enables asynchronous compatibility and prevents cold-starting overhead typically associated with heavier MVC frameworks (like Django).")

add_h("4.2 Database Infrastructure", level=2)
add_p("MongoDB & PyMongo: To deal with unstructured data (chat histories, nested JSON schemas from LLM quiz generation), MongoDB serves as the prime operational datastore. Its flexible indexing structure allows user records and historical attempts to be mutated dynamically without heavy schema migrations.")

add_h("4.3 Frontend Orchestration", level=2)
add_p("HTML5/CSS3 & Bootstrap: Provides a thoroughly responsive design framework.")
add_p("Three.js: Employs a low-level WebGL API to render beautiful 3D animations in the background, significantly reducing bounce rates by boosting visual immersion on the landing and dashboard pages.")

add_h("4.4 Third-Party Integrations", level=2)
add_p("Google Gemini SDK: Powers the conversational AI helper agent and generates intelligent quizzes.")
add_p("youtube-transcript-api / yt-dlp: Highly robust scraping mechanisms providing video title extraction, fallback mechanisms via OEmbed, and raw transcript injection.")

document.add_page_break()

# --- PAGE 6: ARCHITECTURE ---
add_h("5. System Architecture and Design")
add_p("The architecture of LernyX strictly divides the Application layer, Data Layer, and External Intelligence Layer. This loosely coupled model guarantees that if a third-party API (like Gemini or YouTube) drops out, the system implements graceful degradation rather than a total crash.")

add_h("5.1 Request Flow", level=2)
add_p("When a client sends a request (e.g., generating a quiz from a YouTube video), the following processes occur:")
add_numbered("The client payload is validated by Flask.")
add_numbered("A backend thread extracts the YouTube Video ID and simultaneously pings several external sources (yt-dlp, BeautifulSoup, Invideous instances) to ensure a high cache-hit rate for metadata.")
add_numbered("If transcripts are fetched, the server builds a heavily engineered prompt concatenating the transcript and precise JSON schema constraints.")
add_numbered("The prompt interfaces with Google's Gemini LLM. The application logic specifically accounts for markdown parsing, trailing commas, and incomplete JSON generation iteratively.")
add_numbered("The synthesized quiz objects are dumped into MongoDB.")
add_numbered("Flask renders the user-facing assessment template and serves the finalized interaction to the client.")

add_h("5.2 Retrieval-Augmented Generation (RAG) Flow", level=2)
add_p("LernyX's AI Chatbot isn't merely a wrapper around the Gemini API. It uses a Retrieval-Augmented Generation approach.")
add_bullet("Knowledge Base Extraction: The platform maintains specific rules, documentation, and specific context in a vector index (FAISS).")
add_bullet("Pre-computation: User messages are evaluated via embedding vectors.")
add_bullet("Context Injection: The closest matching domain data is prepended to the system prompt.")
add_bullet("Result: Gemini replies safely, mitigating hallucinations and grounding responses to the specific needs of the LernyX domain.")

document.add_page_break()

# --- PAGE 7: DETAILED MODULES ---
add_h("6. Detailed Module Descriptions")

add_h("6.1 Authentication Module", level=2)
add_p("The Authentication system guarantees the privacy of the user's generated datasets. Using Flask-Login, it implements a secure session token across multiple routes.")
add_p("Key highlights include the OTP verification system via Brevo/SMTP. Due to serverless execution environments (like Vercel), email threads are executed synchronously prior to returning contexts. Furthermore, passwords are automatically salted and hashed via Werkzeug's security protocols.")

add_h("6.2 Video Intelligence (Edu-Checker) Module", level=2)
add_p("A unique module within LernyX is its heuristic and AI-assisted educational verifier. To avoid users submitting entertainment content (e.g., irrelevant music videos) for quiz generation, the module runs the video's transcript/metadata through an initial 'educational filter' prompt.")
add_p("If the Gemini AI decides the content isn't instructional, it prevents quiz generation. If Gemini is rate-limited, the system falls back onto a hardcoded keyword substring heuristic matcher (looking for words such as 'tutorial', 'course', etc.).")

add_h("6.3 Aptitude & DSA Generation Module", level=2)
add_p("To serve engineering students and software developers, LernyX supports automatic generation of Data Structure and Algorithm coding questions. Utilizing custom scripts (e.g., generate_dsa_questions.py), it can batched-query the AI for specialized arrays, trees, and dynamic programming questions. These generated problems are stored historically for continuous practice.")

document.add_page_break()

# --- PAGE 8: DATABASE SCHEMA ---
add_h("7. Database Design & Schemas")
add_p("LernyX relies on MongoDB's BSON architecture. The following core collections dictate the system's relationships:")

add_h("7.1 Users Collection", level=2)
add_p("Stores the primary account data.")
add_bullet("_id: ObjectId()")
add_bullet("username: String")
add_bullet("email: String, Unique")
add_bullet("password_hash: String")
add_bullet("dsa_score: Integer")
add_bullet("api_key: String (Optional user-provided Gemini key)")

add_h("7.2 Quizzes / Custom Quizzes Collection", level=2)
add_p("Stores generated JSON artifacts to prevent duplicate API generation costs.")
add_bullet("video_id / code: String (Reference anchor)")
add_bullet("title: String")
add_bullet("questions: Array of Objects [{question, options, correct_index, explanation}]")
add_bullet("created_at: ISODate")

add_h("7.3 Chat Sessions Collection", level=2)
add_p("Stores the persistence strings of user chatbot communications.")
add_bullet("user_id: ObjectId Reference")
add_bullet("history: Array [{role, parts}]")
add_bullet("updated_at: ISODate")

document.add_page_break()

# --- PAGE 9: APIS AND INTEGRATIONS ---
add_h("8. Integrations & API Orchestration")
add_p("Orchestrating multiple asynchronous networks successfully forms the backbone of LernyX. The primary integrations include:")

add_h("8.1 YouTube Transcript Extraction Sandbox", level=2)
add_p("Fetching data from YouTube is notoriously volatile due to rolling anti-bot mechanisms. LernyX employs three fallback tiers:")
add_numbered("BeautifulSoup scraping for initial OpenGraph (OG) properties and embedded meta tags.")
add_numbered("The official youtube-transcript-api for verbatim closed-caption fetching.")
add_numbered("Yt-dlp with cookie headers and ignored error traces to handle heavily restricted geographic video contents and invidious instances to bypass API routing.")

add_h("8.2 Google Generative AI (Gemini Flash)", level=2)
add_p("Instead of relying on a single project key, LernyX has built an API-Key pool distributor function. Defending against quotas, 'get_gemini_model()' checks if the user has injected their own API Key; if not, it cycles randomly across available system keys.")

add_p("Furthermore, a specific text-parsing algorithm filters conversational Gemini outputs. The function '_get_gemini_text' mitigates random markdown fences (```json...```), truncates trailing commas natively, and removes control characters before returning payload outputs to the JSON engine natively via 'clean_json_text(text)'.")

document.add_page_break()

# --- PAGE 10: SECURITY, TESTING & CONCLUSION ---
add_h("9. Security & Authentication Mechanisms")
add_p("Web application security remains prioritized throughout the application. Flask executes the secret keys stored inside environments rather than hardcoding credentials into python logic.")
add_p("Cross-Site Scripting (XSS) is mitigated through Jinja2's auto-escaping templates. Cross-Site Request Forgery (CSRF) tokens remain strictly evaluated. Database Injection attacks are rendered ineffective due to the paradigm shift of NoSQL DB queries processing purely through Object Abstraction via PyMongo, completely sidestepping standard SQL concatenation vulnerabilities.")

add_h("10. Testing & Validation")
add_p("Testing for an application incorporating non-deterministic AI required multiple layers.")
add_h("10.1 Backend API Unit Testing", level=2)
add_p("Specific modules handling text generation and sanitization were unit-tested rigorously for edge cases involving corrupted JSON structures, validating 'clean_json_text()' functionality thoroughly.")
add_h("10.2 System/Load Evaluation", level=2)
add_p("Using mock configurations, the application safely verified fallback SMTP processing by manually rejecting Port 2525 and witnessing the system intelligently pivot into Port 587.")
add_h("10.3 Usability Testing", level=2)
add_p("Feedback heuristically established that long loading states caused dropoffs. As a result, CSS spinner integrations and optimistic rendering principles were validated against dummy datasets.")

add_h("11. Conclusion & Future Enhancements")
add_p("LernyX effectively consolidates video-based comprehension, practical code generation, and intelligent mentoring into a unified, lightweight, scalable web infrastructure. Moving forward, the project's roadmap points towards implementing a full multiplayer Code-Collaboration interface (via WebSockets or Socket.io integrations) and upgrading the LLM backend parameter constraints to support multimodal understanding (i.e., taking screenshots of handwritten mathematics equations and having the AI tutor auto-solve and quiz the student).")
add_p("Ultimately, LernyX proves that integrating Generative AI dynamically rather than statically creates a generational leap in active educational tools.")

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'document_expanded.docx')
document.save(output_path)
print(f"Expanded 10+ page documentation successfully saved to {output_path}")
