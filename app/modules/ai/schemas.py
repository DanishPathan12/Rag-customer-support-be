from pydantic import BaseModel, Field, field_validator


class RAGQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question must not be blank.")
        return value


class RAGSourceResponse(BaseModel):
    file_id: str
    filename: str
    page: int | None
    chunk_index: int | None


class RAGQuestionResponse(BaseModel):
    answer: str
    sources: list[RAGSourceResponse]
