from __future__ import annotations

import logging

import requests

_log = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when the Ollama embedding request fails."""


class OllamaEmbedder:
    """Embed text via Ollama's /api/embeddings endpoint using direct HTTP."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    def embed(self, text: str) -> list[float]:
        """Return a 768-dim embedding vector for *text*.

        Raises EmbeddingError on any network or API failure.
        """
        url = f"{self._base_url}/api/embeddings"
        try:
            response = requests.post(
                url,
                json={"model": self._model, "prompt": text},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise EmbeddingError(f"Ollama embedding request failed: {exc}") from exc
        except Exception as exc:
            raise EmbeddingError(f"Unexpected error during embedding: {exc}") from exc

        embedding = data.get("embedding")
        if not isinstance(embedding, list):
            raise EmbeddingError(
                f"Unexpected response shape from Ollama: {list(data.keys())}"
            )
        return embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts sequentially (Ollama has no batch endpoint)."""
        return [self.embed(text) for text in texts]
