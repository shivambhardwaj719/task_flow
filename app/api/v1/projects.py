import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.task import Task
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectOut, PaginatedProjects
from app.core.auth import get_current_user

router = APIRouter(prefix="/projects", tags=["Projects"])


def get_user_project(project_id: int, user_id: int, db: Session) -> Project:
    """Helper to retrieve a project and enforce authorization boundaries.
    
    Returns 404 if project does not exist.
    Returns 403 Forbidden if project exists but belongs to a different user.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found."
        )
    if project.owner_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access or modify this project."
        )
    return project


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new project owned by the current authenticated user."""
    project = Project(
        name=project_in.name,
        description=project_in.description,
        owner_id=current_user.id
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    project.task_count = 0
    return project


@router.get("", response_model=PaginatedProjects)
def list_projects(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all projects owned by the authenticated user with pagination.
    
    Users cannot view projects belonging to other users.
    """
    query = db.query(Project).filter(Project.owner_id == current_user.id)
    total = query.count()
    
    offset = (page - 1) * page_size
    projects = (
        query.order_by(Project.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    # Attach task counts
    for p in projects:
        p.task_count = db.query(func.count(Task.id)).filter(Task.project_id == p.id).scalar() or 0

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return PaginatedProjects(
        items=projects,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve details for a specific project.
    
    Enforces that only the project owner can view details.
    """
    project = get_user_project(project_id, current_user.id, db)
    project.task_count = db.query(func.count(Task.id)).filter(Task.project_id == project.id).scalar() or 0
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    project_in: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a project's name or description.
    
    Enforces authorization: only the project owner can update it.
    """
    project = get_user_project(project_id, current_user.id, db)

    if project_in.name is not None:
        project.name = project_in.name
    if project_in.description is not None:
        project.description = project_in.description

    db.commit()
    db.refresh(project)
    project.task_count = db.query(func.count(Task.id)).filter(Task.project_id == project.id).scalar() or 0
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a project and all associated tasks.
    
    Enforces authorization: only the project owner can delete it.
    """
    project = get_user_project(project_id, current_user.id, db)
    db.delete(project)
    db.commit()
    return None
