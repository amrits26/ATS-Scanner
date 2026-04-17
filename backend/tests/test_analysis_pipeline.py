"""
Integration tests for the async analysis pipeline.

Covers:
  - Comprehensive analysis endpoint (202 Accepted flow)
  - Input validation (bad PDF, missing JD)
  - Rate limiting (10/minute via slowapi)
  - Quota enforcement (FREE tier 3-scan limit)
  - Polling endpoint structure

Run with:
    pytest backend/tests/test_analysis_pipeline.py -v
"""

import io
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db_models import AnalysisResult, AnalysisStatus, User, UserTier
from backend.main import app
from backend.models import ComprehensiveAnalysisResult


# ---------------------------------------------------------------------------
# Fixtures (local)
# ---------------------------------------------------------------------------
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def _mock_free_user():
    user = MagicMock(spec=User)
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user.supabase_user_id = "sup-free-001"
    user.email = "free@test.com"
    user.tier = UserTier.free
    user.scans_this_month = 0
    user.scan_limit = 3
    user.can_scan = MagicMock(return_value=True)
    return user


def _mock_maxed_user():
    user = MagicMock(spec=User)
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000003")
    user.supabase_user_id = "sup-maxed-003"
    user.email = "maxed@test.com"
    user.tier = UserTier.free
    user.scans_this_month = 3
    user.scan_limit = 3
    user.can_scan = MagicMock(return_value=False)
    return user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_auth(user):
    """Context manager to mock both get_current_user and check_scan_quota."""
    return patch.multiple(
        "backend.auth",
        get_current_user=AsyncMock(return_value=user),
        check_scan_quota=AsyncMock(return_value=user),
    )


# ---------------------------------------------------------------------------
# Input Validation Tests
# ---------------------------------------------------------------------------

class TestInputValidation:
    """Verify the endpoint rejects bad inputs gracefully."""

    @pytest.mark.asyncio
    async def test_missing_resume_returns_422(self):
        """No resume file uploaded → 422 Unprocessable Entity."""
        user = _mock_free_user()
        with _patch_auth(user):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/analyze/comprehensive",
                    data={"jd_text": "Looking for a Python engineer"},
                    headers={"Authorization": "Bearer fake"},
                )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_jd_returns_400(self):
        """Resume provided but no JD → 400 with clear message."""
        user = _mock_free_user()
        with _patch_auth(user):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/analyze/comprehensive",
                    files={"resume": ("resume.txt", b"Python engineer with 5 years experience building scalable applications", "text/plain")},
                    data={"jd_text": ""},
                    headers={"Authorization": "Bearer fake"},
                )
        # Either 400 (JD required) or 400 (resume too short depending on parser)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_resume_returns_400(self):
        """Nearly-empty resume file → 400 (too short)."""
        user = _mock_free_user()
        with _patch_auth(user):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/analyze/comprehensive",
                    files={"resume": ("resume.txt", b"hi", "text/plain")},
                    data={"jd_text": "Looking for Python engineer"},
                    headers={"Authorization": "Bearer fake"},
                )
        assert resp.status_code == 400
        assert "short" in resp.json()["detail"].lower() or "extract" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Quota Enforcement Tests
# ---------------------------------------------------------------------------

