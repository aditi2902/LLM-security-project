import json
import os
from typing import List, Dict

MEMORY_STORE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dataset', 'memory_store.json')

def load_memories() -> List[Dict]:
    """Load memories from the local JSON store."""
    if not os.path.exists(MEMORY_STORE_FILE):
        return []
    try:
        with open(MEMORY_STORE_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def save_memories(memories: List[Dict]):
    """Save memories to the local JSON store."""
    with open(MEMORY_STORE_FILE, 'w') as f:
        json.dump(memories, f, indent=4)

def add_memory(memory_object: Dict):
    """Add a new memory object to the store."""
    memories = load_memories()
    memories.append(memory_object)
    save_memories(memories)

def get_all_memories() -> List[Dict]:
    """Retrieve all stored memories."""
    return load_memories()

def clear_memories():
    """Clear all memories from the store."""
    save_memories([])
