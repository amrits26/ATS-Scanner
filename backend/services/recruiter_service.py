"""
Recruiter Lead Generation Service
Manages high-score candidate queue, unlocks, and hire reporting.
"""
import uuid
import re
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


async def add_high_score_candidate_to_queue(
    db: AsyncSession,
    analysis_result_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    result_json: Dict[str, Any],
    resume_text: str,
) -> Optional[str]:
    """
    If ATS score >= 85, insert candidate into recruiter_candidate_queue.
    Returns candidate_id if inserted, None otherwise.
    """
    try:
        ats_score = result_json.get("ats_score", {}).get("final_ats_score", 0)
        if ats_score < 85:
            return None

        # Extract data from result_json
        skill_gap = result_json.get("skill_gap", {})
        matched_skills = skill_gap.get("matched_skills", [])
        missing_skills = skill_gap.get("missing_skills", [])
        job_title = result_json.get("jd_analysis", {}).get("detected_job_title")

        # Basic experience extraction
        experience_years = None
        exp_match = re.search(r"(\d+)\+?\s*(?:years?|yrs?)", resume_text, re.IGNORECASE)
        if exp_match:
            experience_years = int(exp_match.group(1))

        # Location extraction (naive – look for City, State pattern)
        location_city, location_state = None, None
        loc_match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?),\s*([A-Z]{2})", resume_text)
        if loc_match:
            location_city = loc_match.group(1)
            location_state = loc_match.group(2)

        resume_snippet = resume_text[:500] if resume_text else ""

        # Insert into queue with conflict handling
        query = text("""
            INSERT INTO recruiter_candidate_queue
            (analysis_result_id, user_id, ats_score, matched_skills, missing_skills,
             experience_years, location_city, location_state, job_title_detected, resume_snippet)
            VALUES (:analysis_result_id, :user_id, :ats_score, :matched_skills, :missing_skills,
                    :experience_years, :location_city, :location_state, :job_title, :resume_snippet)
            ON CONFLICT (analysis_result_id) DO NOTHING
            RETURNING id
        """)
        result = await db.execute(query, {
            "analysis_result_id": str(analysis_result_id),
            "user_id": str(user_id) if user_id else None,
            "ats_score": float(ats_score),
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "experience_years": experience_years,
            "location_city": location_city,
            "location_state": location_state,
            "job_title": job_title,
            "resume_snippet": resume_snippet,
        })
        row = result.fetchone()
        if row:
            await db.commit()
            candidate_id = str(row[0])
            logger.info(f"[RECRUITER] Added candidate {candidate_id} to queue, score={ats_score}")
            return candidate_id
    except Exception as e:
        logger.error(f"[RECRUITER] Error adding candidate to queue: {str(e)}")
        await db.rollback()
    
    return None


