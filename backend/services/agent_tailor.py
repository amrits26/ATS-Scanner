"""
Auto-Tailor Agent - One-click resume rewriting for specific job descriptions

Scrapes JD from URL, rewrites resume to match, returns structured DOCX-ready output with tracked changes.
"""

import logging
import json
from typing import Dict, List, Any, Optional
from difflib import SequenceMatcher

from sqlalchemy import text, select

from backend.services.agent_base import AIAgent
from backend.services.job_scraper import scrape_job_description
from backend.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class AutoTailorAgent(AIAgent):
    """
    Rewrites a user's resume to align with a specific job description.
    """

    def __init__(self, user_id: str, session_id: str = None, telemetry_tracker=None):
        super().__init__(
            agent_type="tailor",
            user_id=user_id,
            session_id=session_id,
            telemetry_tracker=telemetry_tracker,
        )

    def _register_tools(self) -> None:
        self.tools = {
            "job_scraper": self._job_scraper_tool,
            "resume_rewriter": self._resume_rewriter,
            "match_score_calculator": self._match_score_calculator,
        }

    async def parse_user_goal(self, query: str) -> Dict[str, Any]:
        return {
            "goal": "rewrite_resume_for_job",
            "required_tools": ["job_scraper", "resume_rewriter", "match_score_calculator"],
        }

    # ========================================================================
    # TOOLS
    # ========================================================================

    async def _job_scraper_tool(self, job_url: str = None, jd_text: str = None) -> Dict:
        """
        Get job description from URL or direct text.
        """
        if jd_text:
            return {"job_description": jd_text, "source": "text"}
        if job_url:
            try:
                jd = await scrape_job_description(job_url)
                return {"job_description": jd, "source": "url"}
            except Exception as e:
                logger.error(f"[TAILOR] Scrape failed: {e}")
                return {"job_description": "", "source": "url", "error": str(e)}
        return {"job_description": "", "source": "none"}

    async def _resume_rewriter(self, resume_text: str, job_description: str) -> Dict:
        """
        Rewrite resume to match JD with structured output and tracked changes.
        """
        if not job_description:
            return {"rewritten_resume": resume_text, "key_alignments": [], "tracked_changes": []}

        # Inject synthetic few-shot examples
        examples = await self._inject_synthetic_examples()

        prompt = f"""You are an expert resume writer specializing in ATS optimization. Rewrite this resume to align perfectly with the job description.

{examples}

Current Resume:
{resume_text}

Job Description:
{job_description[:2000]}

CRITICAL RULES:
1. Keep all factual experience, dates, and titles UNCHANGED.
2. Reorder bullets and adjust wording to highlight required JD skills.
3. Add quantifiable metrics (%, $, #) to 80% of bullets.
4. Start each bullet with a strong action verb (e.g., Built, Designed, Optimized).
5. Match exact keywords from the JD wherever possible.
6. Output ONLY valid JSON (no markdown, no explanations).

Return this exact JSON structure:
{{
    "rewritten_resume": "Full resume with sections...",
    "key_alignments": ["alignment 1", "alignment 2", "alignment 3"],
    "alternative_summaries": [
        "Alternative summary 1...",
        "Alternative summary 2...",
        "Alternative summary 3..."
    ]
}}"""
        
        model_text, usage = await self.call_gemini(prompt, temperature=self.TEMPERATURE_CREATIVE, json_mode=True)

        try:
            result = json.loads(model_text)
            rewritten = result.get("rewritten_resume", resume_text)
            alignments = result.get("key_alignments", [])
            alternatives = result.get("alternative_summaries", [])
        except Exception as e:
            logger.warning(f"[TAILOR] JSON parse failed, using fallback: {e}")
            rewritten = model_text
            alignments = ["Resume tailored to job description"]
            alternatives = []

        # Compute tracked changes
        tracked_changes = self._compute_tracked_changes(resume_text, rewritten)

        return {
            "rewritten_resume": rewritten,
            "key_alignments": alignments,
            "tracked_changes": tracked_changes,
            "alternative_summaries": alternatives
        }

    async def _match_score_calculator(self, rewritten_resume: str, job_description: str) -> Dict:
        """Estimate ATS match score (0-100)."""
        prompt = f"""Estimate the ATS match score (0-100) for this resume against the job description.
Resume excerpt: {rewritten_resume[:500]}
Job Description excerpt: {job_description[:500]}

Return JSON: {{"score": 85, "reasoning": "..."}}"""
        
        text, usage = await self.call_gemini(prompt, temperature=self.TEMPERATURE_SCORING, json_mode=True)
        
        try:
            result = json.loads(text)
        except:
            result = {"score": 75, "reasoning": "Automated estimate."}
        
        return result

    # ========================================================================
    # ENHANCED METHODS FOR STRUCTURED OUTPUT & TRACKED CHANGES
    # ========================================================================

    async def _inject_synthetic_examples(self) -> str:
        """
        Fetch top 3 synthetic training examples from agent_training_examples table
        for Tailor Agent to use as in-context few-shot prompting.
        """
        try:
            session = AsyncSessionLocal()
            query = text("""
                SELECT input_text, output_text 
                FROM agent_training_examples 
                WHERE agent_type = 'tailor' AND is_synthetic = true 
                ORDER BY rating DESC 
                LIMIT 3
            """)
            result = await session.execute(query)
            examples = result.fetchall()
            await session.close()
            
            if not examples:
                return ""
            
            examples_text = "\n\nFEW-SHOT EXAMPLES:\n"
            for idx, (input_text, output_text) in enumerate(examples, 1):
                examples_text += f"\nExample {idx}:\nBefore:\n{input_text}\n\nAfter:\n{output_text}\n"
            
            return examples_text
        except Exception as e:
            logger.warning(f"[TAILOR] Failed to load synthetic examples: {e}")
            return ""

    async def _format_resume_sections(self, resume_text: str) -> Dict[str, Any]:
        """
        Parse free-form resume text and structure into 5 sections:
        Summary, Skills, Experience, Education, Projects
        
        Returns structured JSON ready for DOCX generation.
        """
        parser_prompt = f"""Parse this resume into structured JSON with these exact sections:
- summary: 2-3 sentence professional summary
- skills: list of 10-15 key skills
- experience: list of job entries with company, title, dates, bullets
- education: list of degrees
- projects: list of notable projects (if any)

Resume:
{resume_text}

Return ONLY valid JSON with this structure:
{{
    "summary": "...",
    "skills": ["skill1", "skill2", ...],
    "experience": [
        {{"company": "...", "title": "...", "dates": "...", "bullets": ["...", "..."]}}
    ],
    "education": [
        {{"degree": "...", "school": "...", "year": "..."}}
    ],
    "projects": [
        {{"name": "...", "description": "..."}}
    ]
}}"""

        try:
            text, usage = await self.call_gemini(parser_prompt, temperature=self.TEMPERATURE_SCORING, json_mode=True)
            result = json.loads(text)
            return result
        except Exception as e:
            logger.error(f"[TAILOR] Failed to parse resume into sections: {e}")
            # Fallback: return minimal structure
            return {
                "summary": "",
                "skills": [],
                "experience": [],
                "education": [],
                "projects": []
            }

    async def _estimate_ats_lift(self, original_resume: str, rewritten_resume: str, 
                                  job_description: str) -> Dict[str, Any]:
        """
        Estimate ATS score before/after rewrite and return improvement details.
        """
        # Score original resume
        orig_score_prompt = f"""Estimate ATS match score (0-100) for this resume against the job description.
Resume: {original_resume[:400]}
Job Description: {job_description[:400]}

Return JSON: {{"score": 80}}"""
        
        orig_text, _ = await self.call_gemini(orig_score_prompt, temperature=self.TEMPERATURE_SCORING, json_mode=True)
        try:
            orig_score = json.loads(orig_text)["score"]
        except:
            orig_score = 50

        # Score rewritten resume
        new_score_prompt = f"""Estimate ATS match score (0-100) for this resume against the job description.
Resume: {rewritten_resume[:400]}
Job Description: {job_description[:400]}

Return JSON: {{"score": 85}}"""
        
        new_text, _ = await self.call_gemini(new_score_prompt, temperature=self.TEMPERATURE_SCORING, json_mode=True)
        try:
            new_score = json.loads(new_text)["score"]
        except:
            new_score = 75

        lift = new_score - orig_score
        
        return {
            "before_score": orig_score,
            "after_score": new_score,
            "score_lift": lift,
            "lift_percentage": round((lift / max(orig_score, 1)) * 100, 1)
        }

    def _compute_tracked_changes(self, original_resume: str, rewritten_resume: str) -> List[Dict[str, str]]:
        """
        Compute line-by-line changes using difflib.SequenceMatcher.
        Returns list of change records: {original, rewritten, change_type}
        """
        orig_lines = original_resume.split('\n')
        new_lines = rewritten_resume.split('\n')
        
        matcher = SequenceMatcher(None, orig_lines, new_lines)
        changes = []
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                for orig, new in zip(orig_lines[i1:i2], new_lines[j1:j2]):
                    if orig.strip() and new.strip():
                        changes.append({
                            "original": orig.strip(),
                            "rewritten": new.strip(),
                            "type": "modified"
                        })
            elif tag == 'delete':
                for orig in orig_lines[i1:i2]:
                    if orig.strip():
                        changes.append({
                            "original": orig.strip(),
                            "rewritten": None,
                            "type": "removed"
                        })
            elif tag == 'insert':
                for new in new_lines[j1:j2]:
                    if new.strip():
                        changes.append({
                            "original": None,
                            "rewritten": new.strip(),
                            "type": "added"
                        })
        
        return changes

    async def invoke(self, input_dict: Dict[str, str]) -> str:
        """
        Main invoke method for the Tailor agent.
        Input dict should contain:
        - resume: User's resume text
        - job_description: Full job description
        - keywords_context: (Optional) Pre-audited keywords from Auditor service
        
        Returns: Tailored resume text
        """
        resume = input_dict.get("resume", "")
        job_description = input_dict.get("job_description", "")
        keywords_context = input_dict.get("keywords_context", "")
        
        logger.info("[TAILOR] Starting resume tailoring...")
        
        # If keywords are provided, weave them into the prompt
        prompt_injection = f"\n\n{keywords_context}" if keywords_context else ""
        
        # Rewrite resume with optional keyword injection
        result = await self._resume_rewriter_with_context(
            resume,
            job_description,
            keywords_context
        )
        
        logger.info("[TAILOR] Resume tailoring complete")
        return result.get("rewritten_resume", resume)

    async def _resume_rewriter_with_context(
        self,
        resume_text: str,
        job_description: str,
        keywords_context: str = ""
    ) -> Dict:
        """
        Enhanced resume rewriter that uses pre-audited keywords.
        """
        if not job_description:
            return {"rewritten_resume": resume_text, "key_alignments": [], "tracked_changes": []}

        examples = await self._inject_synthetic_examples()

        # Build enhanced prompt with keywords context
        enhanced_keywords_section = ""
        if keywords_context:
            enhanced_keywords_section = f"\n\nREQUIREMENT ANALYSIS (from Job Auditor):\n{keywords_context}\n\nPrioritize these exact keywords and skills in your rewrite."

        prompt = f"""You are an expert resume writer specializing in ATS optimization. Rewrite this resume to align perfectly with the job description.

{examples}

Current Resume:
{resume_text}

Job Description:
{job_description[:2000]}

{enhanced_keywords_section}

CRITICAL RULES:
1. Keep all factual experience, dates, and titles UNCHANGED.
2. Reorder bullets and adjust wording to highlight required JD skills.
3. Add quantifiable metrics (%, $, #) to 80% of bullets.
4. Start each bullet with a strong action verb (e.g., Built, Designed, Optimized).
5. Match exact keywords from the JD and auditor analysis wherever possible.
6. Use STAR method (Situation-Task-Action-Result) for achievement bullets.
7. Output ONLY valid JSON (no markdown, no explanations).

Return this exact JSON structure:
{{
    "rewritten_resume": "Full resume with sections...",
    "key_alignments": ["alignment 1", "alignment 2", "alignment 3"],
    "alternative_summaries": [
        "Alternative summary 1...",
        "Alternative summary 2...",
        "Alternative summary 3..."
    ]
}}"""
        
        model_text, usage = await self.call_gemini(prompt, temperature=self.TEMPERATURE_CREATIVE, json_mode=True)

        try:
            result = json.loads(model_text)
            rewritten = result.get("rewritten_resume", resume_text)
            alignments = result.get("key_alignments", [])
            alternatives = result.get("alternative_summaries", [])
        except Exception as e:
            logger.warning(f"[TAILOR] JSON parse failed, using fallback: {e}")
            rewritten = model_text
            alignments = ["Resume tailored to job description"]
            alternatives = []

        # Compute tracked changes
        tracked_changes = self._compute_tracked_changes(resume_text, rewritten)

        return {
            "rewritten_resume": rewritten,
            "key_alignments": alignments,
            "tracked_changes": tracked_changes,
            "alternative_summaries": alternatives
        }


# ============================================================================
# Factory function
# ============================================================================

def create_tailor_agent(user_id: str = "system", session_id: str = None) -> AutoTailorAgent:
    """
    Factory function to create and return an AutoTailorAgent instance.
    Use for simple cases where full AIAgent lifecycle is not needed.
    """
    return AutoTailorAgent(
        user_id=user_id,
        session_id=session_id,
        telemetry_tracker=None
    )
