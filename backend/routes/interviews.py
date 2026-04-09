# backend/routes/interviews.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict
import logging

from backend.database import get_db
from backend.auth import get_current_user
from backend.services.interview_submission_service import InterviewSubmissionService
from backend.db_models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/interviews", tags=["interviews"])


@router.post("/submit")
async def submit_interview(
    payload: Dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    User submits their interview experience.
    
    Payload:
    {
        "company": "Google",
        "role": "Senior Software Engineer",
        "questions": [
            {"question": "Design a distributed cache", "answer": "..."},
            ...
        ],
        "outcome": "offer", // offer, rejected, pending
        "difficulty": 4
    }
    """
    try:
        service = InterviewSubmissionService(db)
        result = await service.submit_interview_experience(
            user_id=current_user.id,
            company=payload.get("company"),
            role=payload.get("role"),
            questions=payload.get("questions", []),
            outcome=payload.get("outcome", "pending"),
            difficulty=payload.get("difficulty", 3),
        )
        return {
            "status": "success",
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Interview submission error: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit interview")


@router.get("/{company}")
async def get_company_questions(
    company: str,
    role: str = None,
    limit: int = 15,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get verified interview questions for a company.
    
    Query params:
    - company: Company name (e.g., Google)
    - role: Optional role filter
    - limit: Max results (default 15)
    """
    try:
        service = InterviewSubmissionService(db)
        questions = await service.get_company_interview_questions(
            company=company,
            role=role,
            limit=limit,
        )
        return {
            "status": "success",
            "company": company,
            "role": role,
            "questions": questions,
        }
    except Exception as e:
        logger.error(f"Error fetching company questions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch questions")


@router.get("/user/history")
async def get_submission_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get current user's interview submission history and rewards.
    """
    try:
        service = InterviewSubmissionService(db)
        history = await service.get_user_submission_history(user_id=current_user.id)
        return {
            "status": "success",
            "data": history,
        }
    except Exception as e:
        logger.error(f"Error fetching submission history: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch history")


@router.post("/{submission_id}/rate")
async def rate_question(
    submission_id: str,
    payload: Dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Rate a question's helpfulness (community feedback).
    
    Payload:
    {
        "question_index": 0,
        "helpful": true,
        "rating": 5
    }
    """
    try:
        # TODO: Implement rating logic in InterviewSubmissionService
        return {
            "status": "success",
            "message": "Rating recorded",
        }
    except Exception as e:
        logger.error(f"Error rating question: {e}")
        raise HTTPException(status_code=500, detail="Failed to rate question")


@router.post("/{submission_id}/approve")
async def approve_submission(
    submission_id: str,
    payload: Dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Admin endpoint: Approve a submission.
    Only accessible by admin users.
    
    Payload:
    {
        "approved": true,
        "reviewer_notes": "Quality content"
    }
    """
    # Check if admin
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        service = InterviewSubmissionService(db)
        result = await service.review_submission(
            submission_id=submission_id,
            approved=payload.get("approved", False),
            reviewer_notes=payload.get("reviewer_notes"),
            admin_user_id=current_user.id,
        )
        return {
            "status": "success",
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error approving submission: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve submission")
