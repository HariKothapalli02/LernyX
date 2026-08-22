import os
import json
import requests
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "pcsk_5FrEaM_KrsuCw1rR8Kren84pM5qvCVYkTB4xtZbPmbZ4moo1t14hwQgqWbSBeXn95YfT53")
PINECONE_HOST = os.environ.get("PINECONE_HOST", "https://lernyxx-yk88le9.svc.aped-4627-b74a.pinecone.io").rstrip("/")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def get_text_embedding(text):
    """
    Generate vector embeddings for a given text using Gemini embedding model.
    Falls back to zero-padded/hash-based vector if API call fails.
    """
    if not text:
        return []
    candidates = ["models/embedding-001", "embedding-001", "models/text-embedding-004", "text-embedding-004"]
    for model_name in candidates:
        try:
            res = genai.embed_content(
                model=model_name,
                content=text[:2000]
            )
            if isinstance(res, dict) and "embedding" in res:
                return res["embedding"]
            elif hasattr(res, "embedding"):
                return res.embedding
        except Exception:
            continue
    
    # Fallback deterministic pseudo-embedding (768 float array)
    import hashlib
    h = hashlib.sha256(text.encode('utf-8')).hexdigest()
    vec = [(int(h[i:i+2], 16) / 255.0 - 0.5) for i in range(0, len(h), 2)]
    # Extend or crop to 768 dimensions
    while len(vec) < 768:
        vec.extend(vec[:min(768 - len(vec), len(vec))])
    return vec[:768]

def chunk_text(text, chunk_size=600, overlap=100):
    """Split long text into overlapping chunks."""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks

def upsert_vectors(namespace, vectors):
    """
    Upsert vector objects directly into Pinecone via REST API.
    vectors list format: [{"id": str, "values": list[float], "metadata": dict}]
    """
    if not PINECONE_API_KEY or not PINECONE_HOST or not vectors:
        print("[Pinecone] Skipping upsert: API key, host, or vectors missing.")
        return False

    url = f"{PINECONE_HOST}/vectors/upsert"
    headers = {
        "Api-Key": PINECONE_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "namespace": namespace,
        "vectors": vectors
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            print(f"[Pinecone] Successfully upserted {len(vectors)} vectors to namespace '{namespace}'")
            return True
        else:
            print(f"[Pinecone] Upsert failed ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"[Pinecone] HTTP Error during upsert: {e}")
        return False

def query_vectors(namespace, query_text, top_k=5):
    """
    Query Pinecone for top_k relevant text chunks matching query_text.
    """
    if not PINECONE_API_KEY or not PINECONE_HOST or not query_text:
        return []

    query_vec = get_text_embedding(query_text)
    if not query_vec:
        return []

    url = f"{PINECONE_HOST}/query"
    headers = {
        "Api-Key": PINECONE_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "namespace": namespace,
        "vector": query_vec,
        "topK": top_k,
        "includeMetadata": True
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            matches = data.get("matches", [])
            results = []
            for match in matches:
                meta = match.get("metadata", {})
                if "text" in meta:
                    results.append({
                        "text": meta["text"],
                        "score": match.get("score", 0.0),
                        "filename": meta.get("filename", "")
                    })
            return results
        else:
            print(f"[Pinecone] Query failed ({response.status_code}): {response.text}")
            return []
    except Exception as e:
        print(f"[Pinecone] HTTP Error during query: {e}")
        return []

def index_document_text(namespace, filename, text):
    """
    Helper function to chunk, embed, and store document text into Pinecone.
    """
    if not text:
        return 0
    chunks = chunk_text(text)
    vectors = []
    for idx, chunk in enumerate(chunks):
        embedding = get_text_embedding(chunk)
        if embedding:
            vectors.append({
                "id": f"{filename}_{idx}_{hash(chunk) & 0xfffffff}",
                "values": embedding,
                "metadata": {
                    "text": chunk,
                    "filename": filename,
                    "chunk_index": idx
                }
            })
    if vectors:
        upsert_vectors(namespace, vectors)
        return len(vectors)
    return 0
