"""
ResearchAgent — orchestrates the full enterprise research pipeline:

  plan → execute tasks (concurrent, dependency-aware) →
  process + index documents (DocumentProcessor → HybridRetriever) →
  RAG synthesis (HyDE → rerank → MMR → LLM → self-critique) →
  final report with inline citations + confidence score
"""
import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger

from core.memory import memory_manager
from core.planner import task_planner
from services.llm_service import llm_service
from tools.base_tool import BaseTool


class AgentState(Enum):
    IDLE = "idle"
    PLANNING = "planning"
    RESEARCHING = "researching"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"
    ERROR = "error"


class ResearchAgent:
    def __init__(self):
        self.memory = memory_manager
        self.planner = task_planner
        self.tools: Dict[str, BaseTool] = {}
        self.state = AgentState.IDLE
        self._research_states: Dict[str, AgentState] = {}

    # ── Tool registry ──────────────────────────────────────────────────

    def register_tool(self, name: str, tool: BaseTool):
        self.tools[name] = tool
        logger.info(f"Registered tool: {name}")

    # ── Main entry point ───────────────────────────────────────────────

    async def conduct_research(
        self,
        topic: str,
        requirements: Optional[Dict[str, Any]] = None,
        research_id: Optional[str] = None,
    ) -> str:
        """
        Run the full research pipeline.
        Accepts an optional pre-assigned research_id so the route can return
        it to the client before the background task starts.
        Returns research_id when complete.
        """
        if not research_id:
            research_id = f"research_{uuid.uuid4().hex[:12]}"

        self._research_states[research_id] = AgentState.PLANNING
        self.state = AgentState.PLANNING

        try:
            # ── 1. Store initial context ──────────────────────────────
            await self.memory.store_context(
                research_id,
                {
                    "topic": topic,
                    "requirements": requirements or {},
                    "status": "planning",
                    "started_at": datetime.now().isoformat(),
                    "research_id": research_id,
                },
            )

            # ── 2. Generate research plan ─────────────────────────────
            logger.info(f"[{research_id}] Planning research for: {topic}")
            plan = await self.planner.create_research_plan(topic, requirements)
            await self.memory.store_plan(research_id, plan)
            logger.info(f"[{research_id}] Plan: {len(plan['tasks'])} tasks")

            # ── 3. Execute tasks ──────────────────────────────────────
            self._research_states[research_id] = AgentState.RESEARCHING
            self.state = AgentState.RESEARCHING
            await self._update_status(research_id, "researching")

            await self._execute_tasks(research_id, plan["tasks"], topic)

            # ── 4. Process & index all collected content ──────────────
            await self._update_status(research_id, "indexing")
            await self._process_and_index(research_id, topic)

            # ── 5. RAG synthesis ──────────────────────────────────────
            self._research_states[research_id] = AgentState.SYNTHESIZING
            self.state = AgentState.SYNTHESIZING
            await self._update_status(research_id, "synthesizing")
            logger.info(f"[{research_id}] Synthesising with RAG pipeline")

            report_data = await self._rag_synthesize(research_id, topic)
            await self.memory.store_insight(
                research_id,
                {
                    "type": "final_report",
                    "report": report_data.get("answer", ""),
                    "citations": report_data.get("citations", []),
                    "confidence": report_data.get("confidence", 0.0),
                    "verified": report_data.get("verified", False),
                    "critique": report_data.get("critique"),
                    "generated_at": datetime.now().isoformat(),
                },
            )

            # ── 6. Mark complete ──────────────────────────────────────
            self._research_states[research_id] = AgentState.COMPLETE
            self.state = AgentState.COMPLETE
            await self._update_status(
                research_id,
                "complete",
                {"completed_at": datetime.now().isoformat()},
            )
            logger.info(f"[{research_id}] Research complete")
            return research_id

        except Exception as e:
            logger.error(f"[{research_id}] Research failed: {e}")
            self._research_states[research_id] = AgentState.ERROR
            self.state = AgentState.ERROR
            await self._update_status(research_id, "error", {"error": str(e)})
            raise

    # ── Task execution ─────────────────────────────────────────────────

    async def _execute_tasks(
        self, research_id: str, tasks: List[Dict], topic: str
    ):
        """
        Run tasks respecting dependency order.
        Tasks with no unresolved dependencies execute as concurrent batches
        (capped at 3 to respect upstream rate limits).
        """
        completed: set[str] = set()
        remaining = list(tasks)

        while remaining:
            ready = [
                t
                for t in remaining
                if all(dep in completed for dep in (t.get("dependencies") or []))
            ]
            if not ready:
                ready = [remaining[0]]

            batch = ready[:3]
            results = await asyncio.gather(
                *[self._execute_single_task(research_id, t, topic) for t in batch],
                return_exceptions=True,
            )
            for task, result in zip(batch, results):
                completed.add(task["id"])
                remaining.remove(task)
                if isinstance(result, Exception):
                    logger.warning(f"[{research_id}] Task {task['id']} failed: {result}")

    async def _execute_single_task(
        self, research_id: str, task: Dict, topic: str
    ) -> Dict[str, Any]:
        tool_name = task.get("tool", "web_search")
        tool = self.tools.get(tool_name) or self.tools.get("web_search")

        if not tool:
            logger.warning(f"No tool '{tool_name}' and no web_search fallback; skipping")
            return {"skipped": True}

        params = dict(task.get("parameters") or {})
        params.setdefault("query", task.get("description", topic))
        params.setdefault("topic", topic)

        logger.info(f"[{research_id}] Task '{task['name']}' → {tool.name}")

        try:
            result = await tool.execute(params)
            record = {
                "task_id": task["id"],
                "task_name": task["name"],
                "tool": tool.name,
                "success": result.success,
                "data": result.data,
                "sources": result.sources,
                "summaries": result.summaries,
                "error": result.error,
                "executed_at": datetime.now().isoformat(),
            }
            await self.memory.store_task_result(research_id, task["id"], record)
            return record
        except Exception as e:
            logger.error(f"Task {task['id']} exception: {e}")
            await self.memory.store_task_result(
                research_id, task["id"],
                {"task_id": task["id"], "task_name": task["name"], "success": False, "error": str(e)},
            )
            raise

    # ── Document processing + indexing ─────────────────────────────────

    async def _process_and_index(self, research_id: str, topic: str):
        """
        Pull all raw content from task results, run through DocumentProcessor,
        and index chunks into the HybridRetriever (Qdrant + tantivy).
        """
        try:
            from services.document_processor import document_processor
            from services.retrieval.hybrid_retriever import hybrid_retriever
        except ImportError as e:
            logger.warning(f"Document processing/indexing skipped (import error): {e}")
            return

        task_results = await self.memory.get_task_results(research_id)
        raw_docs: list[dict] = []

        for tr in task_results:
            if not tr.get("success"):
                continue
            data = tr.get("data") or {}

            # web_search detailed_content
            for item in (data.get("detailed_content") or []):
                if item.get("content"):
                    raw_docs.append({
                        "url": item.get("url", ""),
                        "title": item.get("title", ""),
                        "content": item["content"],
                        "crawled_at": datetime.now().timestamp(),
                        "source": "web_search",
                        "keyword_hits": 3,
                    })

            # academic_search results
            for item in (data.get("results") or []):
                snippet = item.get("snippet", "") or item.get("abstract", "")
                if snippet:
                    raw_docs.append({
                        "url": item.get("url", ""),
                        "title": item.get("title", ""),
                        "content": f"{item.get('title', '')}\n\n{snippet}",
                        "crawled_at": datetime.now().timestamp(),
                        "source": item.get("source", "academic"),
                        "keyword_hits": 5,   # Academic sources get a relevance boost
                    })

        all_chunks = []
        for raw in raw_docs:
            chunks = document_processor.process(raw)
            all_chunks.extend(chunks)

        if all_chunks:
            indexed = await hybrid_retriever.index_documents(all_chunks)
            logger.info(f"[{research_id}] Indexed {indexed} chunks ({len(raw_docs)} raw docs)")
        else:
            logger.warning(f"[{research_id}] No chunks to index after document processing")

    # ── RAG synthesis ──────────────────────────────────────────────────

    async def _rag_synthesize(self, research_id: str, topic: str) -> Dict[str, Any]:
        """
        Use RAGPipeline for final synthesis.
        Falls back to the simple LLM synthesis if RAG has no indexed data.
        """
        try:
            from services.rag_pipeline import rag_pipeline
            response = await rag_pipeline.query(topic)

            if response.sources_used > 0:
                logger.info(
                    f"[{research_id}] RAG synthesis: {response.sources_used} sources, "
                    f"confidence={response.confidence:.2f}, verified={response.verified}"
                )
                return {
                    "answer": response.answer,
                    "citations": response.citations,
                    "confidence": response.confidence,
                    "verified": response.verified,
                    "critique": response.critique,
                }
        except Exception as e:
            logger.warning(f"RAG pipeline failed, falling back to direct synthesis: {e}")

        # Fallback: direct LLM synthesis from task results
        fallback_answer = await self._fallback_synthesize(research_id, topic)
        return {
            "answer": fallback_answer,
            "citations": [],
            "confidence": 0.0,
            "verified": False,
            "critique": None,
        }

    async def _fallback_synthesize(self, research_id: str, topic: str) -> str:
        """Simple LLM synthesis without retrieval — used when RAG has no data."""
        task_results = await self.memory.get_task_results(research_id)
        all_sources: List[Dict] = []
        content_blocks: List[str] = []

        for tr in task_results:
            if not tr.get("success"):
                continue
            all_sources.extend(tr.get("sources") or [])
            for s in (tr.get("summaries") or [])[:3]:
                if s:
                    content_blocks.append(s)
            data = tr.get("data") or {}
            for item in (data.get("results") or [])[:5]:
                if item.get("snippet"):
                    content_blocks.append(f"{item.get('title','')}\n{item['snippet']}")

        if not content_blocks:
            return f"Research on '{topic}' could not gather sufficient data."

        seen: set[str] = set()
        unique_sources = []
        for s in all_sources:
            if s.get("url") and s["url"] not in seen:
                seen.add(s["url"])
                unique_sources.append(s)

        findings = "\n\n---\n\n".join(content_blocks[:12])
        sources_text = "\n".join(
            f"[{i+1}] {s.get('title','Untitled')} — {s.get('url','')}"
            for i, s in enumerate(unique_sources[:25])
        )

        _FALLBACK_PROMPT = """\
Write a comprehensive research report on: {topic}

Findings:
{findings}

Sources:
{sources}

Structure:
## Executive Summary
## Key Findings (cite sources as [N])
## Analysis
## Conclusion
## References"""

        return await llm_service.generate(
            _FALLBACK_PROMPT.format(topic=topic, findings=findings[:9000], sources=sources_text),
            system_prompt="You are an expert research analyst. Write structured, evidence-based reports.",
            temperature=0.2,
        )

    # ── Status / results accessors ─────────────────────────────────────

    async def get_research_status(self, research_id: str) -> Dict[str, Any]:
        context = await self.memory.get_research_context(research_id)
        if not context:
            return {"error": "Research session not found"}

        plan = await self.memory.get_research_plan(research_id)
        task_results = await self.memory.get_task_results(research_id)
        total_tasks = len(plan.get("tasks", [])) if plan else 0
        completed_tasks = len(task_results)

        return {
            "research_id": research_id,
            "topic": context.get("topic"),
            "status": context.get("status"),
            "agent_state": self._research_states.get(research_id, AgentState.IDLE).value,
            "started_at": context.get("started_at"),
            "completed_at": context.get("completed_at"),
            "error": context.get("error"),
            "progress": {
                "completed_tasks": completed_tasks,
                "total_tasks": total_tasks,
                "percentage": round(completed_tasks / total_tasks * 100) if total_tasks else 0,
            },
        }

    async def get_research_results(self, research_id: str) -> Dict[str, Any]:
        context = await self.memory.get_research_context(research_id)
        if not context:
            return {"error": "Research session not found"}

        # Load the final report insight
        report: Optional[str] = None
        citations: list = []
        confidence: float = 0.0
        verified: bool = False
        critique: Optional[str] = None

        for f in self.memory.memory_dir.glob(f"{research_id}_insight_*.json"):
            item = await self.memory._load_memory_item(f.stem)
            if item and item.content.get("type") == "final_report":
                report = item.content.get("report")
                citations = item.content.get("citations", [])
                confidence = item.content.get("confidence", 0.0)
                verified = item.content.get("verified", False)
                critique = item.content.get("critique")
                break

        task_results = await self.memory.get_task_results(research_id)
        all_sources: List[Dict] = []
        for tr in task_results:
            all_sources.extend(tr.get("sources") or [])

        seen: set[str] = set()
        unique_sources: List[Dict] = []
        for s in all_sources:
            if s.get("url") and s["url"] not in seen:
                seen.add(s["url"])
                unique_sources.append(s)
        unique_sources.sort(key=lambda s: s.get("credibility_score", 0), reverse=True)

        return {
            "research_id": research_id,
            "topic": context.get("topic"),
            "status": context.get("status"),
            "report": report,
            "citations": citations,
            "confidence": confidence,
            "verified": verified,
            "critique": critique,
            "sources": unique_sources[:30],
            "total_sources": len(unique_sources),
            "task_count": len(task_results),
            "started_at": context.get("started_at"),
            "completed_at": context.get("completed_at"),
        }

    # ── Helpers ────────────────────────────────────────────────────────

    async def _update_status(
        self, research_id: str, status: str, extra: Optional[Dict] = None
    ):
        context = await self.memory.get_research_context(research_id)
        if context:
            context["status"] = status
            if extra:
                context.update(extra)
            await self.memory.store_context(research_id, context)


research_agent = ResearchAgent()