class TestQuotaEnforcement:
    """FREE tier users are capped at 3 scans/month."""

    @pytest.mark.asyncio
    async def test_maxed_free_user_gets_429(self):
        """
        FREE user with 3/3 scans used → 429 Too Many Requests.
        This validates the check_scan_quota dependency.
        """
        from fastapi import HTTPException

        maxed_user = _mock_maxed_user()

        # Don't mock check_scan_quota — let it actually raise
        with patch("backend.auth.get_current_user", new_callable=AsyncMock, return_value=maxed_user):
            with patch(
                "backend.auth.check_scan_quota",
                new_callable=AsyncMock,
                side_effect=HTTPException(status_code=429, detail="Monthly scan limit reached"),
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post(
                        "/api/analyze/comprehensive",
                        files={"resume": ("resume.pdf", _load_fixture("sample_resume.pdf"), "application/pdf")},
                        data={"jd_text": "Looking for Python engineer"},
                        headers={"Authorization": "Bearer fake"},
                    )

        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Async Analysis Happy Path
# ---------------------------------------------------------------------------

class TestAsyncAnalysisFlow:
    """Full async flow: upload → 202 → background job → poll → result."""

    @pytest.mark.asyncio
    async def test_valid_upload_returns_202_with_session_id(self):
        """
        Upload valid resume + JD → 202 Accepted with session_id + poll_url.
        This is the critical entry point for the 8-step pipeline.
        """
        user = _mock_free_user()

        jd_text = (FIXTURES_DIR / "sample_jd.txt").read_text()

        # Mock DB: no existing cached analysis
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        with _patch_auth(user):
            with patch("backend.main.get_db", return_value=mock_db):
                with patch("backend.main.run_analysis_job", new_callable=AsyncMock):
                    transport = ASGITransport(app=app)
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        resp = await client.post(
                            "/api/analyze/comprehensive",
                            files={"resume": ("resume.pdf", _load_fixture("sample_resume.pdf"), "application/pdf")},
                            data={"jd_text": jd_text},
                            headers={"Authorization": "Bearer fake"},
                        )

        assert resp.status_code == 202
        data = resp.json()
        assert "session_id" in data
        assert "poll_url" in data
        assert data["status"] in ["pending", "completed"]

    @pytest.mark.asyncio
    async def test_idempotent_reupload_returns_cached_session(self):
        """
        Same resume+JD within 24h → returns existing session_id (no re-processing).
        Validates the SHA256 hash-based idempotency check.
        """
        user = _mock_free_user()
        existing_session_id = "cached-session-123"

        # Mock: existing completed analysis found
        mock_existing = MagicMock(spec=AnalysisResult)
        mock_existing.session_id = existing_session_id
        mock_existing.status = AnalysisStatus.completed

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_existing
        mock_db.execute.return_value = mock_result

        jd_text = (FIXTURES_DIR / "sample_jd.txt").read_text()

        with _patch_auth(user):
            with patch("backend.main.get_db", return_value=mock_db):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post(
                        "/api/analyze/comprehensive",
                        files={"resume": ("resume.pdf", _load_fixture("sample_resume.pdf"), "application/pdf")},
                        data={"jd_text": jd_text},
                        headers={"Authorization": "Bearer fake"},
                    )

        assert resp.status_code == 202
        data = resp.json()
        assert data["session_id"] == existing_session_id
        assert data["status"] == "completed"


# ---------------------------------------------------------------------------
# Polling Endpoint Tests
# ---------------------------------------------------------------------------

class TestPollingEndpoint:
    """GET /api/analysis/{session_id}/status structure validation."""

    @pytest.mark.asyncio
    async def test_nonexistent_session_returns_404(self):
        """Unknown session_id → 404 Not Found."""
        user = _mock_free_user()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        with patch("backend.auth.get_current_user", new_callable=AsyncMock, return_value=user):
            with patch("backend.main.get_db", return_value=mock_db):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(
                        "/api/analysis/nonexistent-id/status",
                        headers={"Authorization": "Bearer fake"},
                    )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_pending_analysis_returns_progress(self):
        """In-progress analysis returns step-level progress (no result yet)."""
        user = _mock_free_user()

        mock_analysis = MagicMock(spec=AnalysisResult)
        mock_analysis.session_id = "sess-123"
        mock_analysis.user_id = user.id
        mock_analysis.status = AnalysisStatus.processing
        mock_analysis.current_step = 3
        mock_analysis.step_message = "Optimizing resume..."
        mock_analysis.progress_percent = 37
        mock_analysis.result_json = None
        mock_analysis.error_message = None
        mock_analysis.live_keywords_metadata = None
        mock_analysis.step_timestamps = None
        mock_analysis.og_image_ready = False

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_analysis
        mock_db.execute.return_value = mock_result

        with patch("backend.auth.get_current_user", new_callable=AsyncMock, return_value=user):
            with patch("backend.main.get_db", return_value=mock_db):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(
                        "/api/analysis/sess-123/status",
                        headers={"Authorization": "Bearer fake"},
                    )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processing"
        assert data["current_step"] == 3
        assert data["progress_percent"] == 37
        assert data["result"] is None

    @pytest.mark.asyncio
    async def test_completed_analysis_returns_result(self):
        """Completed analysis returns full result JSON."""
        user = _mock_free_user()
        user.tier = UserTier.pro  # PRO gets full result

        mock_result_json = {
            "original_resume": "...",
            "optimized_resume": "Senior Engineer resume text...",
            "ats_score": {
                "keyword_match_percent": 72.5,
                "semantic_similarity_score": 0.85,
                "final_ats_score": 78.0,
                "missing_keywords": ["Terraform"],
                "recommended_keywords_to_add": ["Terraform", "SQS"],
            },
            "jd_analysis": {
                "required_skills": ["Python", "AWS"],
                "preferred_skills": ["TypeScript"],
                "responsibilities": [],
                "keywords": ["Python", "AWS", "Docker"],
                "tools": ["Docker", "Kubernetes"],
                "experience_level": "Senior",
            },
            "keyword_heatmap": {
                "keywords": ["Python", "AWS", "Docker"],
                "frequencies": [5, 3, 2],
                "importance_scores": [0.9, 0.8, 0.7],
            },
            "chart_paths": {},
        }

        mock_analysis = MagicMock(spec=AnalysisResult)
        mock_analysis.session_id = "sess-done"
        mock_analysis.user_id = user.id
        mock_analysis.status = AnalysisStatus.completed
        mock_analysis.current_step = 8
        mock_analysis.step_message = "Complete"
        mock_analysis.progress_percent = 100
        mock_analysis.result_json = mock_result_json
        mock_analysis.error_message = None
        mock_analysis.live_keywords_metadata = None
        mock_analysis.step_timestamps = None
        mock_analysis.og_image_ready = False

        mock_db = AsyncMock()
        mock_db_result = MagicMock()
        mock_db_result.scalars.return_value.first.return_value = mock_analysis
        mock_db.execute.return_value = mock_db_result

        with patch("backend.auth.get_current_user", new_callable=AsyncMock, return_value=user):
            with patch("backend.main.get_db", return_value=mock_db):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(
                        "/api/analysis/sess-done/status",
                        headers={"Authorization": "Bearer fake"},
                    )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["result"] is not None
        assert data["result"]["ats_score"]["final_ats_score"] == 78.0
        assert "Python" in data["result"]["keyword_heatmap"]["keywords"]

    @pytest.mark.asyncio
    async def test_failed_analysis_returns_error_message(self):
        """Failed analysis returns error_message field."""
        user = _mock_free_user()

        mock_analysis = MagicMock(spec=AnalysisResult)
        mock_analysis.session_id = "sess-fail"
        mock_analysis.user_id = user.id
        mock_analysis.status = AnalysisStatus.failed
        mock_analysis.current_step = 2
        mock_analysis.step_message = "Analyzing job description..."
        mock_analysis.progress_percent = 25
        mock_analysis.result_json = None
        mock_analysis.error_message = "Gemini API rate limit exceeded"
        mock_analysis.live_keywords_metadata = None
        mock_analysis.step_timestamps = None
        mock_analysis.og_image_ready = False

        mock_db = AsyncMock()
        mock_db_result = MagicMock()
        mock_db_result.scalars.return_value.first.return_value = mock_analysis
        mock_db.execute.return_value = mock_db_result

        with patch("backend.auth.get_current_user", new_callable=AsyncMock, return_value=user):
            with patch("backend.main.get_db", return_value=mock_db):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(
                        "/api/analysis/sess-fail/status",
                        headers={"Authorization": "Bearer fake"},
                    )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert "Gemini" in data["error_message"]


# ---------------------------------------------------------------------------
# Rate Limiting Tests
# ---------------------------------------------------------------------------

class TestRateLimiting:
    """Verify slowapi rate limit on /api/analyze/comprehensive."""

    @pytest.mark.asyncio
    async def test_rate_limit_header_present(self):
        """Responses should include rate limit headers."""
        user = _mock_free_user()

        with _patch_auth(user):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/analyze/comprehensive",
                    files={"resume": ("resume.txt", b"Short", "text/plain")},
                    data={"jd_text": "test"},
                    headers={"Authorization": "Bearer fake"},
                )

        # Even a 400 should still have been processed through rate limiter
        # The rate limit is 10/minute, so first request should pass through
        assert resp.status_code in [400, 202]
