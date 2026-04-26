import os


# Keep tests isolated from runtime .env.
os.environ.setdefault("PG_HOST", "localhost")
os.environ.setdefault("PG_PORT", "5432")
os.environ.setdefault("PG_DATABASE", "aichatbox")
os.environ.setdefault("PG_USER", "aichatbox")
os.environ.setdefault("PG_PASSWORD", "aichatbox")
os.environ.setdefault("LOCAL_SEMANTIC_EMBEDDINGS", "false")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("GOOGLE_API_KEY", "")
os.environ.setdefault("GROQ_API_KEY", "")
