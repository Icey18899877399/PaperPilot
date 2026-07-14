from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import uuid4

from app.models.schemas import AgentLog


class BaseAgent(ABC):
    name = "base-agent"

    def __init__(self, log_sink: list[AgentLog]):
        self.log_sink = log_sink

    def log(self, trace_id: str, action: str, detail: str) -> None:
        self.log_sink.append(
            AgentLog(
                trace_id=trace_id,
                agent=self.name,
                action=action,
                detail=detail,
            )
        )

    @staticmethod
    def new_trace_id() -> str:
        return uuid4().hex

    @abstractmethod
    async def run(self, *args, **kwargs):
        raise NotImplementedError

