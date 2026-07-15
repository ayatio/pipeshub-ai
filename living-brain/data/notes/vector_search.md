# Vector search and embeddings

An embedding maps text to a point in high-dimensional space where semantic
similarity becomes geometric closeness. Similar meanings land near each other.

Cosine similarity measures the angle between two embedding vectors. Values near
1 mean the texts are semantically close; values near 0 mean unrelated.

pgvector adds a native vector type to Postgres and an approximate-nearest-
neighbour index, so semantic search runs inside the database.

Retrieval-augmented generation feeds the nearest memories to a language model
as context, grounding its answer in your own notes rather than its training.
