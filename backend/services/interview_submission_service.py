# backend/services/interview_submission_service.py
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

logger = logging.getLogger(__name__)

class InterviewSubmissionService:
    """
    Manages user-submitted interview experiences.
    Users contribute real interview questions → earn rewards → public Q&A bank grows
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_interview_experience(
        self,
        user_id: str,
        company: str,
        role: str,
        questions: List[Dict[str, str]],  # [{"question": "...", "answer": "..."}]
        outcome: str,  # "offer", "rejected", "pending"
        difficulty: int = 3,
    ) -> Dict:
        """
        User submits their real interview experience.
        Returns submission_id and reward info.
        
        Args:
            user_id: UUID of submitting user
            company: Company name (e.g., "Google")
            role: Job title (e.g., "Senior Software Engineer")
            questions: List of {question, answer} dicts
            outcome: Interview result (offer/rejected/pending)
            difficulty: 1-5 scale
            
        Returns:
            {submission_id, reward_type, reward_amount, message}
        """
        # Validate input
        if not company or not role or not questions:
            raise ValueError("Company, role, and questions are required")
        
        if len(questions) < 3:
            raise ValueError("Please submit at least 3 interview questions")
        
        # Import here to avoid circular dependency
        from backend.db_models import UserInterviewSubmission, UserReward
        
        submission = UserInterviewSubmission(
            id=str(uuid.uuid4()),
            user_id=user_id,
            company=company,
            role=role,
            questions=questions,
            outcome=outcome,
            difficulty=difficulty,
            status="pending_review",
            created_at=datetime.utcnow(),
        )
        self.db.add(submission)
        await self.db.commit()
        await self.db.refresh(submission)

        logger.info(f"Interview submission {submission.id} from user {user_id} for {company}/{role}")

        # Create reward (pending approval)
        reward = UserReward(
            id=str(uuid.uuid4()),
            user_id=user_id,
            submission_id=str(submission.id),
            reward_type="pending",
            amount_cents=0,
            status="pending_approval",
            created_at=datetime.utcnow(),
        )
        self.db.add(reward)
        await self.db.commit()

        return {
            "submission_id": str(submission.id),
            "status": "pending_review",
            "message": "Thank you! Your submission is being reviewed. You'll earn a reward once approved.",
            "reward_type": "pending",
        }

    async def review_submission(
        self,
        submission_id: str,
        approved: bool,
        reviewer_notes: str = None,
        admin_user_id: str = None,
    ) -> Dict:
        """
        Admin approves or rejects a submission.
        If approved, add questions to public bank + reward user.
        """
        from backend.db_models import (
            UserInterviewSubmission, 
            InterviewQuestionsBank, 
            UserReward
        )

        # Fetch submission
        stmt = select(UserInterviewSubmission).where(
            UserInterviewSubmission.id == submission_id
        )
        result = await self.db.execute(stmt)
        submission = result.scalar_one_or_none()
        
        if not submission:
            raise ValueError("Submission not found")

        submission.status = "approved" if approved else "rejected"
        submission.reviewed_at = datetime.utcnow()
        submission.reviewer_notes = reviewer_notes
        submission.reviewed_by = admin_user_id

        if approved:
            # Add each question to the public bank
            for i, q in enumerate(submission.questions):
                bank_entry = InterviewQuestionsBank(
                    id=str(uuid.uuid4()),
                    company=submission.company,
                    role=submission.role,
                    question=q.get("question", ""),
                    answer_example=q.get("answer", ""),
                    difficulty=submission.difficulty,
                    source="user_submitted",
                    verified=True,
                    submitted_by=submission.user_id,
                    created_at=datetime.utcnow(),
                )
                self.db.add(bank_entry)

            # Reward user: $5 credit
            reward_amount_cents = 500
            
            # Update reward record
            reward_stmt = select(UserReward).where(
                and_(
                    UserReward.submit_id == submission_id,
                    UserReward.status == "pending_approval"
                )
            )
            reward_result = await self.db.execute(reward_stmt)
            reward = reward_result.scalar_one_or_none()
            
            if reward:
                reward.reward_type = "stripe_credit"
                reward.amount_cents = reward_amount_cents
                reward.status = "claimed"
                reward.claimed_at = datetime.utcnow()

            logger.info(
                f"Submission {submission_id} approved. "
                f"User {submission.user_id} rewarded ${reward_amount_cents/100:.2f}"
            )

        await self.db.commit()
        
        return {
            "submission_id": submission_id,
            "status": "approved" if approved else "rejected",
            "message": "Submission processed",
        }

    async def get_company_interview_questions(
        self,
        company: str,
        role: Optional[str] = None,
        limit: int = 15,
    ) -> List[Dict]:
        """
        Fetch verified interview questions for a company.
        
        Args:
            company: Company name filter
            role: Optional role filter
            limit: Max questions to return
            
        Returns:
            List of {question, answer_example, difficulty, role}
        """
        from backend.db_models import InterviewQuestionsBank

        query = select(InterviewQuestionsBank).where(
            and_(
                InterviewQuestionsBank.company == company,
                InterviewQuestionsBank.verified == True,
            )
        )
        
        if role:
            query = query.where(InterviewQuestionsBank.role == role)

        query = query.limit(limit)
        result = await self.db.execute(query)
        questions = result.scalars().all()

        return [
            {
                "question": q.question,
                "answer_example": q.answer_example,
                "difficulty": q.difficulty,
                "role": q.role,
                "submitted_by": q.submitted_by,
            }
            for q in questions
        ]

    async def get_user_submission_history(self, user_id: str) -> Dict:
        """Get submission history and rewards for a user."""
        from backend.db_models import UserInterviewSubmission, UserReward

        stmt = select(UserInterviewSubmission).where(
            UserInterviewSubmission.user_id == user_id
        ).order_by(UserInterviewSubmission.created_at.desc())
        
        result = await self.db.execute(stmt)
        submissions = result.scalars().all()

        reward_stmt = select(UserReward).where(
            UserReward.user_id == user_id
        ).order_by(UserReward.created_at.desc())
        
        reward_result = await self.db.execute(reward_stmt)
        rewards = reward_result.scalars().all()

        total_earned_cents = sum(r.amount_cents for r in rewards if r.status == "claimed")

        return {
            "submissions": [
                {
                    "id": str(s.id),
                    "company": s.company,
                    "role": s.role,
                    "status": s.status,
                    "outcome": s.outcome,
                    "created_at": s.created_at.isoformat(),
                    "question_count": len(s.questions),
                }
                for s in submissions
            ],
            "rewards": [
                {
                    "id": str(r.id),
                    "type": r.reward_type,
                    "amount_cents": r.amount_cents,
                    "status": r.status,
                    "claimed_at": r.claimed_at.isoformat() if r.claimed_at else None,
                }
                for r in rewards
            ],
            "total_earned_cents": total_earned_cents,
            "total_earned_dollars": total_earned_cents / 100,
        }
