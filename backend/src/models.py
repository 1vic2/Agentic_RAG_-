from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str
    conversation_id: str | None = None
    use_web: bool = False
    deep_mode: bool = False
    kb_id: str = ""  # 指定检索的知识库ID，为空则检索全部
    retry_retrieval: bool = False  # 实验性：短指代追问最多增加一次同库向量检索


class CreateKBRequest(BaseModel):
    name: str
    description: str = ""
