import json
import os
import pathlib
from app.core.config import get_settings
from app.core.embedding_factory import build_embeddings
from app.repositories.faiss_vector_store_repository import FaissVectorStoreRepository
from langchain_core.documents import Document

def main():
    settings = get_settings()
    print(f"Embeddings Model: {settings.embeddings_model}")
    print(f"Local Embedding Model: {settings.local_embedding_model}")
    
    embeddings = build_embeddings(settings)
    print(f"Using Embeddings: {type(embeddings)}")

    source_file = "data/faiss_backups/backup_20260518T055825Z/documents.json"
    print(f"Loading documents from {source_file}...")
    with open(source_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    documents = [Document(page_content=d["page_content"], metadata=d["metadata"]) for d in data]
    print(f"Loaded {len(documents)} documents.")

    faiss_dir = pathlib.Path("data/faiss_index")
    repo = FaissVectorStoreRepository(faiss_dir, embeddings)
    print(f"Clearing repository at {faiss_dir}...")
    repo.clear()

    print("Adding documents...")
    batch_size = 250
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        repo.add_documents(batch)
        print(f"Indexed {min(i + batch_size, len(documents))}/{len(documents)} documents...")

    print("Saving repository...")
    repo.save()
    
    final_count = repo.get_document_count()
    print(f"Final document count: {final_count}")

if __name__ == "__main__":
    main()
