"""
Fine-Tuning Pipeline Service

Manages the full lifecycle of fine-tuning jobs:
  1. Export high-quality training examples from agent_feedback_log
  2. Convert to instruction format (Alpaca/ShareGPT JSONL)
  3. Upload to Together AI and launch LoRA fine-tuning
  4. Monitor job progress and auto-deploy on completion
  5. Serve active model IDs so agent_base can route inference
"""

import os
import json
import asyncio
import aiohttp
import random
import tempfile
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db_models import AgentFeedbackLog, FineTuningJob, ModelDeployment
from backend.services.agent_training import AgentTrainingPipeline

logger = logging.getLogger(__name__)

# Warn early if Together AI key is missing
if not os.getenv("TOGETHER_API_KEY"):
    logger.warning(
        "[FINE-TUNE] TOGETHER_API_KEY not set — fine-tuning and fine-tuned inference will be disabled"
    )

# Max time a training job can stay in 'training' before we mark it timed out
MAX_TRAINING_HOURS = 12


class FineTuningService:
    """Manages fine-tuning jobs across providers."""

    TOGETHER_BASE_URL = "https://api.together.xyz/v1"

    # Default LoRA hyperparameters
    DEFAULT_HYPERPARAMS = {
        "lora_r": 16,
        "lora_alpha": 16,
        "lora_dropout": 0.05,
        "epochs": 3,
        "learning_rate": 2e-4,
        "batch_size": 4,
        "warmup_ratio": 0.1,
    }

    # Minimum examples required to start fine-tuning
    MIN_EXAMPLES = 100

    def __init__(self, db: AsyncSession):
        self.db = db
        self.training_pipeline = AgentTrainingPipeline(db)

    # ------------------------------------------------------------------
    # Auth header helper (read key at call time, not module load)
    # ------------------------------------------------------------------

    @staticmethod
    def _together_headers() -> dict:
        key = os.getenv("TOGETHER_API_KEY", "")
        if not key:
            raise ValueError("TOGETHER_API_KEY env var is not set")
        return {
            "Authorization": f"Bearer {key}",
        }

    # ------------------------------------------------------------------
    # Readiness check
    # ------------------------------------------------------------------

    async def should_trigger_fine_tuning(self, agent_type: str) -> dict:
        """Check if enough new high-quality examples exist since last deploy."""

        last_job_stmt = (
            select(FineTuningJob)
            .where(
                and_(
                    FineTuningJob.agent_type == agent_type,
                    FineTuningJob.status == "deployed",
                )
            )
            .order_by(FineTuningJob.completed_at.desc())
            .limit(1)
        )
        result = await self.db.execute(last_job_stmt)
        last_job = result.scalar_one_or_none()

        cutoff = last_job.completed_at if last_job else datetime.min

        count_stmt = select(func.count(AgentFeedbackLog.id)).where(
            and_(
                AgentFeedbackLog.agent_type == agent_type,
                AgentFeedbackLog.rating >= 4,
                AgentFeedbackLog.created_at > cutoff,
            )
        )
        result = await self.db.execute(count_stmt)
        new_examples = result.scalar() or 0

        total_stmt = select(func.count(AgentFeedbackLog.id)).where(
            and_(
                AgentFeedbackLog.agent_type == agent_type,
                AgentFeedbackLog.rating >= 4,
            )
        )
        total_result = await self.db.execute(total_stmt)
        total_examples = total_result.scalar() or 0

        return {
            "ready": new_examples >= self.MIN_EXAMPLES,
            "new_since_last_deploy": new_examples,
            "total_high_quality": total_examples,
            "minimum_required": self.MIN_EXAMPLES,
        }

    # ------------------------------------------------------------------
    # Data preparation
    # ------------------------------------------------------------------

    async def prepare_training_data(
        self, agent_type: str, format: str = "alpaca"
    ) -> tuple:
        """Export and format training examples into train/val JSONL tempfiles.

        Returns (train_path, val_path, total_count).  If fewer than 10 examples,
        val_path will be None (all data used for training).
        """

        stmt = (
            select(AgentFeedbackLog)
            .where(
                and_(
                    AgentFeedbackLog.agent_type == agent_type,
                    AgentFeedbackLog.rating >= 4,
                    AgentFeedbackLog.is_synthetic == False,  # noqa: E712 – real user data only
                )
            )
            .order_by(AgentFeedbackLog.rating.desc())
            .limit(2000)
        )
        result = await self.db.execute(stmt)
        examples = list(result.scalars().all())

        if not examples:
            raise ValueError(f"No high-quality training examples found for {agent_type}")

        formatted = []
        for ex in examples:
            if format == "sharegpt":
                formatted.append(self._to_sharegpt_format(ex))
            else:
                formatted.append(self._to_alpaca_format(ex))

        # 80/20 train/val split (shuffle to avoid ordering bias)
        shuffled = formatted.copy()
        random.shuffle(shuffled)
        split_idx = max(1, int(len(shuffled) * 0.8))

        train_data = shuffled[:split_idx]
        val_data = shuffled[split_idx:] if len(shuffled) >= 10 else None

        train_path = self._write_jsonl(train_data)
        val_path = self._write_jsonl(val_data) if val_data else None

        return train_path, val_path, len(formatted)

    @staticmethod
    def _write_jsonl(items: List[dict]) -> str:
        """Write items to a temp JSONL file and return its path."""
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for item in items:
                    f.write(json.dumps(item) + "\n")
        except BaseException:
            os.unlink(path)
            raise
        return path

    @staticmethod
    def _safe_unlink(path: Optional[str]):
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _to_alpaca_format(self, example: AgentFeedbackLog) -> dict:
        instruction = self._build_instruction(
            example.agent_type, example.input_context or {}
        )
        output = example.user_edited_output or example.agent_output
        return {
            "instruction": instruction,
            "input": "",
            "output": json.dumps(output) if isinstance(output, dict) else str(output),
        }

    def _to_sharegpt_format(self, example: AgentFeedbackLog) -> dict:
        instruction = self._build_instruction(
            example.agent_type, example.input_context or {}
        )
        output = example.user_edited_output or example.agent_output
        output_str = json.dumps(output) if isinstance(output, dict) else str(output)
        return {
            "conversations": [
                {"from": "human", "value": instruction},
                {"from": "gpt", "value": output_str},
            ]
        }

    def _build_instruction(self, agent_type: str, ctx: dict) -> str:
        resume = (ctx.get("resume_text") or "")[:2000]
        jd = (ctx.get("job_description") or "")[:2000]

        prompts = {
            "tailor": (
                "You are an expert resume optimization AI. Given a resume and job description, "
                "rewrite the resume to maximize ATS score while maintaining truthfulness.\n\n"
                f"Resume: {resume}\nJob Description: {jd}\n\n"
                "Optimize the resume sections for ATS compatibility. "
                "Return a JSON with 'optimized_resume' and 'changes_summary'."
            ),
            "coach": (
                "You are a career coach AI. Analyze the resume against the job description "
                "and provide actionable feedback.\n\n"
                f"Resume: {resume}\nJob Description: {jd}\n\n"
                "Return a JSON with 'strengths', 'gaps', 'actionable_tips', and 'overall_fit_score'."
            ),
            "cover_letter": (
                "You are a professional cover letter writer. Write a compelling cover letter "
                "tailored to the job and company.\n\n"
                f"Resume: {resume[:1500]}\nJob Description: {jd[:1500]}\n"
                f"Company: {ctx.get('company', '')}\n"
                f"Hiring Manager: {ctx.get('hiring_manager', '')}\n\n"
                "Return a JSON with 'cover_letter' and 'key_highlights'."
            ),
            "interview": (
                "You are an interview coach. Generate relevant interview questions and model answers.\n\n"
                f"Job Description: {jd}\nResume: {resume[:1500]}\n\n"
                "Return a JSON with 'technical_questions', 'behavioral_questions', and 'preparation_tips'."
            ),
            "negotiation": (
                "You are a salary negotiation coach. Provide negotiation strategy and scripts.\n\n"
                f"Job Offer: {json.dumps(ctx.get('offer_details', {}))}\n"
                f"Market Context: {ctx.get('location', '')} - {ctx.get('role', '')}\n\n"
                "Return a JSON with 'salary_range', 'negotiation_strategy', "
                "'talking_points', and 'counter_offer_script'."
            ),
        }
        return prompts.get(
            agent_type,
            f"Agent type: {agent_type}\nContext: {json.dumps(ctx)[:2000]}",
        )

    # ------------------------------------------------------------------
    # Start fine-tuning job
    # ------------------------------------------------------------------

    async def start_fine_tuning_job(
        self,
        agent_type: str,
        provider: str = "together",
        base_model: str = "meta-llama/Llama-3.2-3B-Instruct",
        hyperparameters: Optional[Dict] = None,
        created_by=None,
    ) -> FineTuningJob:
        """Prepare data, upload, and launch a fine-tuning job."""

        train_path, val_path, examples_count = await self.prepare_training_data(
            agent_type, format="alpaca"
        )

        job = FineTuningJob(
            provider=provider,
            base_model=base_model,
            agent_type=agent_type,
            status="uploading",
            examples_count=examples_count,
            hyperparameters=hyperparameters or self.DEFAULT_HYPERPARAMS,
            created_by=created_by,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)

        try:
            if provider == "together":
                job = await self._start_together_job(job, train_path, val_path)
            else:
                raise ValueError(f"Unsupported provider: {provider}")
            return job
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)[:500]
            await self.db.commit()
            raise
        finally:
            self._safe_unlink(train_path)
            self._safe_unlink(val_path)

    async def _upload_file_to_together(
        self, session: aiohttp.ClientSession, headers: dict, filepath: str, purpose: str
    ) -> str:
        """Upload a single file to Together AI, return file_id."""
        form = aiohttp.FormData()
        form.add_field(
            "file",
            open(filepath, "rb"),
            filename=os.path.basename(filepath),
            content_type="application/jsonl",
        )
        form.add_field("purpose", purpose)

        async with session.post(
            f"{self.TOGETHER_BASE_URL}/files",
            headers=headers,
            data=form,
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise RuntimeError(f"File upload failed ({resp.status}): {error}")
            file_info = await resp.json()
            return file_info["id"]

    async def _start_together_job(
        self, job: FineTuningJob, train_path: str, val_path: Optional[str]
    ) -> FineTuningJob:
        """Upload train (+ optional val) file and start fine-tuning on Together AI."""

        headers = self._together_headers()

        async with aiohttp.ClientSession() as session:
            # Step 1: Upload training JSONL
            train_file_id = await self._upload_file_to_together(
                session, headers, train_path, "fine-tune"
            )

            # Step 1b: Upload validation JSONL (if we have one)
            val_file_id = None
            if val_path:
                val_file_id = await self._upload_file_to_together(
                    session, headers, val_path, "fine-tune"
                )

            job.training_file_url = train_file_id
            job.status = "training"
            job.started_at = datetime.utcnow()
            await self.db.commit()

            # Step 2: Start fine-tuning
            hp = job.hyperparameters or self.DEFAULT_HYPERPARAMS
            payload: dict = {
                "training_file": train_file_id,
                "model": job.base_model,
                "hyperparameters": {
                    "lora_r": hp.get("lora_r", 16),
                    "lora_alpha": hp.get("lora_alpha", 16),
                    "lora_dropout": hp.get("lora_dropout", 0.05),
                    "epochs": hp.get("epochs", 3),
                    "learning_rate": hp.get("learning_rate", 2e-4),
                    "batch_size": hp.get("batch_size", 4),
                    "warmup_ratio": hp.get("warmup_ratio", 0.1),
                },
                "suffix": f"ats-{job.agent_type}-{datetime.utcnow().strftime('%Y%m%d')}",
            }
            if val_file_id:
                payload["validation_file"] = val_file_id

            async with session.post(
                f"{self.TOGETHER_BASE_URL}/fine-tunes",
                headers={**headers, "Content-Type": "application/json"},
                json=payload,
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"Fine-tune creation failed ({resp.status}): {error}")
                ft_info = await resp.json()
                job.provider_job_id = ft_info["id"]

            await self.db.commit()
            return job

    # ------------------------------------------------------------------
    # Background monitoring (called from scheduler, not asyncio.create_task)
    # ------------------------------------------------------------------

    async def poll_job_status(self, job_id) -> FineTuningJob:
        """Check a single in-progress job's status with the provider.

        Also enforces a hard timeout (MAX_TRAINING_HOURS) — if a job
        has been in 'training' longer than that, mark it as timed out.
        """

        stmt = select(FineTuningJob).where(FineTuningJob.id == job_id)
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job or job.status != "training":
            return job

        # Hard timeout guard
        if job.started_at and (
            datetime.utcnow() - job.started_at > timedelta(hours=MAX_TRAINING_HOURS)
        ):
            job.status = "timeout"
            job.error_message = f"Training exceeded {MAX_TRAINING_HOURS}h limit"
            job.completed_at = datetime.utcnow()
            await self.db.commit()
            logger.error(f"[FINE-TUNE] Job {job.id} timed out after {MAX_TRAINING_HOURS}h")
            return job

        if job.provider == "together":
            await self._poll_together_job(job)

        return job

    async def _poll_together_job(self, job: FineTuningJob):
        """Poll Together AI for fine-tuning status update."""

        headers = self._together_headers()

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.TOGETHER_BASE_URL}/fine-tunes/{job.provider_job_id}",
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[FINE-TUNE] Poll failed for job {job.id}: {resp.status}")
                    return
                data = await resp.json()

            provider_status = data.get("status", "")

            if provider_status == "completed":
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                job.fine_tuned_model_id = data.get("fine_tuned_model")
                job.training_metrics = data.get("training_metrics", {})
                job.cost_usd = data.get("cost")
                await self.db.commit()

                # Auto-deploy
                await self._deploy_model(job)
                logger.info(
                    f"[FINE-TUNE] Job {job.id} completed → deployed model {job.fine_tuned_model_id}"
                )

            elif provider_status in ("failed", "cancelled"):
                job.status = provider_status
                job.error_message = data.get("error", "Unknown error")
                job.completed_at = datetime.utcnow()
                await self.db.commit()
                logger.error(f"[FINE-TUNE] Job {job.id} {provider_status}: {job.error_message}")

    # ------------------------------------------------------------------
    # Deployment management
    # ------------------------------------------------------------------

    async def _deploy_model(self, job: FineTuningJob):
        """Deploy a completed fine-tuned model, deactivating any previous one."""

        # Deactivate previous active deployments for this agent type
        await self.db.execute(
            update(ModelDeployment)
            .where(
                and_(
                    ModelDeployment.agent_type == job.agent_type,
                    ModelDeployment.is_active == True,  # noqa: E712
                )
            )
            .values(is_active=False, deactivated_at=datetime.utcnow())
        )

        deployment = ModelDeployment(
            fine_tuning_job_id=job.id,
            agent_type=job.agent_type,
            model_id=job.fine_tuned_model_id,
            provider=job.provider,
            deployment_type="primary",
            is_active=True,
        )
        self.db.add(deployment)

        job.status = "deployed"
        job.is_active = True
        await self.db.commit()

    async def deploy_model_manually(self, job: FineTuningJob):
        """Public wrapper for manual deploy from routes."""
        if job.status != "completed":
            raise ValueError(f"Cannot deploy job with status: {job.status}")
        await self._deploy_model(job)

    # ------------------------------------------------------------------
    # Active model lookup (called by agent_base.py at inference time)
    # ------------------------------------------------------------------

    async def get_active_model(self, agent_type: str) -> Optional[str]:
        """Return the model_id of the currently deployed fine-tuned model, or None.

        Supports gradual rollout via `rollout_percentage`.  When < 100, a
        random draw decides whether this request is routed to the fine-tuned
        model or falls back to the base model.
        """

        stmt = (
            select(ModelDeployment)
            .where(
                and_(
                    ModelDeployment.agent_type == agent_type,
                    ModelDeployment.is_active == True,  # noqa: E712
                )
            )
            .order_by(ModelDeployment.deployed_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        deployment = result.scalar_one_or_none()
        if not deployment:
            return None

        # A/B rollout: respect rollout_percentage (default 100 = always use)
        rollout = deployment.rollout_percentage if deployment.rollout_percentage is not None else 100
        if rollout < 100 and random.randint(1, 100) > rollout:
            return None  # This request falls back to the base model

        return deployment.model_id

    # ------------------------------------------------------------------
    # Listing & evaluation
    # ------------------------------------------------------------------

    async def list_fine_tuning_jobs(
        self, agent_type: Optional[str] = None
    ) -> List[FineTuningJob]:
        query = select(FineTuningJob).order_by(FineTuningJob.created_at.desc())
        if agent_type:
            query = query.where(FineTuningJob.agent_type == agent_type)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def evaluate_model_performance(self, deployment_id) -> dict:
        """Evaluate a deployed model's recent performance metrics."""

        stmt = select(ModelDeployment).where(ModelDeployment.id == deployment_id)
        result = await self.db.execute(stmt)
        deployment = result.scalar_one_or_none()
        if not deployment:
            raise ValueError("Deployment not found")

        metrics = await self.training_pipeline.get_agent_performance_metrics(
            deployment.agent_type, days=30
        )

        deployment.performance_metrics = metrics
        await self.db.commit()
        return metrics
