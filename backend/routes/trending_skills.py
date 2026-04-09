# backend/routes/trending_skills.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List
import logging

from backend.database import get_db
from backend.auth import get_current_user
from backend.services.trending_skills_service import TrendingSkillsService
from backend.db_models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trending-skills", tags=["trending_skills"])


@router.get("/current")
async def get_trending_skills(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get top trending skills this month.
    
    Query params:
    - limit: Max skills to return (default 20, max 50)
    """
    try:
        if limit > 50:
            limit = 50
        
        service = TrendingSkillsService(db)
        skills = await service.get_trending_skills(limit=limit)
        
        return {
            "status": "success",
            "trending_skills": skills,
            "count": len(skills),
        }
    except Exception as e:
        logger.error(f"Error fetching trending skills: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch trending skills")


@router.get("/percentile")
async def get_skill_percentile(
    skill: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get user's skill proficiency vs market demand.
    
    Example: /api/trending-skills/percentile?skill=Python
    
    Returns:
    {
        "skill": "Python",
        "your_proficiency": 85,
        "market_demand_percentage": 92,
        "percentile": 82,  # Your rank 1-100
        "trend": "↑ +5% YoY",
        "recommendation": "Strong skill, high demand"
    }
    """
    try:
        if not skill:
            raise HTTPException(status_code=400, detail="Skill parameter required")
        
        service = TrendingSkillsService(db)
        percentile = await service.calculate_skill_percentile(
            user_id=current_user.id,
            skill=skill,
        )
        
        return {
            "status": "success",
            "data": percentile,
        }
    except Exception as e:
        logger.error(f"Error calculating percentile: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate percentile")


@router.get("/chart")
async def get_skill_trend_chart(
    skill: str,
    months: int = 6,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get historical skill demand trend for charting.
    
    Example: /api/trending-skills/chart?skill=Python&months=12
    
    Returns time-series data for graphs (e.g., demand over 6 months).
    """
    try:
        if not skill:
            raise HTTPException(status_code=400, detail="Skill parameter required")
        
        if months < 1 or months > 24:
            months = 6
        
        service = TrendingSkillsService(db)
        chart_data = await service.get_skill_trend_chart(
            skill=skill,
            months=months,
        )
        
        return {
            "status": "success",
            "data": chart_data,
        }
    except Exception as e:
        logger.error(f"Error fetching chart data: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch chart data")


@router.get("/recommendations")
async def get_upskilling_recommendations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get personalized skill recommendations based on market demand + user profile.
    
    Returns:
    {
        "recommendations": [
            {
                "skill": "Rust",
                "current_demand_percentage": 65,
                "priority": "high",
                "description": "Growing demand, potential high ROI"
            },
            ...
        ]
    }
    """
    try:
        service = TrendingSkillsService(db)
        recommendations = await service.generate_upskilling_recommendations(
            user_id=current_user.id
        )
        
        return {
            "status": "success",
            "recommendations": recommendations,
        }
    except Exception as e:
        logger.error(f"Error generating recommendations: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate recommendations")


@router.get("/market-insights")
async def get_market_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get overall market insights (dashboard).
    
    Returns:
    {
        "total_jobs_analyzed": 12500,
        "top_5_skills": [
            {"skill": "Python", "demand": "95%"},
            ...
        ],
        "timestamp": "2025-11-15T10:30:00Z"
    }
    """
    try:
        service = TrendingSkillsService(db)
        insights = await service.get_market_insights()
        
        return {
            "status": "success",
            "data": insights,
        }
    except Exception as e:
        logger.error(f"Error fetching market insights: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch market insights")
