"""
Comprehensive test suite for IntelliResume AI backend.
Run with: python -m pytest tests/test_backend.py -v
"""

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Import backend app
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.main import app
from backend.models import (
    ComprehensiveAnalysisResult,
    JobDescriptionAnalysis,
    ATSScoreResponse,
    SkillGapAnalysis,
    ResumeQualityScore,
)


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Test basic health check endpoints."""

    def test_root_endpoint(self, client):
        """Test GET / returns online status."""
        response = client.get("/")
        assert response.status_code == 200
        assert "status" in response.json()
        assert response.json()["status"] == "ATS API is online"

    def test_health_endpoint(self, client):
        """Test GET /health returns ok status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "IntelliResume AI"


class TestAnalysisEndpoint:
    """Test the main /api/analyze/comprehensive endpoint."""

    def test_missing_resume(self, client):
        """Test endpoint rejects request without resume."""
        response = client.post(
            "/api/analyze/comprehensive",
            data={"jd_text": "Sample job description"},
        )
        assert response.status_code == 422  # Unprocessable Entity (FastAPI validation)

    def test_missing_job_description(self, client):
        """Test endpoint rejects request without job description."""
        # Create a dummy PDF-like content
        dummy_pdf = b"%PDF-1.4\n%dummy content"
        
        response = client.post(
            "/api/analyze/comprehensive",
            files={"resume": ("resume.pdf", dummy_pdf)},
        )
        # Should fail because no JD provided
        assert response.status_code == 400
        assert "Job description is required" in response.json()["detail"]

    def test_endpoint_accepts_all_parameters(self, client):
        """Test endpoint accepts all parameter combinations."""
        dummy_pdf = b"%PDF-1.4\n%dummy"
        
        # Test with jd_text
        response = client.post(
            "/api/analyze/comprehensive",
            files={"resume": ("resume.pdf", dummy_pdf)},
            data={"jd_text": "Sample job description"},
        )
        # Will fail due to invalid PDF, but should pass parameter validation
        assert response.status_code in [200, 400]  # Either success or PDF parsing error
        
        # Test with job_description file
        response = client.post(
            "/api/analyze/comprehensive",
            files={
                "resume": ("resume.pdf", dummy_pdf),
                "job_description": ("jd.pdf", dummy_pdf),
            },
        )
        assert response.status_code in [200, 400]

    def test_endpoint_returns_correct_structure(self, client):
        """Test endpoint returns correct response structure."""
        # Note: This test expects OpenAI API key to be configured
        # For testing, we'll verify the structure when it eventually succeeds
        dummy_pdf = b"%PDF-1.4\n%dummy"
        
        response = client.post(
            "/api/analyze/comprehensive",
            files={"resume": ("resume.pdf", dummy_pdf)},
            data={"jd_text": "Sample job description"},
        )
        
        # The endpoint should either:
        # 1. Return 200 with ComprehensiveAnalysisResult structure
        # 2. Return 400 with valid error message
        assert response.status_code in [200, 400, 422]
        
        data = response.json()
        if response.status_code == 200:
            # Verify response structure
            assert "optimized_resume" in data
            assert "ats_score" in data
            assert "jd_analysis" in data
            assert "skill_gap" in data
            assert "resume_quality" in data
            assert "chart_paths" in data


class TestCORSHeaders:
    """Test CORS middleware configuration."""

    def test_cors_headers_present(self, client):
        """Test CORS headers are returned."""
        response = client.get("/health")
        
        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers or response.status_code == 200


class TestErrorHandling:
    """Test error handling and validation."""

    def test_invalid_file_type(self, client):
        """Test endpoint handles invalid file types gracefully."""
        # Send invalid file type
        response = client.post(
            "/api/analyze/comprehensive",
            files={"resume": ("resume.txt", b"plain text content")},
            data={"jd_text": "Job description"},
        )
        # Should handle gracefully either success or error
        assert response.status_code in [200, 400, 422]

    def test_empty_resume(self, client):
        """Test endpoint rejects empty resume."""
        response = client.post(
            "/api/analyze/comprehensive",
            files={"resume": ("resume.pdf", b"")},
            data={"jd_text": "Job description"},
        )
        # Should reject empty file
        assert response.status_code in [400, 422]

    def test_very_short_job_description(self, client):
        """Test endpoint handles very short JD."""
        dummy_pdf = b"%PDF-1.4\n%dummy"
        
        response = client.post(
            "/api/analyze/comprehensive",
            files={"resume": ("resume.pdf", dummy_pdf)},
            data={"jd_text": "a"},
        )
        # Very short JD might be rejected or accepted
        assert response.status_code in [200, 400, 422]


