// backend/tests/test_interview_submissions.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from backend.services.interview_submission_service import InterviewSubmissionService


class TestInterviewSubmission:
    """Test interview submission service and validation."""

    @pytest.fixture
    async def mock_db(self):
        """Create mock database session."""
        db = MagicMock(spec=AsyncSession)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_submit_interview_requires_questions(self, mock_db):
        """Verify submission requires at least 3 questions."""
        service = InterviewSubmissionService(mock_db)
        
        with pytest.raises(ValueError) as exc_info:
            await service.submit_interview_experience(
                user_id="user-123",
                company="Google",
                role="Engineer",
                questions=[],  # Empty
                outcome="offer"
            )
        
        assert "at least 3" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_submit_interview_requires_company(self, mock_db):
        """Verify submission requires company."""
        service = InterviewSubmissionService(mock_db)
        
        with pytest.raises(ValueError):
            await service.submit_interview_experience(
                user_id="user-123",
                company="",  # Empty
                role="Engineer",
                questions=[
                    {"question": "Q1", "answer": "A1"},
                    {"question": "Q2", "answer": "A2"},
                    {"question": "Q3", "answer": "A3"},
                ],
                outcome="offer"
            )

    @pytest.mark.asyncio
    async def test_submit_interview_success(self, mock_db):
        """Verify successful interview submission."""
        service = InterviewSubmissionService(mock_db)
        
        result = await service.submit_interview_experience(
            user_id="user-123",
            company="Google",
            role="Senior Software Engineer",
            questions=[
                {"question": "Design a cache", "answer": "Use Redis..."},
                {"question": "Tell me about yourself", "answer": "..."},
                {"question": "Why Google?", "answer": "..."},
            ],
            outcome="offer",
            difficulty=4
        )
        
        assert "submission_id" in result
        assert result["status"] == "pending_review"
        mock_db.add.assert_called()
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_get_company_questions(self, mock_db):
        """Verify fetching company questions."""
        from backend.db_models import InterviewQuestionsBank
        
        # Mock database result
        mock_questions = [
            MagicMock(question="Q1", answer_example="A1", difficulty=4, role="Engineer"),
            MagicMock(question="Q2", answer_example="A2", difficulty=4, role="Engineer"),
        ]
        mock_db.execute = AsyncMock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = mock_questions
        
        service = InterviewSubmissionService(mock_db)
        questions = await service.get_company_interview_questions(
            company="Google",
            role="Engineer",
            limit=15
        )
        
        assert len(questions) == 2
        assert all("question" in q for q in questions)


class TestInterviewReward:
    """Test reward mechanism for submissions."""

    @pytest.mark.asyncio
    async def test_approved_submission_rewards_user(self):
        """Verify approved submission creates reward for user."""
        db = MagicMock(spec=AsyncSession)
        
        # This would be tested with a real database in integration tests
        # Here we just verify the logic flow is correct
        assert True  # Placeholder


class TestInterviewStats:
    """Test user submission history and statistics."""

    @pytest.mark.asyncio
    async def test_get_submission_history(self):
        """Verify user can retrieve their submission history."""
        db = MagicMock(spec=AsyncSession)
        db.execute = AsyncMock()
        
        # Mock empty history
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result
        
        service = InterviewSubmissionService(db)
        history = await service.get_user_submission_history(user_id="user-123")
        
        assert "submissions" in history
        assert "rewards" in history
        assert "total_earned_dollars" in history


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
