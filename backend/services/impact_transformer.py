"""
Impact Transformer Service - AI-Powered Resume Bullet Rewriting

Transforms weak resume bullets into STAR-formatted, quantifiable achievements.
Uses instruction fine-tuning prompts to maximize impact without expensive LLM calls.

Examples:
  "Worked on features" → "Spearheaded feature development for 2M+ DAU app, improving retention by 18%"
  "Fixed bugs" → "Resolved critical performance bottleneck affecting 15% of sessions, reducing crash rate to <0.1%"
"""

import logging
import json
from typing import List, Dict, Optional
import google.generativeai as genai
import os
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))


class BulletRewriteRequest(BaseModel):
    """Request to rewrite a single resume bullet"""
    original_bullet: str = Field(description="Current resume bullet")
    skill_context: str = Field(description="Required skill/tool/context from JD")
    bullet_category: str = Field(default="achievement", description="achievement, responsibility, skill")


class BulletRewriteResult(BaseModel):
    """Result of bullet rewriting"""
    original: str
    rewritten: str
    star_method_applied: bool
    metrics_added: List[str] = Field(default_factory=list)
    impact_level: str = Field(default="high", description="low, medium, high")


class ImpactTransformerService:
    """
    Transforms generic resume bullets into high-impact STAR method statements.
    
    STAR Method:
    - Situation: The context
    - Task: What was needed
    - Action: What you did
    - Result: Measurable outcome
    """

    # Template prompts for bullet transformation
    ACHIEVEMENT_PROMPT = """Transform this resume bullet into a high-impact STAR achievement statement.
Input: {bullet}
Context: This achievement should demonstrate proficiency with: {skill_context}

Rules:
1. Use action verbs (Spearheaded, Engineered, Architected, Optimized, etc.)
2. Add specific metrics (%, $, time saved, users impacted)
3. Follow STAR method (Situation → Task → Action → Result)
4. Keep under 2 lines
5. Make it quantifiable and impressive

Output a single rewritten bullet:"""

    RESPONSIBILITY_PROMPT = """Reframe this job responsibility as a measurable achievement.
Input: {bullet}
Context: Emphasize experience with: {skill_context}

Rules:
1. Change passive to active voice
2. Add impact metrics if possible
3. Show scale (users, teams, systems affected)
4. Make it outcome-focused

Output a single rewritten bullet:"""

    # Known metrics patterns to inject if missing
    METRIC_TEMPLATES = {
        "performance": ["reduced latency by {x}%", "improved performance by {x}x", "decreased load time by {x}ms"],
        "scale": ["served {x}M+ users", "handled {x}K requests/sec", "processed {x}GB of data daily"],
        "quality": ["reduced bugs by {x}%", "improved test coverage to {x}%", "achieved {x}% uptime"],
        "features": ["shipped {x} features used by {x}K users", "drove adoption to {x}% of user base"],
        "team": ["led team of {x} engineers", "mentored {x} junior developers", "reduced onboarding time by {x}%"],
        "time": ["reduced development time by {x}%", "shipped {x} weeks early", "cut deployment time to {x} min"],
    }

    def __init__(self):
        logger.info("[IMPACT] Impact Transformer initialized")

    async def transform_bullet(
        self,
        bullet: str,
        skill_context: str,
        category: str = "achievement"
    ) -> BulletRewriteResult:
        """
        Transform a single resume bullet into high-impact STAR format.
        """
        try:
            logger.debug(f"[IMPACT] Transforming: {bullet[:60]}...")
            
            # Select prompt based on category
            if category == "responsibility":
                prompt = self.RESPONSIBILITY_PROMPT
            else:
                prompt = self.ACHIEVEMENT_PROMPT
            
            # Format prompt with context
            formatted_prompt = prompt.format(
                bullet=bullet,
                skill_context=skill_context
            )
            
            # Call Gemini for transformation
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(formatted_prompt)
            rewritten = response.text.strip()
            
            # Analyze improvements
            has_metrics = self._has_metrics(rewritten)
            impact_level = self._assess_impact(rewritten)
            metrics_added = self._extract_metrics(rewritten)
            
            logger.debug(f"[IMPACT] Rewritten: {rewritten[:60]}...")
            
            return BulletRewriteResult(
                original=bullet,
                rewritten=rewritten,
                star_method_applied=self._has_star_method(rewritten),
                metrics_added=metrics_added,
                impact_level=impact_level
            )
            
        except Exception as e:
            logger.error(f"[IMPACT] Transform failed: {e}")
            return BulletRewriteResult(
                original=bullet,
                rewritten=bullet,  # Fallback to original
                star_method_applied=False
            )

    async def transform_resume_section(
        self,
        experience_section: str,
        job_skills: List[str]
    ) -> Dict[str, List[BulletRewriteResult]]:
        """
        Transform all bullets in an experience section.
        Batches transformations for efficiency.
        """
        try:
            logger.info("[IMPACT] Transforming experience section...")
            
            # Parse bullets (assume one per line)
            bullets = [b.strip() for b in experience_section.split('\n') if b.strip() and b.startswith('-')]
            
            results = []
            for bullet in bullets:
                # Match bullet to most relevant skill
                most_relevant_skill = self._find_most_relevant_skill(bullet, job_skills)
                
                result = await self.transform_bullet(
                    bullet,
                    most_relevant_skill,
                    category="achievement"
                )
                results.append(result)
            
            logger.info(f"[IMPACT] Transformed {len(results)} bullets")
            
            return {
                "transformed_bullets": results,
                "section_impact": "high" if all(r.impact_level == "high" for r in results) else "medium"
            }
            
        except Exception as e:
            logger.error(f"[IMPACT] Section transform failed: {e}")
            return {"transformed_bullets": [], "section_impact": "unknown"}

    def _has_star_method(self, bullet: str) -> bool:
        """Check if bullet roughly follows STAR method structure"""
        star_indicators = {
            "situation": ["when", "for", "at", "in the", "where"],
            "task": ["needed", "required", "had to", "tasked", "faced"],
            "action": ["built", "created", "developed", "engineered", "architected", "spearheaded", "led", "drove"],
            "result": ["increased", "reduced", "improved", "achieved", "resulted in", "%", "x", "growth"],
        }
        
        bullet_lower = bullet.lower()
        score = 0
        for element, keywords in star_indicators.items():
            if any(kw in bullet_lower for kw in keywords):
                score += 1
        
        return score >= 3  # At least 3 STAR elements

    def _has_metrics(self, bullet: str) -> bool:
        """Check if bullet contains quantifiable metrics"""
        import re
        
        metric_patterns = [
            r'\d+%',  # Percentages
            r'\d+x',  # Multipliers
            r'\$\d+',  # Dollar amounts
            r'\d+[KMB]',  # Scaled numbers
            r'\d+\s*(users|sessions|requests|queries|ms|sec)',
        ]
        
        for pattern in metric_patterns:
            if re.search(pattern, bullet):
                return True
        return False

    def _extract_metrics(self, bullet: str) -> List[str]:
        """Extract all metrics from a bullet"""
        import re
        
        patterns = [
            r'\d+%',
            r'\d+x',
            r'\$[\d,]+',
            r'\d+[KMB]',
            r'\d+\s*(users|sessions|requests|queries|ms|sec)',
        ]
        
        metrics = []
        for pattern in patterns:
            matches = re.findall(pattern, bullet)
            metrics.extend(matches)
        
        return list(set(metrics))

    def _assess_impact(self, bullet: str) -> str:
        """Assess overall impact level of the bullet"""
        impact_keywords = {
            "high": [
                "spearheaded", "architected", "led", "drove", "owned",
                "reduced by 50%", "increased by 100%", "millions", "platform",
                "system-wide", "company-wide"
            ],
            "medium": [
                "developed", "implemented", "created", "built",
                "improved", "optimized", "contributed",
                "10-50%", "thousands"
            ],
            "low": [
                "worked on", "helped with", "assisted", "participated",
                "some", "several"
            ]
        }
        
        bullet_lower = bullet.lower()
        
        for level in ["high", "medium", "low"]:
            if any(kw in bullet_lower for kw in impact_keywords[level]):
                return level
        
        # Fallback: count metrics
        if self._has_metrics(bullet):
            return "medium"
        return "low"

    def _find_most_relevant_skill(self, bullet: str, job_skills: List[str]) -> str:
        """Find the most relevant job skill for a bullet"""
        bullet_lower = bullet.lower()
        
        for skill in job_skills:
            if skill.lower() in bullet_lower:
                return skill
        
        # If no exact match, return first skill
        return job_skills[0] if job_skills else "general professional experience"


def get_impact_transformer() -> ImpactTransformerService:
    """Get or create singleton ImpactTransformerService instance"""
    return ImpactTransformerService()
