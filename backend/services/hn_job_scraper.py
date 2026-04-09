# backend/services/hn_job_scraper.py
import asyncio
import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import aiohttp
from bs4 import BeautifulSoup
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

HN_WHOISHIRING_URL = "https://news.ycombinator.com"
HN_API_URL = "https://hacker-news.firebaseio.com/v0"

class HNJobScraper:
    """
    Scrapes Hacker News "Who is Hiring" threads for job market insights.
    100% legal - public data, no authentication needed.
    """

    def __init__(self, db: AsyncSession = None):
        self.db = db
        self.skill_patterns = {
            'Python': r'\bPython\b',
            'JavaScript': r'\b(JavaScript|JS)\b',
            'TypeScript': r'\bTypeScript\b',
            'React': r'\bReact\b',
            'Vue': r'\bVue\b',
            'Node.js': r'\b(Node\.js|Node)\b',
            'Go': r'\bGo\b',
            'Rust': r'\bRust\b',
            'Java': r'\bJava\b',
            'C++': r'\bC\+\+\b',
            'SQL': r'\b(SQL|PostgreSQL|MySQL|MongoDB)\b',
            'AWS': r'\bAWS\b',
            'GCP': r'\b(GCP|Google Cloud)\b',
            'Kubernetes': r'\b(Kubernetes|K8s)\b',
            'Docker': r'\bDocker\b',
            'AI': r'\b(AI|Artificial Intelligence|Machine Learning|ML)\b',
            'Data Science': r'\b(Data Science|Data Scientist)\b',
            'DevOps': r'\bDevOps\b',
            'Cloud': r'\bCloud\b',
        }

    async def scrape_whoishiring(self) -> List[Dict]:
        """
        Scrape the latest "Who is Hiring" thread.
        Returns list of job postings with extracted skills.
        
        Returns:
            [{text, skills, posted_date}, ...]
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Get latest HN "Who is Hiring" thread
                async with session.get(
                    f"{HN_API_URL}/topstories.json",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"HN API returned {resp.status}")
                        return []
                    
                    top_stories = await resp.json()

                jobs = []
                
                # Check first 30 stories for "Who is Hiring"
                for story_id in top_stories[:30]:
                    async with session.get(
                        f"{HN_API_URL}/item/{story_id}.json",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        if resp.status != 200:
                            continue
                        
                        story = await resp.json()
                        
                        # Look for "Who is Hiring" thread
                        if story and "title" in story:
                            if "who is hiring" in story.get("title", "").lower():
                                # Found it! Now parse comments
                                comments = await self._fetch_comments(session, story.get("kids", [])[:200])
                                jobs.extend(comments)
                                break

                logger.info(f"Scraped {len(jobs)} job postings from HN")
                return jobs

        except Exception as e:
            logger.error(f"Error scraping HN: {e}")
            return []

    async def _fetch_comments(self, session: aiohttp.ClientSession, comment_ids: List[int]) -> List[Dict]:
        """Fetch and parse job comments."""
        jobs = []
        
        for comment_id in comment_ids[:100]:  # Limit to 100 comments
            try:
                async with session.get(
                    f"{HN_API_URL}/item/{comment_id}.json",
                    timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    if resp.status != 200:
                        continue
                    
                    comment = await resp.json()
                    if not comment or "text" not in comment:
                        continue
                    
                    text = comment.get("text", "")
                    
                    # Extract skills
                    skills = self._extract_skills(text)
                    
                    if skills:
                        jobs.append({
                            "text": text[:500],  # First 500 chars
                            "skills": skills,
                            "posted": datetime.utcnow(),
                        })
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.debug(f"Error parsing comment {comment_id}: {e}")
                continue

        return jobs

    def _extract_skills(self, text: str) -> List[str]:
        """Extract skills from job posting text."""
        skills = []
        
        for skill, pattern in self.skill_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                skills.append(skill)
        
        return list(set(skills))  # Deduplicate

    async def update_trending_skills(self) -> Dict:
        """
        Run weekly to update trending_skills table with HN market data.
        
        Returns:
            {updated_count, new_skills, top_5_skills}
        """
        from backend.db_models import TrendingSkills

        if not self.db:
            logger.error("Database not initialized")
            return {}

        # Scrape latest jobs
        jobs = await self.scrape_whoishiring()
        if not jobs:
            logger.warning("No jobs scraped")
            return {}

        # Count skills
        skill_counts: Dict[str, int] = {}
        for job in jobs:
            for skill in job.get("skills", []):
                skill_counts[skill] = skill_counts.get(skill, 0) + 1

        # Update database
        total_jobs = len(jobs)
        updated_count = 0

        for skill, count in skill_counts.items():
            demand_percentage = (count / total_jobs * 100) if total_jobs > 0 else 0
            
            # Check if skill exists
            stmt = select(TrendingSkills).where(
                and_(
                    TrendingSkills.skill_name == skill,
                    TrendingSkills.month == datetime.utcnow().strftime("%Y-%m")
                )
            )
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.demand_percentage = demand_percentage
                existing.job_count = count
                existing.updated_at = datetime.utcnow()
            else:
                new_skill = TrendingSkills(
                    id=str(uuid.uuid4()),
                    skill_name=skill,
                    demand_percentage=demand_percentage,
                    month=datetime.utcnow().strftime("%Y-%m"),
                    job_count=count,
                    source="hn_whoishiring",
                    created_at=datetime.utcnow(),
                )
                self.db.add(new_skill)
            
            updated_count += 1

        await self.db.commit()

        # Get top 5
        top_stmt = select(TrendingSkills).order_by(
            TrendingSkills.demand_percentage.desc()
        ).limit(5)
        top_result = await self.db.execute(top_stmt)
        top_skills = top_result.scalars().all()

        logger.info(
            f"Updated {updated_count} skills from {total_jobs} HN jobs. "
            f"Top: {[s.skill_name for s in top_skills]}"
        )

        return {
            "updated_count": updated_count,
            "new_skills": list(skill_counts.keys()),
            "top_5_skills": [s.skill_name for s in top_skills],
            "total_jobs_analyzed": total_jobs,
        }

    async def get_skill_trend(self, skill: str, months: int = 6) -> List[Dict]:
        """Get skill demand trend over N months."""
        from backend.db_models import TrendingSkills
        from sqlalchemy import and_, func
        
        cutoff_date = datetime.utcnow() - timedelta(days=30 * months)

        stmt = select(TrendingSkills).where(
            and_(
                TrendingSkills.skill_name == skill,
                TrendingSkills.created_at >= cutoff_date
            )
        ).order_by(TrendingSkills.created_at)

        result = await self.db.execute(stmt)
        records = result.scalars().all()

        return [
            {
                "month": r.month,
                "demand_percentage": r.demand_percentage,
                "job_count": r.job_count,
            }
            for r in records
        ]


# For imports
import uuid
from sqlalchemy import and_
