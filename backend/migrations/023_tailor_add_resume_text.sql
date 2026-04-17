-- 023_tailor_add_resume_text.sql
-- Add resume_text column to store the original resume for diff view on success page

ALTER TABLE tailor_rewrite_purchases
ADD COLUMN IF NOT EXISTS resume_text TEXT DEFAULT NULL;
