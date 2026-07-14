import os
import chromadb
from sentence_transformers import SentenceTransformer

# Initialize ChromaDB client and Embedding Model
# We use a lightweight, fast model that runs easily on CPU
MODEL_NAME = "all-MiniLM-L6-v2"
model = None

try:
    model = SentenceTransformer(MODEL_NAME)
except Exception as e:
    print(f"Failed to load sentence-transformers model: {e}")

# Base dir
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "dataset", "chroma_db")

# Create chroma client
chroma_client = chromadb.PersistentClient(path=DB_PATH)
# Get or create collection
collection = chroma_client.get_or_create_collection(name="prompt_security_cache")

def check_semantic_cache(prompt: str, similarity_threshold: float = 0.85) -> dict:
    """
    Checks if the incoming prompt is semantically close to any known blocked attacks.
    Returns a dict with 'safe': False and 'reason' if a match is found.
    """
    if not model:
        return {"safe": True}
        
    try:
        # Check if collection is empty
        if collection.count() == 0:
            return {"safe": True}
            
        # Encode the query prompt
        query_embedding = model.encode(prompt).tolist()
        
        # Query ChromaDB
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=1
        )
        
        if results and results["distances"] and len(results["distances"][0]) > 0:
            distance = results["distances"][0][0]
            # ChromaDB cosine distance: 0 is identical, 2 is opposite.
            # Cosine similarity = 1 - (distance / 2) if distance is cosine distance (default in Chroma is l2 or cosine depending on config, default is l2).
            # Let's check metadata or assume default L2 distance.
            # Default space is 'l2', so distance is squared L2 distance.
            # Let's enforce cosine distance for easier thresholding:
            # We can configure the collection to use cosine distance.
            # If distance is small (< 0.25 for cosine), it's highly similar.
            # Let's inspect the distance. If distance < 0.3 (highly similar), block.
            if distance < 0.35:
                category = results["metadatas"][0][0].get("category", "MALICIOUS_ATTACK")
                reason = f"Blocked by Semantic Cache: High similarity to a known {category} attack."
                return {
                    "safe": False,
                    "risk_score": 95,
                    "attack_type": category,
                    "reason": reason
                }
    except Exception as e:
        print(f"Error checking semantic cache: {e}")
        
    return {"safe": True}

def add_attack_to_cache(attack_text: str, category: str):
    """Adds a blocked/bypassed attack to the semantic cache for future fast-path blocking."""
    if not model:
        return
        
    try:
        import hashlib
        h = hashlib.sha256(attack_text.encode()).hexdigest()
        embedding = model.encode(attack_text).tolist()
        
        # Add to collection
        collection.add(
            embeddings=[embedding],
            documents=[attack_text],
            metadatas=[{"category": category}],
            ids=[h]
        )
    except Exception as e:
        print(f"Error adding to semantic cache: {e}")
