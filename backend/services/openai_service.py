"""OpenAI service for ATS analysis."""

import json
import os
from typing import Dict, List

from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load environment variables
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables")

client = AsyncOpenAI(api_key=api_key)


async def analyze_resume_match(resume_text: str, job_description: str) -> Dict:
    """
    Analyze resume against job description using OpenAI.

    Returns:
        dict with keys: score (int 0-100), missing_skills (list), advice (str)
    """
    prompt = f"""
You are an expert ATS (Applicant Tracking System) analyst. Analyze the provided resume against the job description.

Resume:
{resume_text}

Job Description:
{job_description}

Provide a JSON response with exactly these keys:
- score: An integer from 0 to 100 representing overall match percentage
- missing_skills: A list of important skills or keywords from the job description that are missing from the resume
- advice: A brief paragraph of feedback on how well the resume matches the job requirements

Return only valid JSON, no additional text.
"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )

        content = response.choices[0].message.content.strip()
        result = json.loads(content)

        # Validate structure
        if not all(key in result for key in ["score", "missing_skills", "advice"]):
            raise ValueError("Invalid response structure")

        # Ensure score is int 0-100
        result["score"] = max(0, min(100, int(result["score"])))

        # Ensure missing_skills is list
        if not isinstance(result["missing_skills"], list):
            result["missing_skills"] = []

        # Ensure advice is string
        if not isinstance(result["advice"], str):
            result["advice"] = "Advice not available."

        return result

    except Exception as e:
        # Fallback in case of error
        return {
            "score": 0,
            "missing_skills": [],
            "advice": f"Error during analysis: {str(e)}"
        }