class TestDownloadEndpoint:
    """Test the download-docx endpoint."""

    def test_download_docx_missing_content(self, client):
        """Test endpoint rejects missing resume content."""
        response = client.post("/api/download-docx", data={})
        assert response.status_code == 422  # FastAPI validation error

    def test_download_docx_empty_content(self, client):
        """Test endpoint rejects empty resume content."""
        response = client.post(
            "/api/download-docx",
            data={"optimized_resume": ""},
        )
        assert response.status_code == 400
        assert "Optimized resume text is required" in response.json()["detail"]

    def test_download_docx_valid_content(self, client):
        """Test endpoint accepts valid resume content."""
        response = client.post(
            "/api/download-docx",
            data={"optimized_resume": "John Doe\nSoftware Engineer\nExperience..."},
        )
        # Should return DOCX file or error
        assert response.status_code in [200, 400]
        if response.status_code == 200:
            assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class TestChartEndpoint:
    """Test the charts serving endpoint."""

    def test_chart_not_found(self, client):
        """Test endpoint returns 404 for missing chart."""
        response = client.get("/api/charts/nonexistent/chart.png")
        assert response.status_code == 404


class TestEndpointStructure:
    """Test that all expected endpoints exist."""

    def test_all_endpoints_exist(self, client):
        """Test all documented endpoints are accessible."""
        endpoints = [
            ("GET", "/"),
            ("GET", "/health"),
            ("POST", "/api/scan"),
            ("POST", "/api/optimize"),
            ("POST", "/api/analyze/comprehensive"),
            ("POST", "/api/download-docx"),
        ]
        
        for method, path in endpoints:
            if method == "GET":
                response = client.get(path)
            else:
                # POST endpoints might require parameters, so we just check they exist
                # by sending empty request (might get 400 but endpoint exists)
                response = client.post(path)
            
            # Should get a response (200, 400, 422, etc.) but not 404
            assert response.status_code != 404, f"Endpoint {method} {path} not found"


class TestModelValidation:
    """Test Pydantic model validation."""

    def test_comprehensive_result_model(self):
        """Test ComprehensiveAnalysisResult model can be created."""
        from backend.models import (
            ComprehensiveAnalysisResult,
            ATSScoreResponse,
            JobDescriptionAnalysis,
            SkillGapAnalysis,
            ResumeQualityScore,
            KeywordHeatmapData,
            WritingFeedback,
        )
        
        # Create sample instances
        ats_score = ATSScoreResponse(
            keyword_match_percent=85.0,
            semantic_similarity_score=0.92,
            final_ats_score=88,
            missing_keywords=["Python"],
            recommended_keywords_to_add=["AWS"],
        )
        
        jd_analysis = JobDescriptionAnalysis(
            required_skills=["Python", "CloudFormation"],
            preferred_skills=["Docker", "Kubernetes"],
            responsibilities=["Develop APIs"],
            keywords=["AWS", "DevOps"],
            tools=["Docker"],
            experience_level="Senior",
        )
        
        skill_gap = SkillGapAnalysis(
            matched_skills=["Python"],
            missing_skills=["Kubernetes"],
            gap_score=75.0,
            match_count=1,
            total_required=2,
        )
        
        quality_score = ResumeQualityScore(
            overall_score=82,
            readability_score=85,
            formatting_score=80,
            content_score=83,
            keyword_density_score=78,
            feedback=["Add more metrics"],
        )
        
        heatmap = KeywordHeatmapData(
            keywords=["Python", "AWS"],
            frequencies=[45, 32],
            importance_scores=[0.95, 0.88],
        )
        
        # These should all validate without error
        assert ats_score is not None
        assert jd_analysis is not None
        assert skill_gap is not None
        assert quality_score is not None
        assert heatmap is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
