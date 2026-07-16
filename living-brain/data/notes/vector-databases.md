# Notes: vector databases and retrieval

Embeddings turn text into vectors so that semantically similar passages land
near each other in vector space. Retrieval then becomes a nearest-neighbour
search over those vectors.

For a small personal corpus a brute-force cosine scan is more than fast enough;
you only reach for an approximate index (HNSW, IVF) once you have hundreds of
thousands of chunks.

nomic-embed-text is a solid local embedding model that runs well under Ollama.
It produces 768-dimensional vectors and is a good default for offline setups.

Key decision: keep the storage simple. SQLite with embeddings stored as JSON is
enough to start, and it removes any external database dependency.
