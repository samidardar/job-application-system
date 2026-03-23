import logging
import time
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.agent_run import AgentRun, AgentStatusEnum

logger = logging.getLogger(__name__)


class BaseAgent:
    name: str = "base"

    def __init__(self, db: AsyncSession, pipeline_run_id: uuid.UUID | None, user_id: uuid.UUID):
        self.db = db
        self.pipeline_run_id = pipeline_run_id
        self.user_id = user_id
        self._agent_run: AgentRun | None = None
        self._start_time: float = 0

    async def _start_run(self, job_id: uuid.UUID | None = None, input_data: dict | None = None) -> AgentRun | None:
        self._start_time = time.time()
        if self.pipeline_run_id is None:
            logger.info(f"[{self.name}] Starting (no pipeline_run) | job_id={job_id}")
            return None
        agent_run = AgentRun(
            pipeline_run_id=self.pipeline_run_id,
            user_id=self.user_id,
            job_id=job_id,
            agent_name=self.name,
            status=AgentStatusEnum.RUNNING,
            input_data=input_data or {},
            started_at=datetime.utcnow(),
        )
        self.db.add(agent_run)
        await self.db.flush()
        self._agent_run = agent_run
        logger.info(f"[{self.name}] Starting | job_id={job_id}")
        return agent_run

    async def _finish_run(
        self,
        status: AgentStatusEnum,
        output_data: dict | None = None,
        error_message: str | None = None,
        claude_tokens_used: int = 0,
    ) -> None:
        if not self._agent_run:
            return
        duration = time.time() - self._start_time
        self._agent_run.status = status
        self._agent_run.output_data = output_data or {}
        self._agent_run.error_message = error_message
        self._agent_run.claude_tokens_used = claude_tokens_used
        self._agent_run.duration_seconds = round(duration, 2)
        self._agent_run.completed_at = datetime.utcnow()
        await self.db.flush()
        logger.info(f"[{self.name}] Finished | status={status} | duration={duration:.1f}s | tokens={claude_tokens_used}")
