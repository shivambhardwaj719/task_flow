from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150, description="Project name")
    description: Optional[str] = Field(None, max_length=1000, description="Project description")


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=1000)


class ProjectOut(ProjectBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime
    task_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class PaginatedProjects(BaseModel):
    items: List[ProjectOut]
    total: int
    page: int
    page_size: int
    total_pages: int
