# backend/routes/analytics.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict
import logging

from backend.database import get_db
from backend.auth import get_current_user
from backend.services.analytics_service import AnalyticsService
from backend.db_models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def check_admin(current_user: User) -> User:
    """Verify user is admin."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    admin: User = Depends(check_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get complete analytics dashboard with all KPIs.
    Admin-only endpoint.
    """
    try:
        service = AnalyticsService(db)
        summary = await service.get_dashboard_summary()
        
        return {
            "status": "success",
            "data": summary,
        }
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard")


@router.get("/mrr")
async def get_mrr_details(
    current_user: User = Depends(get_current_user),
    admin: User = Depends(check_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get detailed MRR breakdown by product.
    """
    try:
        service = AnalyticsService(db)
        mrr = await service.calculate_mrr()
        
        return {
            "status": "success",
            "mrr": mrr,
        }
    except Exception as e:
        logger.error(f"MRR error: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate MRR")


@router.get("/churn")
async def get_churn_details(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    admin: User = Depends(check_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get churn rate for specified period.
    """
    try:
        if days < 1 or days > 365:
            days = 30
        
        service = AnalyticsService(db)
        churn = await service.calculate_churn_rate(days=days)
        
        return {
            "status": "success",
            "churn": churn,
            "period_days": days,
        }
    except Exception as e:
        logger.error(f"Churn error: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate churn")


@router.get("/adoption")
async def get_adoption_details(
    current_user: User = Depends(get_current_user),
    admin: User = Depends(check_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get agent adoption rates.
    """
    try:
        service = AnalyticsService(db)
        adoption = await service.get_agent_adoption()
        
        return {
            "status": "success",
            "adoption": adoption,
        }
    except Exception as e:
        logger.error(f"Adoption error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get adoption rates")


@router.get("/forecast")
async def get_forecast(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    admin: User = Depends(check_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get revenue forecast for N days.
    """
    try:
        if days < 1 or days > 90:
            days = 30
        
        service = AnalyticsService(db)
        forecast = await service.forecast_revenue(days=days)
        
        return {
            "status": "success",
            "forecast": forecast,
            "forecast_days": days,
        }
    except Exception as e:
        logger.error(f"Forecast error: {e}")
        raise HTTPException(status_code=500, detail="Failed to forecast revenue")


@router.get("/funnel")
async def get_conversion_funnel(
    current_user: User = Depends(get_current_user),
    admin: User = Depends(check_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get free → pro conversion funnel stages.
    """
    try:
        service = AnalyticsService(db)
        funnel = await service.get_conversion_funnel()
        
        return {
            "status": "success",
            "funnel": funnel,
        }
    except Exception as e:
        logger.error(f"Funnel error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get conversion funnel")


@router.get("/cohorts")
async def get_cohort_analysis(
    months: int = 3,
    current_user: User = Depends(get_current_user),
    admin: User = Depends(check_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Get user retention by signup cohort.
    """
    try:
        if months < 1 or months > 12:
            months = 3
        
        service = AnalyticsService(db)
        cohorts = await service.get_user_cohort_analysis(months=months)
        
        return {
            "status": "success",
            "cohorts": cohorts,
            "months": months,
        }
    except Exception as e:
        logger.error(f"Cohort error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get cohort analysis")
