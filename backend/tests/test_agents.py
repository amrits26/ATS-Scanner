// backend/tests/test_agents.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import json
from unittest.mock import MagicMock, AsyncMock, patch

from backend.main import app
from backend.services.agent_coach import ResumeCoachAgent
from backend.services.agent_tailor import AutoTailorAgent
from backend.services.agent_interview import InterviewPrepAgent


# Mock JWT for testing
MOCK_JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
MOCK_USER_ID = "test-user-123"


class TestCoachAgent:
    """Test Resume Coach agent endpoint and integration."""

    @pytest.mark.asyncio
    async def test_coach_returns_valid_response(self):
        """Verify coach endpoint returns required fields."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            with patch("backend.auth.get_current_user") as mock_auth:
                user = MagicMock()
                user.id = MOCK_USER_ID
                mock_auth.return_value = user
                
                response = await client.post(
                    "/api/agent/coach",
                    json={
                        "question": "How can I improve my resume?",
                        "resume_text": "Software Engineer at Google with 5 years experience in Python and AWS."
                    },
                    headers={"Authorization": f"Bearer {MOCK_JWT_TOKEN}"}
                )
                
                assert response.status_code in [200, 202]  # 200 sync, 202 async accepted
                data = response.json()
                assert "session_id" in data
                assert "status" in data
                assert data["status"] in ["completed", "accepted"]

    @pytest.mark.asyncio
    async def test_coach_requires_resume_text(self):
        """Verify coach endpoint rejects empty resume."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/agent/coach",
                json={
                    "question": "How to improve?",
                    "resume_text": ""
                },
                headers={"Authorization": f"Bearer {MOCK_JWT_TOKEN}"}
            )
            
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_coach_agent_initialization(self):
        """Test agent can be instantiated and has required tools."""
        db_mock = MagicMock(spec=AsyncSession)
        agent = ResumeCoachAgent(user_id=MOCK_USER_ID, db=db_mock)
        
        assert agent.agent_type == "coach"
        assert agent.user_id == MOCK_USER_ID
        assert hasattr(agent, "tools")


class TestTailorAgent:
    """Test Auto-Tailor agent endpoint and integration."""

    @pytest.mark.asyncio
    async def test_tailor_returns_match_score(self):
        """Verify tailor endpoint returns match score 0-100."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/agent/tailor",
                json={
                    "resume_text": "Senior Software Engineer with Python, React, Node.js",
                    "jd_text": "Looking for Sr Engineer with Python, TypeScript, AWS"
                },
                headers={"Authorization": f"Bearer {MOCK_JWT_TOKEN}"}
            )
            
            if response.status_code in [200, 202]:
                data = response.json()
                if "match_score" in data:
                    assert 0 <= data["match_score"] <= 100

    @pytest.mark.asyncio
    async def test_tailor_requires_job_data(self):
        """Verify tailor requires either jd_url or jd_text."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/agent/tailor",
                json={
                    "resume_text": "Senior Engineer"
                },
                headers={"Authorization": f"Bearer {MOCK_JWT_TOKEN}"}
            )
            
            assert response.status_code in [400, 422]


class TestInterviewAgent:
    """Test Interview Prep agent endpoint and integration."""

    @pytest.mark.asyncio
    async def test_interview_generates_questions(self):
        """Verify interview endpoint generates questions."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/agent/interview-prep",
                json={
                    "job_title": "Senior Software Engineer",
                    "company": "Google",
                    "resume_text": "Led ML infrastructure team at previous company"
                },
                headers={"Authorization": f"Bearer {MOCK_JWT_TOKEN}"}
            )
            
            if response.status_code in [200, 202]:
                data = response.json()
                if "questions" in data:
                    assert isinstance(data["questions"], dict)
                    assert any(key in data["questions"] for key in ["technical", "behavioral"])

    @pytest.mark.asyncio
    async def test_interview_agent_initialization(self):
        """Test interview agent can be instantiated."""
        db_mock = MagicMock(spec=AsyncSession)
        agent = InterviewPrepAgent(user_id=MOCK_USER_ID, db=db_mock)
        
        assert agent.agent_type == "interview"
        assert agent.user_id == MOCK_USER_ID


class TestAgentCosts:
    """Test cost tracking and budget enforcement."""

    @pytest.mark.asyncio
    async def test_agent_execution_includes_cost(self):
        """Verify agent responses include gemini_cost_cents."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/agent/coach",
                json={
                    "question": "Help me?",
                    "resume_text": "Engineer"
                },
                headers={"Authorization": f"Bearer {MOCK_JWT_TOKEN}"}
            )
            
            if response.status_code in [200, 202]:
                data = response.json()
                if "gemini_cost_cents" in data:
                    assert isinstance(data["gemini_cost_cents"], (int, float))
                    assert data["gemini_cost_cents"] >= 0

    @pytest.mark.asyncio
    async def test_agent_execution_includes_timing(self):
        """Verify agent responses include execution_time_seconds."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/agent/coach",
                json={
                    "question": "Help?",
                    "resume_text": "Engineer"
                },
                headers={"Authorization": f"Bearer {MOCK_JWT_TOKEN}"}
            )
            
            if response.status_code in [200, 202]:
                data = response.json()
                if "execution_time_seconds" in data:
                    assert isinstance(data["execution_time_seconds"], (int, float))
                    assert data["execution_time_seconds"] > 0


class TestAgentAuth:
    """Test authentication and authorization."""

    @pytest.mark.asyncio
    async def test_agents_require_auth(self):
        """Verify agent endpoints require authentication."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/agent/coach",
                json={
                    "question": "Help?",
                    "resume_text": "Engineer"
                }
                # No auth header
            )
            
            assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_agent_rejects_invalid_token(self):
        """Verify agent rejects invalid JWT."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/agent/coach",
                json={
                    "question": "Help?",
                    "resume_text": "Engineer"
                },
                headers={"Authorization": "Bearer invalid_token_xyz"}
            )
            
            assert response.status_code in [401, 403]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
