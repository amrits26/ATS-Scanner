#!/usr/bin/env python3
"""
Offline evaluation of Gemini prompt on labeled test set.
GAP 4 FIX: Uses async Gemini API calls for non-blocking performance.

Run: python scripts/evaluate_prompt.py
Expected: MAE < 10, Accuracy (±5) > 85%
"""

import json
import os
import asyncio
import logging
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv
import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))


# Sample test set (replace with real labeled data)
SAMPLE_TEST_SET = [
    {
        "resume": "Senior Software Engineer with 10 years experience in Python, AWS, and distributed systems. Led team of 8 engineers.",
        "jd": "We need a Senior Engineer with 5+ years Python and cloud experience",
        "expected_score": 85
    },
    {
        "resume": "Recent CS grad, built todo app in React during bootcamp",
        "jd": "Senior Principal Architect needed for distributed systems at scale",
        "expected_score": 15
    },
    {
        "resume": "Project Manager with 3 years experience in Agile and Scrum",
        "jd": "DevOps Engineer: Linux, Docker, Kubernetes, CI/CD pipelines",
        "expected_score": 20
    },
    {
        "resume": "Full-stack developer: React, Node.js, MongoDB, Docker, AWS, 6 years experience",
        "jd": "Full Stack Developer: React, Express, PostgreSQL, Docker required",
        "expected_score": 78
    },
    {
        "resume": "Data Scientist with 8 years in ML, Python, TensorFlow, SQL, Spark, statistical analysis",
        "jd": "Data Scientist: Python, SQL, scikit-learn, 5+ years required",
        "expected_score": 82
    },
    {
        "resume": "Marketing Manager with 5 years B2B SaaS experience",
        "jd": "Senior Backend Engineer: Golang, gRPC, Kubernetes, microservices",
        "expected_score": 10
    },
]


class EvaluatorPromptV1:
    """GAP 4 FIX: Async Gemini evaluator for non-blocking performance."""
    
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-1.5-flash')
    
    async def generate_content_async(self, prompt: str) -> str:
        """
        Non-blocking async call to Gemini API.
        
        Args:
            prompt: Full prompt with resume + JD
            
        Returns:
            Response text (should be JSON)
        """
        try:
            # Use asyncio to prevent blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(prompt)
            )
            return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return json.dumps({"score": 50})
    
    async def evaluate_single(self, test_case: Dict) -> Dict:
        """
        GAP 4 FIX: Async evaluation of single test case.
        
        Args:
            test_case: {"resume": "...", "jd": "...", "expected_score": 75}
            
        Returns:
            {"error": 5, "passed": true, "predicted": 75, "expected": 75}
        """
        prompt = f"""
        Analyze the resume match to the job description. Return ONLY valid JSON.
        
        Resume (first 500 words):
        {test_case['resume'][:500]}
        
        Job Description (first 500 words):
        {test_case['jd'][:500]}
        
        Return this exact JSON format (no markdown, no explanation):
        {{"score": <integer 0-100>}}
        """
        
        try:
            response_text = await self.generate_content_async(prompt)
            
            # Parse JSON response
            try:
                result = json.loads(response_text)
                predicted_score = result.get("score", 50)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON: {response_text[:100]}")
                predicted_score = 50
            
            expected_score = test_case["expected_score"]
            error = abs(predicted_score - expected_score)
            passed = error <= 5
            
            return {
                "predicted": predicted_score,
                "expected": expected_score,
                "error": error,
                "passed": passed
            }
        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            return {
                "predicted": 50,
                "expected": test_case["expected_score"],
                "error": abs(50 - test_case["expected_score"]),
                "passed": False
            }


async def evaluate_batch_async(evaluator: EvaluatorPromptV1, test_cases: List[Dict]) -> Dict:
    """
    GAP 4 FIX: Run multiple evaluations in parallel (non-blocking).
    
    Args:
        evaluator: EvaluatorPromptV1 instance
        test_cases: List of test cases
        
    Returns:
        Batch results with mae, accuracy, etc.
    """
    logger.info(f"Evaluating {len(test_cases)} test cases in parallel (async mode)...")
    
    # Run all tests in parallel
    tasks = [evaluator.evaluate_single(tc) for tc in test_cases]
    results = await asyncio.gather(*tasks)
    
    # Calculate statistics
    errors = [r["error"] for r in results]
    mae = sum(errors) / len(errors) if errors else 0
    passed = sum(1 for r in results if r["passed"])
    accuracy = passed / len(results) if results else 0
    
    return {
        "mae": round(mae, 2),
        "accuracy": round(accuracy * 100, 1),
        "passed": passed,
        "total": len(results),
        "results": results,
        "status": "✅ PASS" if accuracy > 0.85 else "❌ NEEDS WORK"
    }


async def main():
    """Main evaluation runner."""
    
    # Create test set if missing
    test_set_path = Path("scripts/test_set.json")
    if not test_set_path.exists():
        logger.info(f"Using sample test set ({len(SAMPLE_TEST_SET)} cases)")
        test_set = SAMPLE_TEST_SET
    else:
        with open(test_set_path) as f:
            test_set = json.load(f)
        logger.info(f"Loaded {len(test_set)} test cases from {test_set_path}")
    
    # Run evaluation
    evaluator = EvaluatorPromptV1()
    batch_results = await evaluate_batch_async(evaluator, test_set)
    
    # Display results
    print("\n" + "="*60)
    print("🧪 PROMPT EVALUATION RESULTS (ASYNC)")
    print("="*60)
    print(f"Total Test Cases: {batch_results['total']}")
    print(f"Passed (error ≤ 5): {batch_results['passed']}")
    print(f"Mean Absolute Error (MAE): {batch_results['mae']}")
    print(f"Accuracy (±5%): {batch_results['accuracy']}%")
    print(f"Status: {batch_results['status']}")
    print("="*60 + "\n")
    
    # Individual results
    print("📊 Individual Results:")
    for i, result in enumerate(batch_results["results"], 1):
        status = "✓" if result["passed"] else "✗"
        print(f"  [{i:2d}] {status} Expected: {result['expected']:3d}, Got: {result['predicted']:3d}, Error: {result['error']:2d}")
    
    # Save results
    output_path = Path("scripts/eval_results.json")
    with open(output_path, "w") as f:
        json.dump(batch_results, f, indent=2)
    logger.info(f"Results saved to {output_path}")
    
    # Return exit code
    return 0 if batch_results["status"].startswith("✅") else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
