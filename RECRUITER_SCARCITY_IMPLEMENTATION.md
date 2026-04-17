"""
RECRUITER SCARCITY FEATURE - IMPLEMENTATION COMPLETE
Date: April 9, 2026
Status: Ready for testing and deployment

This feature adds 7-day expiration + FOMO messaging to recruiter candidate unlocks.
Expected impact: +30-50% unlock conversion rate, ~+50% revenue per 100 high-scorers.

═══════════════════════════════════════════════════════════════════════════════
DEPLOYMENT CHECKLIST
═══════════════════════════════════════════════════════════════════════════════

DATABASE MIGRATION:
□ Run migration: backend/migrations/008_recruiter_scarcity_expiry.sql
  Command: psql $DATABASE_URL < backend/migrations/008_recruiter_scarcity_expiry.sql
  Verifies:
    - recruiter_candidate_queue.expires_at column added
    - recruiter_active_candidates view created
    - recruiter_scarcity_events table created
    - Indexes created for performance

BACKEND SERVICES:
□ recruiter_service.py updated:
  - get_active_candidates_count() - Returns count + FOMO message
  - log_scarcity_event() - Logs impressions for A/B testing

□ analysis_service.py updated:
  - add_high_score_candidate_to_queue() now sets expires_at + status

□ recruiter.py routes updated:
  - GET /api/recruiter/candidates/count - Return scarcity data

□ jobs.py updated:
  - cleanup_expired_candidates() - Daily cleanup task
  - WorkerSettings.functions now includes cleanup_expired_candidates

FRONTEND:
□ RecruiterScarcityBadge component created:
  - Display FOMO messaging based on count
  - 4 variants: urgent_3, warning_10, normal, empty
  - Loading and error states
  - A/B analytics ready

□ CSS styling: RecruiterScarcityBadge.css
  - Gradient backgrounds (red for urgent, orange for warning)
  - Responsive design (mobile-first)
  - Accessibility: high contrast, reduced motion support

═══════════════════════════════════════════════════════════════════════════════
TESTING CHECKLIST
═══════════════════════════════════════════════════════════════════════════════

1. DATABASE
   □ Verify migration ran successfully:
     SELECT column_name FROM information_schema.columns 
     WHERE table_name='recruiter_candidate_queue' AND column_name='expires_at';
   
   □ Test view works:
     SELECT COUNT(*) FROM recruiter_active_candidates;
   
   □ Verify scarcity_events table exists:
     SELECT * FROM recruiter_scarcity_events LIMIT 1;

2. BACKEND - Manual API Testing
   □ Start server: python -m uvicorn backend.main:app --reload
   
   □ Create test recruiter token
   
   □ Call candidates/count endpoint:
     curl -H "Authorization: Bearer $TOKEN" \
       "http://localhost:8000/api/recruiter/candidates/count?skills=python&recruiting_email=test@example.com"
     
     Expected response:
     {
         "count": 5,
         "message": "⏳ 5 candidates available (some expire within 48 hours)",
         "message_variant": "warning_10",
         "expires_soon_count": 1
     }

3. FRONTEND - Component Integration
   □ Import component in recruiter dashboard:
     import { RecruiterScarcityBadge } from './components/RecruiterScarcityBadge';
     import './components/RecruiterScarcityBadge.css';
   
   □ Add to JSX:
     <RecruiterScarcityBadge
       skills="python,javascript"
       locationState="CA"
       minScore={85}
       recruiterEmail={currentUser.email}
       onCountChange={(count) => setAvailableCount(count)}
     />
   
   □ Verify UI renders correctly:
     - Different message for count ranges: 1-3, 4-10, 11+, 0
     - Correct color variants (red, orange, green, gray)
     - Loading spinner appears briefly
     - Responsive on mobile

4. ARQ CLEANUP TASK
   □ Start ARQ worker: python -m arq backend.jobs.WorkerSettings
   
   □ Verify cleanup runs (check logs):
     [ARQ CLEANUP] Marked X candidates as expired
   
   □ Test cron manually (optional):
     from backend.jobs import cleanup_expired_candidates
     result = await cleanup_expired_candidates({})
     # Should return {"expired_count": N}

5. A/B TESTING VALIDATION
   □ Generate test data with varied expiration times
   
   □ Verify events logged to recruiter_scarcity_events:
     SELECT * FROM recruiter_scarcity_events ORDER BY created_at DESC;
   
   □ Run A/B analysis query (before/after conversion):
     SELECT 
       message_variant,
       COUNT(*) as impression_count,
       ROUND(100.0 * SUM(CASE WHEN event_type='unlock' THEN 1 ELSE 0 END) / COUNT(*), 2) as conversion_rate
     FROM recruiter_scarcity_events
     GROUP BY message_variant;

═══════════════════════════════════════════════════════════════════════════════
EXPECTED METRICS
═══════════════════════════════════════════════════════════════════════════════

Before Scarcity Feature:
- Unlock conversion: ~5-7%
- Revenue per 100 high-scorers: $40 ($5 × 8 unlocks average)

After Scarcity Feature (Projected):
- Unlock conversion: ~8-12% (+30-50% lift)
- Revenue per 100 high-scorers: $60-$80 (+50-100% lift)
- Message variant distribution: 30% urgent_3, 40% warning_10, 30% normal

═══════════════════════════════════════════════════════════════════════════════
TROUBLESHOOTING
═══════════════════════════════════════════════════════════════════════════════

Issue: Migration fails with "column already exists"
Solution: Already applied previously; verify with: SELECT expires_at FROM recruiter_candidate_queue LIMIT 1;

Issue: GET /candidates/count returns 0 count for all searches
Solution: Check that high-score candidates are being inserted:
  SELECT COUNT(*) FROM recruiter_candidate_queue WHERE status='pending';

Issue: Frontend component not displaying
Solution: Verify import and CSS file is present:
  - RecruiterScarcityBadge.tsx exists in src/components/
  - RecruiterScarcityBadge.css imported in component
  - API key token passed correctly

Issue: ARQ cleanup task not running
Solution: Check worker logs for errors:
  - Verify cleanup_expired_candidates in WorkerSettings.functions
  - Check Redis connection: redis-cli PING
  - Restart worker: python -m arq backend.jobs.WorkerSettings

═══════════════════════════════════════════════════════════════════════════════
ROLLBACK PLAN (If needed)
═══════════════════════════════════════════════════════════════════════════════

1. Disable scarcity messages (feature flag):
   In recruiter.py, add:
   if not os.getenv("RECRUITER_SCARCITY_ENABLED", "true").lower() == "true":
       return {"count": 999, "message": "...", "message_variant": "normal", ...}

2. Revert database changes (optional):
   ALTER TABLE recruiter_candidate_queue DROP COLUMN expires_at;
   DROP VIEW recruiter_active_candidates;
   DROP TABLE recruiter_scarcity_events;

3. Revert code:
   - Remove get_active_candidates_count, log_scarcity_event from recruiter_service.py
   - Remove cleanup_expired_candidates from jobs.py
   - Remove /candidates/count endpoint from recruiter.py
   - Remove RecruiterScarcityBadge component and CSS

═══════════════════════════════════════════════════════════════════════════════
FILES CHANGED
═══════════════════════════════════════════════════════════════════════════════

Database:
  ✓ backend/migrations/008_recruiter_scarcity_expiry.sql (NEW)

Backend Services:
  ✓ backend/services/recruiter_service.py (UPDATED - added 2 functions)
  ✓ backend/services/analysis_service.py (UPDATED - added expires_at to INSERT)
  ✓ backend/routes/recruiter.py (UPDATED - added endpoint + imports)
  ✓ backend/jobs.py (UPDATED - added cleanup task, updated WorkerSettings)

Frontend:
  ✓ frontend/src/components/RecruiterScarcityBadge.tsx (NEW)
  ✓ frontend/src/components/RecruiterScarcityBadge.css (NEW)

═══════════════════════════════════════════════════════════════════════════════
NEXT STEPS
═══════════════════════════════════════════════════════════════════════════════

1. Run database migration
2. Test API endpoint locally
3. Integrate component in recruiter dashboard
4. Deploy to staging
5. Monitor conversion metrics for 1 week
6. If >30% lift confirmed: Deploy to production
7. Begin A/B test on secondary message variants

For fear-email A/B testing (next feature): See plan in session memory
"""
