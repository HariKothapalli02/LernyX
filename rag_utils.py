import os
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv

load_dotenv()

# Initialize embeddings
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004",
    google_api_key=os.environ.get("GEMINI_API_KEY")
)

# Local storage path for the vector index
VECTOR_DB_PATH = "faiss_index"

def process_document(file_path):
    """Load, chunk, and index a document."""
    try:
        if file_path.lower().endswith('.pdf'):
            loader = PyPDFLoader(file_path)
        else:
            loader = TextLoader(file_path)
        
        documents = loader.load()
        
        # Split into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            length_function=len,
        )
        chunks = text_splitter.split_documents(documents)
        
        # Create or update vector store
        if os.path.exists(VECTOR_DB_PATH):
            vector_store = FAISS.load_local(VECTOR_DB_PATH, embeddings, allow_dangerous_deserialization=True)
            vector_store.add_documents(chunks)
        else:
            vector_store = FAISS.from_documents(chunks, embeddings)
        
        # Save locally
        vector_store.save_local(VECTOR_DB_PATH)
        return True
    except Exception as e:
        print(f"Error processing document for RAG: {e}")
        return False

def get_relevant_context(query, k=3):
    """Retrieve relevant chunks for a query."""
    try:
        if not os.path.exists(VECTOR_DB_PATH):
            return ""
        
        vector_store = FAISS.load_local(VECTOR_DB_PATH, embeddings, allow_dangerous_deserialization=True)
        results = vector_store.similarity_search(query, k=k)
        
        context = "\n---\n".join([doc.page_content for doc in results])
        return context
    except Exception as e:
        print(f"Error retrieving context: {e}")
        return ""
