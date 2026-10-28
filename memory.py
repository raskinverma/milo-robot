"""
memory.py — Local semantic long-term memory for EMO Robot.

Uses ChromaDB (local vector store) + Ollama nomic-embed-text embeddings.
Memories persist across sessions in ~/.emo_robot/memory/

Equivalent to kek.html's memory.py but fully free & local.
"""

import os
import json
import time
import hashlib
import chromadb
import requests
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path.home() / ".emo_robot" / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

EMBED_MODEL = "nomic-embed-text"   # ~274MB, local via Ollama
OLLAMA_URL  = "http://localhost:11434"
TOP_K       = 4   # how many memories to retrieve per query


class RobotMemory:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(MEMORY_DIR))
        self.collection = self.client.get_or_create_collection(
            name="milo_memories",
            metadata={"hnsw:space": "cosine"},
        )
        print(f"🧠 Memory loaded: {self.collection.count()} memories stored.")

    def _embed(self, text: str) -> list[float]:
        """Get local embedding from Ollama nomic-embed-text."""
        try:
            r = requests.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": text},
                timeout=30,
            )
            r.raise_for_status()
            return r.json()["embedding"]
        except Exception as e:
            print(f"⚠️ Embedding failed: {e}")
            return []

    def save(self, user_text: str, bot_reply: str):
        """Store a conversation turn as a searchable memory."""
        if not user_text.strip():
            return

        # Build a clean memory string
        memory_text = f"User said: {user_text.strip()} | Milo replied: {bot_reply.strip()}"
        doc_id = hashlib.md5(f"{time.time()}{memory_text}".encode()).hexdigest()[:12]

        embedding = self._embed(memory_text)
        if not embedding:
            return  # Skip if embedding failed (nomic not pulled yet)

        self.collection.add(
            documents=[memory_text],
            embeddings=[embedding],
            ids=[doc_id],
            metadatas=[{
                "timestamp": datetime.now().isoformat(),
                "user": user_text.strip()[:200],
                "bot": bot_reply.strip()[:200],
            }],
        )
        print(f"💾 Memory saved (total: {self.collection.count()})")

    def recall(self, query: str, top_k: int = TOP_K) -> str:
        """Return relevant past memories as a formatted string for the prompt."""
        if self.collection.count() == 0 or not query.strip():
            return ""

        embedding = self._embed(query)
        if not embedding:
            return ""

        try:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=min(top_k, self.collection.count()),
            )
            docs = results.get("documents", [[]])[0]
            if not docs:
                return ""
            memory_block = "\n".join(f"- {d}" for d in docs)
            return memory_block
        except Exception as e:
            print(f"⚠️ Memory recall failed: {e}")
            return ""

    def count(self) -> int:
        return self.collection.count()


# --- Quick Test ---
if __name__ == "__main__":
    mem = RobotMemory()

    # Save a test memory
    mem.save("My name is Raskin and I love robotics.", "Nice to meet you, Raskin! Robotics is awesome!")
    mem.save("I have a cat named Pixel.", "Pixel sounds adorable!")
    mem.save("I like dark roast coffee in the mornings.", "A fellow coffee lover! Dark roast is bold.")

    # Retrieve relevant memories
    query = "What do you know about me?"
    recalled = mem.recall(query)
    print(f"\n🔍 Query: '{query}'")
    print(f"📚 Recalled memories:\n{recalled}")
