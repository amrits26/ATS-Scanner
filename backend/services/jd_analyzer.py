"""Job description analyzer using OpenAI to extract structured ATS-relevant data."""

import json
import os
import re
from typing import Any

from openai import AsyncOpenAI

from ..models import JobDescriptionAnalysis
from ..utils.text_cleaner import clean_extracted_text


SYSTEM_JD = """You are an expert ATS (Applicant Tracking System) analyst. Your task is to extract structured data from job descriptions for resume optimization.
Return STRICT JSON only. No explanations. Do not fabricate experience or add content not present in the job description.
Output must be valid JSON with these exact keys: required_skills, preferred_skills, responsibilities, keywords, tools, experience_level.
Use empty arrays or empty string when a field is not found."""

USER_JD_TEMPLATE = """Extract ATS-relevant data from this job description. Return STRICT JSON only.

Job description:
---
{jd_text}
---

Return a single JSON object with:
- required_skills: list of required skills (exact phrases from JD)
- preferred_skills: list of preferred/nice-to-have skills
- responsibilities: list of key responsibilities
- keywords: list of important keywords for ATS (technical terms, tools, methodologies)
- tools: list of software/tools mentioned
- experience_level: e.g. "Entry", "Mid", "Senior", "Lead", or ""

Do not fabricate. Use only what is stated. Return STRICT JSON only. No markdown, no code block wrapper."""


async def analyze_job_description(jd_text: str) -> JobDescriptionAnalysis:
    """Call OpenAI to extract structured JD data. Handles empty/short text and JSON errors."""
    cleaned = clean_extracted_text(jd_text)
    if len(cleaned) < 20:
        return JobDescriptionAnalysis(
            experience_level="",
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return JobDescriptionAnalysis()

    client = AsyncOpenAI(api_key=api_key)
    try:
        resp = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_JD},
                {"role": "user", "content": USER_JD_TEMPLATE.format(jd_text=cleaned[:12000])},
            ],
            temperature=0.1,
        )
        content = (resp.choices[0].message.content or "").strip()
        content = _strip_json_block(content)
        data: dict[str, Any] = json.loads(content)
        return JobDescriptionAnalysis(
            required_skills=_list(data.get("required_skills")),
            preferred_skills=_list(data.get("preferred_skills")),
            responsibilities=_list(data.get("responsibilities")),
            keywords=_list(data.get("keywords")),
            tools=_list(data.get("tools")),
            experience_level=str(data.get("experience_level") or "").strip(),
        )
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        return JobDescriptionAnalysis()
    except Exception:
        return JobDescriptionAnalysis()


def _list(val: Any) -> list[str]:
    if not isinstance(val, list):
        return []
    return [str(x).strip() for x in val if x]


def _strip_json_block(text: str) -> str:
    """Remove markdown code block if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()
