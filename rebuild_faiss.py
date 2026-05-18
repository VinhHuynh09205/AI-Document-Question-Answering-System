import os
import json
import shutil
from langchain_core.documents import Document
from app.core.config import get_settings
from app.core.embedding_factory import build_embeddings
from app.repositories.faiss_vector_store_repository import FaissVectorStoreRepository

def rebuild():
    settings = get_settings()
    # Try multiple attribute names for the model name
    try:
        model_name = settings.embeddings_model
    except AttributeError:
        try:
            model_name = settings.EMBEDDINGS_MODEL
        except AttributeError:
             model_name = "unknown"
             
    print(f"Active Model: {model_name}")
    
    backup_path = "data/faiss_backups/20260518T061239Z_pre_bge_m3_reindex/documents.json"
    temp_dir = "data/faiss_index_rebuild_bge_m3"
    target_dir = "data/faiss_index"
    
    if not os.path.exists(backup_path):
        print(f"Error: Backup file {backup_path} not found.")
        return

    print(f"Loading documents from {backup_path}...")
    with open(backup_path, 'r', encoding='utf-8') as f:
        docs_data = json.load(f)
    
    documents = []
    for d in docs_data:
        content = d.get('page_content') or d.get('text')
        if content:
            documents.append(Document(page_content=content, metadata=d.get('metadata', {})))
            
    print(f"Loaded {len(documents)} documents.")

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)

    print("Building embeddings and creating FAISS index...")
    embeddings = build_embeddings()
    repo = FaissVectorStoreRepository(embeddings=embeddings, index_path=temp_dir)
    
    repo.add_documents(documents)
    
    if hasattr(repo, 'save'):
        repo.save()
    
    print(f"Index successfully built in {temp_dir}")
    
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    # Clear target directory before copying
    for filename in os.listdir(target_dir):
        file_path = os.path.join(target_dir, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)

    for filename in os.listdir(temp_dir):
        shutil.copy(os.path.join(temp_dir, filename), os.path.join(target_dir, filename))
    
    print(f"Replaced {target_dir} contents with rebuilt files.")
    print(f"Rebuild complete. Indexed {len(documents)} documents.")

if __name__ == "__main__":
    rebuild()
