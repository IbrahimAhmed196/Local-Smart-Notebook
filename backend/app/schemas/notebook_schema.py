from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

# 1. Schema لإنشاء نوت بوك جديد (اللي المستخدم بيبعتهم في الـ Body)
class NotebookCreate(BaseModel):
    title: str
    description: Optional[str] = None

# 2. Schema للرد (Response) اللي بيترجع للمستخدم بعد ما العملية تنجح
class NotebookResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True  # عشان يقرأ البيانات من نماذج SQLAlchemy مباشرة