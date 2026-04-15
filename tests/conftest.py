import os


# Keep tests isolated from runtime .env (which may use MySQL and semantic embeddings).
os.environ.setdefault("DATABASE_BACKEND", "sqlite")
os.environ.setdefault("LOCAL_SEMANTIC_EMBEDDINGS", "false")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("GOOGLE_API_KEY", "")
os.environ.setdefault("GROQ_API_KEY", "")
