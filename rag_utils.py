import os
import json
import math
import google.generativeai as genai
from pypdf import PdfReader
from dotenv import load_dotenv

load_dotenv()

# Configure Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Local storage for the "vector db"
KNOWLEDGE_BASE_PATH = "knowledge_base.json"

def dot_product(v1, v2):
    return sum(x * y for x, y in zip(v1, v2))

def magnitude(v):
    return math.sqrt(sum(x * x for x in v))

def cosine_similarity(v1, v2):
    mag1 = magnitude(v1)
    mag2 = magnitude(v2)
    if mag1 == 0 or mag2 == 0:
        return 0
    return dot_product(v1, v2) / (mag1 * mag2)

def split_text(text, chunk_size=1000, overlap=100):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += (chunk_size - overlap)
    return chunks

def process_document(file_path):
    """Load, chunk, and index a document using a lightweight approach."""
    try:
        text = ""
        if file_path.lower().endswith('.pdf'):
            reader = PdfReader(file_path)
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
        else:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        
        if not text.strip():
            return False

        chunks = split_text(text)
        
        # Get embeddings for chunks
        new_entries = []
        for chunk in chunks:
            if not chunk.strip(): continue
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=chunk,
                task_type="retrieval_document"
            )
            new_entries.append({
                "content": chunk,
                "embedding": result['embedding']
            })
        
        # Load existing or create new
        kb = []
        if os.path.exists(KNOWLEDGE_BASE_PATH):
            try:
                with open(KNOWLEDGE_BASE_PATH, 'r') as f:
                    kb = json.load(f)
            except:
                kb = []
        
        kb.extend(new_entries)
        
        # Save (limit size to prevent huge files)
        if len(kb) > 1000:
            kb = kb[-1000:]
            
        with open(KNOWLEDGE_BASE_PATH, 'w') as f:
            json.dump(kb, f)
            
        return True
    except Exception as e:
        print(f"Error in Lite RAG processing: {e}")
        return False

def get_relevant_context(query, k=3):
    """Retrieve relevant chunks using pure Python cosine similarity."""
    try:
        if not os.path.exists(KNOWLEDGE_BASE_PATH):
            return ""
        
        # Embed query
        query_result = genai.embed_content(
            model="models/text-embedding-004",
            content=query,
            task_type="retrieval_query"
        )
        query_embedding = query_result['embedding']
        
        # Load KB
        with open(KNOWLEDGE_BASE_PATH, 'r') as f:
            kb = json.load(f)
        
        if not kb:
            return ""

        # Calculate similarities
        scored_chunks = []
        for entry in kb:
            score = cosine_similarity(query_embedding, entry['embedding'])
            scored_chunks.append((score, entry['content']))
        
        # Sort and take top k
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [chunk for score, chunk in scored_chunks[:k]]
        
        return "\n---\n".join(top_chunks)
    except Exception as e:
        print(f"Error in Lite RAG retrieval: {e}")
        return ""
