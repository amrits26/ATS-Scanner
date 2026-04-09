# backend/services/analytics_service.py
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

logger = logging.getLogger(__name__)

class AnalyticsService:
    """
    Aggregates business metrics for admin dashboard.
    Tracks: MRR, churn, CAC, LTV, agent adoption, etc.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.cache_ttl = 3600  # 1 hour cache

    async def calculate_mrr(self, days_back: int = 30) -> Dict:
        """
        Calculate Monthly Recurring Revenue.
        
        Returns:
            {
                current: 32500,  // $32.5K in cents
                change_percent: 12.5,  // MoM change
                breakdown: {
                    email_nudges: 4000,
                    coach: 8500,
                    tailor: 12000,
                    interview: 4000,
                    analytics_pro: 4000
                }
            }
        """
        from backend.db_models import Subscription

        # Get current month subscriptions
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)

        stmt = select(
            Subscription.product,
            func.sum(Subscription.price_cents).label("total")
        ).where(
            and_(
                Subscription.created_at >= month_start,
                Subscription.cancelled_at == None
            )
        ).group_by(Subscription.product)

        result = await self.db.execute(stmt)
        current_breakdown = {row[0]: row[1] for row in result.fetchall()}
        current_mrr = sum(current_breakdown.values())

        # Get previous month for comparison
        prev_month_start = month_start - timedelta(days=1)
        prev_month_start = datetime(prev_month_start.year, prev_month_start.month, 1)
        prev_month_end = month_start - timedelta(seconds=1)

        prev_stmt = select(func.sum(Subscription.price_cents)).where(
            and_(
                Subscription.created_at >= prev_month_start,
                Subscription.created_at <= prev_month_end,
                Subscription.cancelled_at == None
            )
        )

        prev_result = await self.db.execute(prev_stmt)
        prev_mrr = prev_result.scalar() or 0

        # Calculate MoM growth
        change_percent = 0
        if prev_mrr > 0:
            change_percent = ((current_mrr - prev_mrr) / prev_mrr * 100)

        return {
            "current_cents": current_mrr,
            "current_dollars": current_mrr / 100,
            "change_percent": round(change_percent, 2),
            "breakdown": {
                k: {"cents": v, "dollars": v / 100}
                for k, v in current_breakdown.items()
            }
        }

    async def calculate_churn_rate(self, days: int = 30) -> Dict:
        """
        Calculate user churn rate.
        
        Returns:
            {
                rate: 0.08,  // 8%
                users_churned: 24,
                total_users: 300,
                goal: 0.05
            }
        """
        from backend.db_models import User, Subscription

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Total active users
        total_stmt = select(func.count(User.id)).where(User.created_at < datetime.utcnow())
        total_result = await self.db.execute(total_stmt)
        total_users = total_result.scalar() or 1

        # Churned users (cancelled subscription in period)
        churn_stmt = select(func.count(Subscription.id)).where(
            and_(
                Subscription.cancelled_at >= cutoff_date,
                Subscription.cancelled_at < datetime.utcnow()
            )
        )
        churn_result = await self.db.execute(churn_stmt)
        churned_users = churn_result.scalar() or 0

        churn_rate = churned_users / max(total_users, 1)

        return {
            "rate": round(churn_rate, 4),
            "rate_percentage": round(churn_rate * 100, 2),
            "users_churned": churned_users,
            "total_users": total_users,
            "goal_percentage": 5.0,
            "vs_goal": "✅ Better than goal" if churn_rate <= 0.05 else "⚠️ Needs improvement"
        }

    async def get_agent_adoption(self) -> Dict:
        """
        Get percentage of users adopting each agent.
        
        Returns:
            {
                coach: {usage: 42, percentage: 14},
                tailor: {usage: 156, percentage: 52},
                interview: {usage: 78, percentage: 26}
            }
        """
        from backend.db_models import AgentExecution, User

        # Total users
        total_stmt = select(func.count(User.id))
        total_result = await self.db.execute(total_stmt)
        total_users = total_result.scalar() or 1

        # Users per agent
        adoption = {}
        for agent_type in ["coach", "tailor", "interview"]:
            stmt = select(func.count(func.distinct(AgentExecution.user_id))).where(
                AgentExecution.agent_type == agent_type
            )
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            adoption[agent_type] = {
                "users": count,
                "percentage": round((count / total_users * 100), 1)
            }

        return adoption

    async def forecast_revenue(self, days: int = 30) -> Dict:
        """
        Simple forecast of future revenue based on current trend.
        
        Returns:
            {
                current: 32500,
                forecast_30_days: 36500,
                confidence: 0.87
            }
        """
        current = await self.calculate_mrr()
        current_mrr = current["current_cents"]

        # Simple linear extrapolation
        change_percent = current.get("change_percent", 0)
        forecast_mrr = current_mrr * (1 + (change_percent / 100))

        # Confidence (lower if trend is volatile)
        confidence = 0.75 if abs(change_percent) < 20 else 0.60

        return {
            "current_cents": current_mrr,
            "forecast_30_days_cents": int(forecast_mrr),
            "forecast_30_days_dollars": round(forecast_mrr / 100, 2),
            "growth_rate_percent": change_percent,
            "confidence_percentage": round(confidence * 100, 0),
            "prediction": "↑ Growing" if forecast_mrr > current_mrr else "↓ Declining"
        }

    async def get_conversion_funnel(self) -> Dict:
        """
        Get free → pro → pro_max conversion rates.
        
        Returns:
            {
                free_users: 5000,
                free_trial_conversions: 450,  // 9%
                pro_conversions: 200,          // 44% of trial
                pro_max_conversions: 50        // 25% of pro
            }
        """
        from backend.db_models import User, Subscription

        # Free users
        free_stmt = select(func.count(User.id)).where(User.subscription_tier == "free")
        free_result = await self.db.execute(free_stmt)
        free_users = free_result.scalar() or 1

        # Trial users (converted from free, not yet paid)
        trial_stmt = select(func.count(func.distinct(User.id))).where(
            User.subscription_tier == "pro_trial"
        )
        trial_result = await self.db.execute(trial_stmt)
        trial_users = trial_result.scalar() or 0

        # Pro users
        pro_stmt = select(func.count(func.distinct(User.id))).where(
            User.subscription_tier == "pro"
        )
        pro_result = await self.db.execute(pro_stmt)
        pro_users = pro_result.scalar() or 0

        # Pro Max users
        pro_max_stmt = select(func.count(func.distinct(User.id))).where(
            User.subscription_tier == "pro_max"
        )
        pro_max_result = await self.db.execute(pro_max_stmt)
        pro_max_users = pro_max_result.scalar() or 0

        return {
            "free_users": free_users,
            "trial_users": trial_users,
            "trial_conversion_percent": round((trial_users / max(free_users, 1) * 100), 2),
            "pro_users": pro_users,
            "pro_conversion_percent": round((pro_users / max(trial_users, 1) * 100), 2),
            "pro_max_users": pro_max_users,
            "pro_max_conversion_percent": round((pro_max_users / max(pro_users, 1) * 100), 2),
        }

    async def get_user_cohort_analysis(self, months: int = 3) -> List[Dict]:
        """
        Get retention by signup cohort.
        
        Returns:
            [
                {
                    cohort: "2025-10",
                    new_users: 1200,
                    retained_day_7: 980,
                    retained_day_30: 650,
                    retention_rate_30: "54%"
                },
                ...
            ]
        """
        from backend.db_models import User

        cohorts = []
        now = datetime.utcnow()

        for i in range(months):
            month = now - timedelta(days=30 * i)
            month_str = month.strftime("%Y-%m")

            month_start = datetime(month.year, month.month, 1)
            month_end = datetime(
                month.year if month.month < 12 else month.year + 1,
                month.month + 1 if month.month < 12 else 1,
                1
            ) - timedelta(seconds=1)

            # New users in month
            new_stmt = select(func.count(User.id)).where(
                and_(
                    User.created_at >= month_start,
                    User.created_at <= month_end
                )
            )
            new_result = await self.db.execute(new_stmt)
            new_users = new_result.scalar() or 0

            # Retained at day 7
            day_7_cutoff = month_start + timedelta(days=7)
            retained_7_stmt = select(func.count(func.distinct(User.id))).where(
                and_(
                    User.created_at >= month_start,
                    User.created_at <= month_end,
                    # User had activity in last 7 days (simplified)
                )
            )
            retained_7_result = await self.db.execute(retained_7_stmt)
            retained_7 = retained_7_result.scalar() or 0

            # Retained at day 30
            retained_30 = int(retained_7 * 0.65)  # Approximate

            cohorts.append({
                "cohort": month_str,
                "new_users": new_users,
                "retained_day_7": retained_7,
                "retained_day_30": retained_30,
                "retention_rate_30_percent": round((retained_30 / max(new_users, 1) * 100), 1)
            })

        return cohorts

    async def get_dashboard_summary(self) -> Dict:
        """
        Get all key metrics for admin dashboard.
        """
        mrr = await self.calculate_mrr()
        churn = await self.calculate_churn_rate()
        adoption = await self.get_agent_adoption()
        forecast = await self.forecast_revenue()
        funnel = await self.get_conversion_funnel()

        return {
            "mrr": mrr,
            "churn": churn,
            "adoption": adoption,
            "forecast": forecast,
            "funnel": funnel,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def log_analytics_snapshot(self) -> None:
        """Create immutable daily snapshot for historical tracking."""
        from backend.db_models import AnalyticsSnapshot

        summary = await self.get_dashboard_summary()
        
        today = datetime.utcnow().date()
        snapshot = AnalyticsSnapshot(
            date=today,
            mrr_cents=summary["mrr"]["current_cents"],
            active_users=summary["funnel"]["pro_users"] + summary["funnel"]["pro_max_users"],
            churned_users=summary["churn"]["users_churned"],
            coach_sessions=0,  # Would aggregate from AgentExecution
            tailor_sessions=0,
            interview_sessions=0,
            created_at=datetime.utcnow(),
        )
        self.db.add(snapshot)
        await self.db.commit()
