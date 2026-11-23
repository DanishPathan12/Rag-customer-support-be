import pytest

from app.core.config import Settings
from app.core.exceptions import AIResponseUnavailableError
from app.modules.ai.rag_service import GeminiRAGService, NO_ANSWER


def make_settings(**overrides) -> Settings:
    values = {
        "database_url": "sqlite://",
        "jwt_secret": "j" * 32,
        "otp_pepper": "p" * 32,
        "google_api_key": "google-api-key",
        "chroma_collection_name": "support-knowledge",
        "gemini_embedding_min_request_interval_seconds": 0,
    }
    values.update(overrides)
    return Settings(**values)


def test_question_is_embedded_retrieved_and_answered_from_context(monkeypatch) -> None:
    service = GeminiRAGService(make_settings())

    class FakeEmbeddings:
        def embed_query(self, question: str) -> list[float]:
            assert question == "When will my order arrive?"
            return [0.1, 0.2]

    class FakeCollection:
        def query(self, **kwargs) -> dict:
            assert kwargs["query_embeddings"] == [[0.1, 0.2]]
            assert kwargs["n_results"] == 4
            return {
                "documents": [["Orders arrive within three business days."]],
                "metadatas": [
                    [
                        {
                            "file_id": "file-123",
                            "filename": "shipping-policy.pdf",
                            "page": 2,
                            "chunk_index": 4,
                        }
                    ]
                ],
            }

    generated_prompts: list[str] = []
    monkeypatch.setattr(
        service.chroma_service,
        "_get_or_create_collection",
        lambda: FakeCollection(),
    )
    monkeypatch.setattr(
        service.chroma_service,
        "_create_embeddings",
        lambda task_type: FakeEmbeddings(),
    )
    monkeypatch.setattr(
        service,
        "_generate_answer",
        lambda prompt: generated_prompts.append(prompt) or "Your order arrives within three business days. [Source 1]",
    )

    result = service._answer_question("When will my order arrive?")

    assert result.answer == "Your order arrives within three business days. [Source 1]"
    assert result.sources[0].filename == "shipping-policy.pdf"
    assert result.sources[0].page == 2
    assert "Orders arrive within three business days." in generated_prompts[0]


def test_question_with_no_retrieved_chunks_does_not_call_gemini(monkeypatch) -> None:
    service = GeminiRAGService(make_settings())

    class FakeEmbeddings:
        def embed_query(self, question: str) -> list[float]:
            return [0.1, 0.2]

    class FakeCollection:
        def query(self, **kwargs) -> dict:
            return {"documents": [[]], "metadatas": [[]]}

    monkeypatch.setattr(
        service.chroma_service,
        "_get_or_create_collection",
        lambda: FakeCollection(),
    )
    monkeypatch.setattr(
        service.chroma_service,
        "_create_embeddings",
        lambda task_type: FakeEmbeddings(),
    )
    monkeypatch.setattr(
        service,
        "_generate_answer",
        lambda prompt: (_ for _ in ()).throw(AssertionError("Gemini should not be called")),
    )

    result = service._answer_question("What is the return policy?")

    assert result.answer == NO_ANSWER
    assert result.sources == []


def test_answer_generation_falls_back_when_the_primary_model_is_unavailable(
    monkeypatch,
) -> None:
    service = GeminiRAGService(
        make_settings(
            gemini_response_model="gemini-primary",
            gemini_response_fallback_model="gemini-fallback",
            gemini_response_max_retries=0,
        )
    )
    attempted_models: list[str] = []

    def generate(model: str, prompt: str) -> str:
        attempted_models.append(model)
        if model == "gemini-primary":
            raise RuntimeError("503 UNAVAILABLE. Model is experiencing high demand.")
        return "Grounded answer. [Source 1]"

    monkeypatch.setattr(service, "_generate_with_model", generate)

    assert service._generate_answer("Context") == "Grounded answer. [Source 1]"
    assert attempted_models == ["gemini-primary", "gemini-fallback"]


def test_answer_generation_returns_service_unavailable_after_all_models_fail(
    monkeypatch,
) -> None:
    service = GeminiRAGService(
        make_settings(
            gemini_response_model="gemini-primary",
            gemini_response_fallback_model="gemini-fallback",
            gemini_response_max_retries=0,
        )
    )
    monkeypatch.setattr(
        service,
        "_generate_with_model",
        lambda model, prompt: (_ for _ in ()).throw(
            RuntimeError("503 UNAVAILABLE. Model is experiencing high demand.")
        ),
    )

    with pytest.raises(AIResponseUnavailableError) as error:
        service._generate_answer("Context")

    assert error.value.retry_after_seconds == 1
