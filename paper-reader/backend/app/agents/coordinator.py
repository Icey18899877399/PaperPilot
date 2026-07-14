from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.chat_agent import ChatAgent
from app.agents.paper_agent import PaperUnderstandingAgent
from app.agents.translation_agent import TranslationAgent


class CoordinatorAgent(BaseAgent):
    """Central entry point for routing tasks and preserving an auditable trace."""

    name = "coordinator-agent"

    def __init__(
        self,
        paper_agent: PaperUnderstandingAgent,
        translation_agent: TranslationAgent,
        chat_agent: ChatAgent,
        log_sink,
    ):
        super().__init__(log_sink)
        self.paper_agent = paper_agent
        self.translation_agent = translation_agent
        self.chat_agent = chat_agent

    async def run(self, task: str, **payload):
        trace_id = payload.pop("trace_id", self.new_trace_id())
        self.log(trace_id, "route", f"任务路由到{task}")
        if task == "guide":
            return await self.paper_agent.run(trace_id=trace_id, **payload)
        if task == "mind-map":
            return await self.paper_agent.run_mind_map(trace_id=trace_id, **payload)
        if task == "translate":
            return await self.translation_agent.run(trace_id=trace_id, **payload)
        if task == "translate-page":
            return await self.translation_agent.run_page(trace_id=trace_id, **payload)
        if task == "chat":
            return await self.chat_agent.run(trace_id=trace_id, **payload)
        raise ValueError(f"Unsupported agent task: {task}")