async def get_available_leads(
    db: AsyncSession,
    recruiter_email: str,
    skills: Optional[List[str]] = None,
    location_state: Optional[str] = None,
    min_score: float = 85,
    days_old: int = 30,
    page: int = 1,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Return paginated list of leads with unlock/hire status for this recruiter.
    """
    offset = (page - 1) * limit
    cutoff_date = datetime.utcnow() - timedelta(days=days_old)

    # Build dynamic WHERE clause
    where_clauses = [
        "q.ats_score >= :min_score",
        "q.created_at >= :cutoff_date",
    ]
    
    params = {
        "recruiter_email": recruiter_email,
        "min_score": float(min_score),
        "cutoff_date": cutoff_date,
        "limit": limit,
        "offset": offset,
    }
    
    if skills:
        where_clauses.append("q.matched_skills && :skills_array")
        params["skills_array"] = skills
    
    if location_state:
        where_clauses.append("q.location_state = :location_state")
        params["location_state"] = location_state

    where_sql = " AND ".join(where_clauses)

    query = text(f"""
        SELECT
            q.id,
            q.ats_score,
            q.matched_skills,
            q.missing_skills,
            q.experience_years,
            q.location_city,
            q.location_state,
            q.job_title_detected,
            q.resume_snippet,
            q.created_at,
            CASE
                WHEN h.id IS NOT NULL THEN 'hired'
                WHEN u.id IS NOT NULL AND u.status = 'completed' AND u.expires_at > NOW() THEN 'unlocked'
                WHEN u.id IS NOT NULL AND u.status = 'pending' THEN 'pending_payment'
                ELSE 'available'
            END AS unlock_status
        FROM recruiter_candidate_queue q
        LEFT JOIN recruiter_unlock_purchases u
            ON q.id = u.candidate_id AND u.recruiter_email = :recruiter_email
        LEFT JOIN recruiter_hire_reports h
            ON q.id = h.candidate_id AND h.recruiter_email = :recruiter_email
        WHERE {where_sql}
        ORDER BY q.ats_score DESC, q.created_at DESC
        LIMIT :limit OFFSET :offset
    """)

    result = await db.execute(query, params)
    rows = result.fetchall()
    
    leads = []
    for row in rows:
        leads.append({
            "id": str(row[0]),
            "ats_score": float(row[1]),
            "matched_skills": row[2] or [],
            "missing_skills": row[3] or [],
            "experience_years": row[4],
            "location_city": row[5],
            "location_state": row[6],
            "job_title_detected": row[7],
            "resume_snippet": row[8],
            "created_at": row[9].isoformat() if row[9] else None,
            "unlock_status": row[10],
        })

    # Count total matching records
    count_query = text(f"""
        SELECT COUNT(*)
        FROM recruiter_candidate_queue q
        WHERE {where_sql}
    """)
    count_result = await db.execute(count_query, params)
    total = count_result.scalar() or 0

    return {
        "leads": leads,
        "total": int(total),
        "page": page,
        "limit": limit,
    }


async def get_recruiter_stats(db: AsyncSession, recruiter_email: str) -> Dict[str, Any]:
    """Return stats for a recruiter: unlocks, hires, amounts."""
    # Unlock stats
    unlock_query = text("""
        SELECT COUNT(*) as total_unlocks, COALESCE(SUM(amount_cents), 0) as amount_spent_cents
        FROM recruiter_unlock_purchases
        WHERE recruiter_email = :email AND status = 'completed'
    """)
    unlock_res = await db.execute(unlock_query, {"email": recruiter_email})
    unlock_row = unlock_res.fetchone()
    total_unlocks = unlock_row[0] if unlock_row else 0
    amount_spent_cents = unlock_row[1] if unlock_row else 0

    # Hire stats
    hire_query = text("""
        SELECT COUNT(*) as total_hires, COALESCE(SUM(amount_cents), 0) as amount_earned_cents
        FROM recruiter_hire_reports
        WHERE recruiter_email = :email AND status = 'paid'
    """)
    hire_res = await db.execute(hire_query, {"email": recruiter_email})
    hire_row = hire_res.fetchone()
    total_hires = hire_row[0] if hire_row else 0
    amount_earned_cents = hire_row[1] if hire_row else 0

    # Recent hires
    recent_query = text("""
        SELECT q.ats_score, h.hire_date, h.status
        FROM recruiter_hire_reports h
        JOIN recruiter_candidate_queue q ON h.candidate_id = q.id
        WHERE h.recruiter_email = :email
        ORDER BY h.hire_date DESC
        LIMIT 5
    """)
    recent_res = await db.execute(recent_query, {"email": recruiter_email})
    recent_hires = [
        {
            "candidate_ats_score": row[0],
            "hire_date": row[1].isoformat() if row[1] else None,
            "payment_status": row[2]
        }
        for row in recent_res.fetchall()
    ]

    return {
        "total_unlocks": int(total_unlocks),
        "total_hires": int(total_hires),
        "amount_spent": round(amount_spent_cents / 100, 2),
        "amount_earned": round(amount_earned_cents / 100, 2),
        "recent_hires": recent_hires,
    }


async def get_unlocked_candidate(
    db: AsyncSession,
    candidate_id: str,
    recruiter_email: str
) -> Optional[Dict[str, Any]]:
    """Return full candidate info if unlocked and not expired."""
    query = text("""
        SELECT q.ats_score, q.matched_skills, q.missing_skills, q.experience_years,
               q.location_city, q.location_state, q.job_title_detected, q.resume_snippet,
               ar.result_json
        FROM recruiter_candidate_queue q
        JOIN analysis_results ar ON q.analysis_result_id = ar.id
        LEFT JOIN recruiter_unlock_purchases u
            ON q.id = u.candidate_id AND u.recruiter_email = :recruiter_email
        WHERE q.id = :candidate_id
          AND u.status = 'completed'
          AND u.expires_at > NOW()
    """)
    result = await db.execute(query, {
        "candidate_id": candidate_id,
        "recruiter_email": recruiter_email
    })
    row = result.fetchone()
    if not row:
        return None

    # Get full resume from result_json
    result_json = row[8] or {}
    full_resume = result_json.get("original_resume") or row[7]

    return {
        "id": candidate_id,
        "ats_score": float(row[0]),
        "matched_skills": row[1] or [],
        "missing_skills": row[2] or [],
        "experience_years": row[3],
        "location": f"{row[4]}, {row[5]}" if row[4] and row[5] else None,
        "job_title_detected": row[6],
        "resume_full_text": full_resume,
    }
