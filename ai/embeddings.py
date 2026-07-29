"""
Embeddings module — Vector storage and similarity search.

Responsibilities:
1. Load embedding model once (singleton, expensive operation)
2. Convert text into vectors
3. Store vectors in ChromaDB with candidate/resume metadata
4. Query for similar resumes (for duplicate detection)
5. Return ranked similarity matches

Input: Text blocks (resume text, skills, descriptions)
Output: For storage: nothing (persists to ChromaDB)
        For querying: List[(candidate_id, resume_id, similarity_score)]

This module is pure vector plumbing — no fraud logic.
Same philosophy as database/db.py in Phase 1.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingsClient:
    """
    Singleton for embedding model and ChromaDB vector store.
    """
    
    def __init__(self):
        """
        Initialize embedding model and ChromaDB.
        Only happens once per application lifetime.
        """
        # Ensure storage path exists
        self.storage_path = Path(settings.CHROMA_DB_PATH)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"[Embeddings] Loading model: {settings.EMBEDDING_MODEL}")
        
        # Load embedding model (expensive — done once)
        try:
            self.model = SentenceTransformer(settings.EMBEDDING_MODEL)
            logger.info(f"[Embeddings] Model loaded successfully")
        except Exception as e:
            logger.error(f"[Embeddings] Failed to load model: {str(e)}")
            raise
        
        # Initialize ChromaDB
        logger.info(f"[Embeddings] Initializing ChromaDB at {self.storage_path}")
        try:
            chroma_settings = Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=str(self.storage_path),
                anonymized_telemetry=False,
            )
            self.client = chromadb.Client(chroma_settings)
            
            # Get or create collection for resume embeddings
            self.collection = self.client.get_or_create_collection(
                name="resume_embeddings",
                metadata={"hnsw:space": "cosine"}  # Cosine similarity
            )
            logger.info(f"[Embeddings] ChromaDB collection ready")
        except Exception as e:
            logger.error(f"[Embeddings] Failed to initialize ChromaDB: {str(e)}")
            raise
    
    def embed_text(self, text: str) -> List[float]:
        """
        Convert text to embedding vector.
        
        Args:
            text: Text to embed
            
        Returns:
            Vector as list of floats
        """
        if not text or not text.strip():
            logger.warning("[Embeddings] Attempted to embed empty text")
            return [0.0] * self.model.get_sentence_embedding_dimension()
        
        try:
            # Truncate if too long (embeddings can't handle arbitrarily long text)
            max_tokens = 512
            text_truncated = text[:max_tokens * 4]  # Rough approximation
            
            embedding = self.model.encode(text_truncated, convert_to_tensor=False)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"[Embeddings] Failed to embed text: {str(e)}")
            raise
    
    def store_resume_embedding(
        self,
        resume_id: int,
        candidate_id: int,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Store resume embedding in ChromaDB.
        
        Args:
            resume_id: Resume ID from database
            candidate_id: Candidate ID from database
            text: Full resume text to embed
            metadata: Optional additional metadata (filename, upload_date, etc.)
        """
        try:
            # Embed text
            embedding = self.embed_text(text)
            
            # Prepare metadata
            doc_metadata = {
                "resume_id": str(resume_id),
                "candidate_id": str(candidate_id),
            }
            if metadata:
                doc_metadata.update(metadata)
            
            # Store in ChromaDB
            self.collection.add(
                ids=[f"resume_{resume_id}"],
                embeddings=[embedding],
                documents=[text[:1000]],  # Store first 1000 chars as doc preview
                metadatas=[doc_metadata],
            )
            
            logger.debug(f"[Embeddings] Stored embedding for resume {resume_id}")
        except Exception as e:
            logger.error(f"[Embeddings] Failed to store embedding for resume {resume_id}: {str(e)}")
            raise
    
    def query_similar_resumes(
        self,
        text: str,
        top_k: int = 5,
        min_similarity: float = 0.85,
    ) -> List[Tuple[int, int, float]]:
        """
        Find similar resumes in the store.
        
        Args:
            text: Resume text to query
            top_k: Return top K results
            min_similarity: Only return matches above this threshold
            
        Returns:
            List of (candidate_id, resume_id, similarity_score)
        """
        try:
            # Embed query text
            query_embedding = self.embed_text(text)
            
            # Query ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["metadatas", "distances"],
            )
            
            # Convert distances to similarity scores
            # ChromaDB returns distances, convert to similarity (1 - distance for cosine)
            matches = []
            if results["ids"] and len(results["ids"]) > 0:
                for i, doc_id in enumerate(results["ids"][0]):
                    distance = results["distances"][0][i]
                    similarity = 1 - distance  # Convert distance to similarity
                    
                    if similarity >= min_similarity:
                        metadata = results["metadatas"][0][i]
                        candidate_id = int(metadata["candidate_id"])
                        resume_id = int(metadata["resume_id"])
                        matches.append((candidate_id, resume_id, similarity))
            
            logger.debug(f"[Embeddings] Query returned {len(matches)} matches above {min_similarity} similarity")
            return matches
        except Exception as e:
            logger.error(f"[Embeddings] Query failed: {str(e)}")
            raise
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get stats about the embedding collection.
        
        Returns:
            Dict with collection size, etc.
        """
        try:
            count = self.collection.count()
            return {
                "collection_name": "resume_embeddings",
                "document_count": count,
                "embedding_dimension": self.model.get_sentence_embedding_dimension(),
            }
        except Exception as e:
            logger.error(f"[Embeddings] Failed to get stats: {str(e)}")
            return {"error": str(e)}
    
    def delete_resume_embedding(self, resume_id: int) -> None:
        """
        Delete a resume embedding from the store.
        
        Args:
            resume_id: Resume ID to delete
        """
        try:
            self.collection.delete(ids=[f"resume_{resume_id}"])
            logger.debug(f"[Embeddings] Deleted embedding for resume {resume_id}")
        except Exception as e:
            logger.error(f"[Embeddings] Failed to delete embedding for resume {resume_id}: {str(e)}")
            raise


# Singleton instance
try:
    embeddings_client = EmbeddingsClient()
except Exception as e:
    logger.error(f"[Embeddings] Failed to initialize singleton: {str(e)}")
    embeddings_client = None
