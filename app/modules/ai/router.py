from fastapi import APIRouter, Depends

from app.common.dependencies import get_current_user
from app.modules.ai.dependencies import get_gemini_rag_service
from app.modules.ai.rag_service import GeminiRAGService
from app.modules.ai.schemas import RAGQuestionRequest, RAGQuestionResponse, RAGSourceResponse
from app.modules.users.models import User


router = APIRouter(prefix="/ai", tags=["knowledge base"])


@router.post(
    "/ask",
    response_model=RAGQuestionResponse,
    summary="Answer a plain-text question from the knowledge base",
    description="Embeds the question, retrieves ChromaDB context, and answers with Gemini.",
)
async def ask_knowledge_base(
    payload: RAGQuestionRequest,
    _: User = Depends(get_current_user),
    rag_service: GeminiRAGService = Depends(get_gemini_rag_service),
) -> RAGQuestionResponse:
    result = await rag_service.answer_question(payload.question)
    return RAGQuestionResponse(
        answer=result.answer,
        sources=[RAGSourceResponse(**source.__dict__) for source in result.sources],
    )
