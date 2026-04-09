// backend/tests/test_hn_scraper.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.hn_job_scraper import HNJobScraper


class TestHNScraper:
    """Test Hacker News job scraper."""

    @pytest.fixture
    async def mock_db(self):
        """Create mock database session."""
        return MagicMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_scraper_extracts_skills(self):
        """Verify scraper correctly identifies skills in job posts."""
        scraper = HNJobScraper()
        
        text = "Looking for Python and JavaScript developer with AWS experience"
        skills = scraper._extract_skills(text)
        
        assert "Python" in skills
        assert "JavaScript" in skills
        assert "AWS" in skills

    @pytest.mark.asyncio
    async def test_scraper_skill_extraction_case_insensitive(self):
        """Verify skill extraction is case-insensitive."""
        scraper = HNJobScraper()
        
        text = "PYTHON and python and PyThOn"
        skills = scraper._extract_skills(text)
        
        # Should only have one Python (deduplicated)
        assert skills.count("Python") == 1

    @pytest.mark.asyncio
    async def test_scraper_identifies_multiple_skills(self):
        """Verify scraper finds all relevant skills."""
        scraper = HNJobScraper()
        
        text = """
        We are hiring! Requirements:
        - Python or Go
        - React or Vue
        - Kubernetes and Docker
        - AWS or GCP
        - Machine Learning experience
        """
        skills = scraper._extract_skills(text)
        
        expected = ["Python", "Go", "React", "Vue", "Kubernetes", "Docker", "AWS", "GCP", "AI"]
        for exp in expected:
            assert exp in skills or any(exp.lower() in s.lower() for s in skills)

    @pytest.mark.asyncio
    async def test_scraper_no_false_positives(self):
        """Verify scraper doesn't match unrelated words."""
        scraper = HNJobScraper()
        
        text = "This is a job posting without technical skills mentioned"
        skills = scraper._extract_skills(text)
        
        assert len(skills) == 0

    @pytest.mark.asyncio
    async def test_scraper_handles_empty_text(self):
        """Verify scraper handles empty input gracefully."""
        scraper = HNJobScraper()
        
        skills = scraper._extract_skills("")
        
        assert skills == []

    @pytest.mark.asyncio
    async def test_scraper_initialization(self, mock_db):
        """Verify scraper can be initialized."""
        scraper = HNJobScraper(mock_db)
        
        assert scraper.db == mock_db
        assert len(scraper.skill_patterns) > 10


class TestHNScraperIntegration:
    """Integration tests for HN scraper."""

    @pytest.mark.asyncio
    async def test_scrape_whoishiring_returns_list(self):
        """Verify scraper returns list format."""
        scraper = HNJobScraper()
        
        with patch("aiohttp.ClientSession") as mock_session:
            # Mock API responses
            mock_session.return_value.__aenter__ = AsyncMock()
            mock_session.return_value.__aexit__ = AsyncMock()
            
            result = await scraper.scrape_whoishiring()
            
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_scraper_update_trending_skills(self):
        """Verify scraper can update trending skills table."""
        db = MagicMock(spec=AsyncSession)
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.add = MagicMock()
        
        scraper = HNJobScraper(db)
        
        with patch.object(scraper, "scrape_whoishiring", return_value=[
            {"skills": ["Python", "AWS"]},
            {"skills": ["Python", "Go"]},
        ]):
            result = await scraper.update_trending_skills()
            
            assert isinstance(result, dict)
            assert "updated_count" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
