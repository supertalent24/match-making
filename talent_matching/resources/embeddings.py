"""Mock embedding resource for development and testing.

This resource simulates embedding generation without making actual API calls.
It returns random vectors matching OpenAI's text-embedding-3-large dimensions.
"""

import hashlib
import random
from typing import Any

from dagster import ConfigurableResource
from pydantic import Field


class MockEmbeddingResource(ConfigurableResource):
    """Mock embedding resource that generates deterministic random vectors.
    
    In production, this would be replaced with an actual OpenAI embedding resource
    or a local sentence-transformers model.
    
    The mock generates deterministic vectors based on input text hash,
    ensuring the same input always produces the same output (useful for testing).
    """

    model_version: str = Field(
        default="mock-embedding-v1",
        description="Version identifier for the mock embedding model",
    )
    dimensions: int = Field(
        default=1536,
        description="Vector dimensions (1536 matches OpenAI text-embedding-3-large)",
    )
    deterministic: bool = Field(
        default=True,
        description="If True, same input always produces same output",
    )

    def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text.
        
        Args:
            text: Input text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        if self.deterministic:
            # Use text hash as seed for reproducible results
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            seed = int(text_hash[:8], 16)
            rng = random.Random(seed)
        else:
            rng = random.Random()

        # Generate random vector
        vector = [rng.gauss(0, 1) for _ in range(self.dimensions)]
        
        # Normalize to unit length (standard for cosine similarity)
        magnitude = sum(x * x for x in vector) ** 0.5
        normalized = [x / magnitude for x in vector]
        
        return normalized

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.
        
        Args:
            texts: List of input texts to embed
            
        Returns:
            List of embedding vectors
        """
        return [self.embed(text) for text in texts]

    def embed_with_metadata(self, text: str, vector_type: str) -> dict[str, Any]:
        """Generate an embedding with associated metadata.
        
        Args:
            text: Input text to embed
            vector_type: Type of vector (e.g., 'position', 'experience', 'domain_context')
            
        Returns:
            Dictionary containing vector and metadata
        """
        return {
            "vector": self.embed(text),
            "vector_type": vector_type,
            "model_version": self.model_version,
            "dimensions": self.dimensions,
            "text_length": len(text),
        }
