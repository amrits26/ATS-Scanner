# backend/services/trending_skills_service.py
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

class TrendingSkillsService:
    """
    Aggregates skill demand data from multiple sources (HN, submissions, etc.)
    Provides market insights: "Is Python demand increasing? What's your percentile?"
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_skill_percentile(
        self,
        user_id: str,
        skill: str,
    ) -> Dict:
        """
        Calculate where user's skill stands vs market demand.
        
        Returns:
            {
                skill: "Python",
                your_proficiency: 85,  # from user's resume scoring
                market_demand: 95,     # %ile of job postings mentioning it
                percentile: 82,        # Your rank (1-100)
                trend: "↑ +15% YoY",
                recommendation: "Strong skill, high demand"
            }
        """
        from backend.db_models import TrendingSkills, AnalysisResult

        # Get market demand
        current_month = datetime.utcnow().strftime("%Y-%m")
        stmt = select(TrendingSkills).where(
            and_(
                TrendingSkills.skill_name == skill,
                TrendingSkills.month == current_month
            )
        )
        result = await self.db.execute(stmt)
        market_data = result.scalar_one_or_none()

        market_demand = market_data.demand_percentage if market_data else 0

        # Get user's proficiency for this skill
        # (simplified - in real system would check resume analysis)
        user_proficiency = 75  # Placeholder

        # Calculate percentile (skill demand ranking vs all skills)
        all_stmt = select(TrendingSkills).where(
            TrendingSkills.month == current_month
        ).order_by(desc(TrendingSkills.demand_percentage))
        
        all_result = await self.db.execute(all_stmt)
        all_skills = all_result.scalars().all()

        rank = 0
        for i, s in enumerate(all_skills):
            if s.skill_name.lower() == skill.lower():
                rank = i + 1
                break

        percentile = max(1, 100 - (rank * 100 // len(all_skills))) if all_skills else 50

        # Calculate trend (YoY)
        last_year = datetime.utcnow() - timedelta(days=365)
        last_year_month = last_year.strftime("%Y-%m")
        
        year_ago_stmt = select(TrendingSkills).where(
            and_(
                TrendingSkills.skill_name == skill,
                TrendingSkills.month == last_year_month
            )
        )
        year_ago_result = await self.db.execute(year_ago_stmt)
        year_ago_data = year_ago_result.scalar_one_or_none()

        previous_demand = year_ago_data.demand_percentage if year_ago_data else market_demand
        yoy_change = ((market_demand - previous_demand) / (previous_demand + 0.1) * 100)
        trend = f"↑ +{yoy_change:.0f}% YoY" if yoy_change > 0 else f"↓ {yoy_change:.0f}% YoY"

        return {
            "skill": skill,
            "your_proficiency": user_proficiency,
            "market_demand_percentage": market_demand,
            "percentile": percentile,
            "trend": trend,
            "recommendation": self._get_recommendation(percentile, yoy_change),
        }

    def _get_recommendation(self, percentile: int, yoy_change: float) -> str:
        """Get recommendation based on percentile and trend."""
        if percentile >= 80:
            if yoy_change > 10:
                return "🔥 Highly demanded and growing fast"
            return "✅ Strong skill with consistent demand"
        elif percentile >= 50:
            if yoy_change > 10:
                return "📈 Growing demand - good time to learn"
            return "🎯 Moderate demand - solid to know"
        else:
            return "⚠️ Low current demand - consider alternatives"

    async def get_trending_skills(self, limit: int = 20) -> List[Dict]:
        """
        Get top trending skills this month.
        
        Returns:
            [
                {skill: "Python", demand: 95, trend: "↑ +5%"},
                ...
            ]
        """
        from backend.db_models import TrendingSkills

        current_month = datetime.utcnow().strftime("%Y-%m")
        stmt = select(TrendingSkills).where(
            TrendingSkills.month == current_month
        ).order_by(desc(TrendingSkills.demand_percentage)).limit(limit)

        result = await self.db.execute(stmt)
        skills = result.scalars().all()

        return [
            {
                "skill": s.skill_name,
                "demand_percentage": s.demand_percentage,
                "job_count": s.job_count,
            }
            for s in skills
        ]

    async def generate_upskilling_recommendations(self, user_id: str) -> List[Dict]:
        """
        Suggest skills user should learn based on market demand + their profile.
        
        Returns:
            [
                {skill: "Rust", current_demand: 65%, upside: "Trending +30% YoY", effort: "High"},
                ...
            ]
        """
        from backend.db_models import TrendingSkills, UserAnalysis

        # Get user's current skills (simplified)
        user_stmt = select(UserAnalysis).where(
            UserAnalysis.user_id == user_id
        ).order_by(desc(UserAnalysis.created_at)).limit(1)
        
        user_result = await self.db.execute(user_stmt)
        user_analysis = user_result.scalar_one_or_none()

        current_skills = set()
        if user_analysis and user_analysis.detected_skills:
            for skill_entry in user_analysis.detected_skills:
                if isinstance(skill_entry, dict):
                    current_skills.add(skill_entry.get("name", "").lower())
                else:
                    current_skills.add(str(skill_entry).lower())

        # Get trending skills
        trending_stmt = select(TrendingSkills).where(
            TrendingSkills.month == datetime.utcnow().strftime("%Y-%m")
        ).order_by(desc(TrendingSkills.demand_percentage))

        trending_result = await self.db.execute(trending_stmt)
        trending_skills = trending_result.scalars().all()

        recommendations = []
        for skill in trending_skills[:15]:
            if skill.skill_name.lower() not in current_skills and skill.demand_percentage > 30:
                recommendations.append({
                    "skill": skill.skill_name,
                    "current_demand_percentage": skill.demand_percentage,
                    "priority": "high" if skill.demand_percentage > 70 else "medium",
                })

        return recommendations[:5]

    async def get_skill_trend_chart(self, skill: str, months: int = 6) -> Dict:
        """
        Get historical skill demand trend for charting.
        
        Returns:
            {
                skill: "Python",
                data: [
                    {month: "2025-10", demand: 88},
                    {month: "2025-11", demand: 90},
                    ...
                ]
            }
        """
        from backend.db_models import TrendingSkills

        cutoff_date = datetime.utcnow() - timedelta(days=30 * months)
        
        stmt = select(TrendingSkills).where(
            and_(
                TrendingSkills.skill_name == skill,
                TrendingSkills.created_at >= cutoff_date
            )
        ).order_by(TrendingSkills.month)

        result = await self.db.execute(stmt)
        records = result.scalars().all()

        return {
            "skill": skill,
            "data": [
                {
                    "month": r.month,
                    "demand_percentage": r.demand_percentage,
                    "job_count": r.job_count,
                }
                for r in records
            ],
        }

    async def get_market_insights(self) -> Dict:
        """
        Get overall market insights for dashboard.
        
        Returns:
            {
                total_jobs_analyzed: 12500,
                top_5_skills: [...],
                fastest_growing: [...],
                highest_paid: [...],
            }
        """
        from backend.db_models import TrendingSkills

        current_month = datetime.utcnow().strftime("%Y-%m")

        # Top 5 by demand
        top_stmt = select(TrendingSkills).where(
            TrendingSkills.month == current_month
        ).order_by(desc(TrendingSkills.demand_percentage)).limit(5)

        top_result = await self.db.execute(top_stmt)
        top_skills = top_result.scalars().all()

        # Total jobs
        count_stmt = select(func.sum(TrendingSkills.job_count)).where(
            TrendingSkills.month == current_month
        )
        count_result = await self.db.execute(count_stmt)
        total_jobs = count_result.scalar() or 0

        return {
            "total_jobs_analyzed": total_jobs,
            "top_5_skills": [
                {"skill": s.skill_name, "demand": f"{s.demand_percentage:.0f}%"}
                for s in top_skills
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }
