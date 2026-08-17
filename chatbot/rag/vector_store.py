import os
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# API key is resolved lazily at call time — importing this module never crashes
# even if GEMINI_API_KEY is not set yet.
def _get_api_key():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
    return key


def _get_embeddings():
    api_key = _get_api_key()
    genai.configure(api_key=api_key)
    return GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",
        google_api_key=api_key,
    )


from chatbot.config import VECTOR_DB_DIR


def create_vector_store(documents, persist_directory=None):
    """Create a vector store from document chunks."""
    if persist_directory is None:
        persist_directory = VECTOR_DB_DIR

    embeddings = _get_embeddings()
    vector_store = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=persist_directory,
    )
    print(f"Vector store created with {len(documents)} document chunks")
    print(f"Vector store persisted to {persist_directory}")
    return vector_store


def load_vector_store(persist_directory=None):
    """Load an existing vector store."""
    if persist_directory is None:
        persist_directory = VECTOR_DB_DIR

    embeddings = _get_embeddings()
    return Chroma(
        persist_directory=persist_directory,
        embedding_function=embeddings,
    )
