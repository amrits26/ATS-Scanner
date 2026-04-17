-- Migration 017: Add final_ats_score column to analysis_results
-- Purpose: Enable fast percentile queries without parsing JSONB
-- The column is populated by analysis_service.py on completion (step 12)

ALTER TABLE analysis_results
  ADD COLUMN IF NOT EXISTS final_ats_score FLOAT;

-- Index for percentile rank queries
CREATE INDEX IF NOT EXISTS idx_analysis_final_ats_score
  ON analysis_results (final_ats_score)
  WHERE final_ats_score IS NOT NULL AND status = 'completed';

-- Backfill existing rows from result_json JSONB
UPDATE analysis_results
  SET final_ats_score = (result_json -> 'ats_score' ->> 'final_ats_score')::float
  WHERE status = 'completed'
    AND result_json IS NOT NULL
    AND result_json -> 'ats_score' ->> 'final_ats_score' IS NOT NULL
    AND final_ats_score IS NULL;
