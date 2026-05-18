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


def test_tokenize_keywords_supports_multilingual_terms() -> None:
    tokens = FaissVectorStoreRepository._tokenize_keywords(
        "Điều khoản thanh toán 支払い条件 hợp đồng"
    )

    assert "điều" in tokens
    assert "khoản" in tokens
    assert "thanh" in tokens
    assert "toán" in tokens
    assert "支払い条件" in tokens


def test_tokenize_keywords_keeps_identifier_like_tokens() -> None:
    tokens = FaissVectorStoreRepository._tokenize_keywords(
        "Contact: support-team@example.com order_id INV-2025-09"
    )

    assert "support-team@example.com" in tokens
    assert "order_id" in tokens
    assert "inv-2025-09" in tokens
