"""ATS resume optimizer: rewrite resume with better keywords and wording (no fabrication)."""

import json
import os
import re
from typing import Any

from openai import AsyncOpenAI

from ..models import OptimizedResumeResponse, SectionImprovements
from ..utils.text_cleaner import clean_extracted_text


SYSTEM_OPT = """You are an expert ATS resume optimizer. You improve resumes for applicant tracking systems.
Rules:
- Do NOT fabricate experience, jobs, or skills. Only reword and restructure what is already in the resume.
- Do NOT add metrics or numbers that are not implied or stated in the original.
- Integrate job description keywords naturally where they genuinely apply to the candidate's experience.
- Use strong action verbs and ATS-friendly formatting (clear headings, consistent bullets).
- Return STRICT JSON only. No explanations."""

USER_OPT_TEMPLATE = """Optimize this resume for the given job description. Return STRICT JSON only.

Resume (original):
---
{resume_text}
---

Job description (excerpt for keyword context):
---
{jd_excerpt}
---

Return a single JSON object with:
- optimized_resume: full optimized resume text (plain text, use \\n for line breaks, clear sections like SUMMARY, EXPERIENCE, SKILLS, EDUCATION)
- section_improvements: object with keys summary, experience, skills (each string: brief note on what you improved in that section)

Do not fabricate. Only reword and add keywords that fit the candidate's actual experience. Return STRICT JSON only. No markdown wrapper."""


async def optimize_resume(resume_text: str, jd_text: str) -> OptimizedResumeResponse:
    """Rewrite resume for ATS using JD context. Preserves facts, improves wording and keyword alignment."""
    resume_clean = clean_extracted_text(resume_text)
    jd_clean = clean_extracted_text(jd_text)
    if len(resume_clean) < 30:
        return OptimizedResumeResponse(optimized_resume=resume_clean or resume_text)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return OptimizedResumeResponse(optimized_resume=resume_clean)

    jd_excerpt = (jd_clean[:6000]) if jd_clean else ""
    resume_excerpt = (resume_clean[:10000]) if resume_clean else resume_clean

    client = AsyncOpenAI(api_key=api_key)
    try:
        resp = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_OPT},
                {"role": "user", "content": USER_OPT_TEMPLATE.format(resume_text=resume_excerpt, jd_excerpt=jd_excerpt)},
            ],
            temperature=0.3,
        )
        content = (resp.choices[0].message.content or "").strip()
        content = _strip_json_block(content)
        data: dict[str, Any] = json.loads(content)
        opt_text = str(data.get("optimized_resume") or "").strip().replace("\\n", "\n")
        si = data.get("section_improvements") or {}
        return OptimizedResumeResponse(
            optimized_resume=opt_text or resume_clean,
            section_improvements=SectionImprovements(
                summary=str(si.get("summary") or ""),
                experience=str(si.get("experience") or ""),
                skills=str(si.get("skills") or ""),
            ),
        )
    except (json.JSONDecodeError, KeyError):
        return OptimizedResumeResponse(optimized_resume=resume_clean)
    except Exception:
        return OptimizedResumeResponse(optimized_resume=resume_clean)


def _strip_json_block(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()
