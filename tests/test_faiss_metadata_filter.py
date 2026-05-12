from app.repositories.faiss_vector_store_repository import FaissVectorStoreRepository


def test_match_metadata_filter_extension_matches_dot_and_no_dot() -> None:
    metadata = {"extension": ".docx", "owner": "alice"}

    assert FaissVectorStoreRepository._match_metadata_filter(
        metadata,
        {"extension": "docx"},
    )
    assert FaissVectorStoreRepository._match_metadata_filter(
        metadata,
        {"extension": ".docx"},
    )
    assert FaissVectorStoreRepository._match_metadata_filter(
        metadata,
        {"extension": ["pdf", "docx"]},
    )


def test_match_metadata_filter_keeps_exact_match_for_non_extension_keys() -> None:
    metadata = {"extension": ".pdf", "owner": "workspace-user", "chat_id": "chat-1"}

    assert FaissVectorStoreRepository._match_metadata_filter(
        metadata,
        {"owner": "workspace-user", "chat_id": "chat-1"},
    )
    assert not FaissVectorStoreRepository._match_metadata_filter(
        metadata,
        {"owner": "another-user"},
    )
