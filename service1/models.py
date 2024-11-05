from datetime import datetime
from sqlmodel import SQLModel, Field
from typing import Optional


class PDF(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    filename: str
    s3_url: str
    summary: Optional[str] = Field(default=None)
    upload_date: datetime = Field(default_factory=datetime.utcnow)
    