import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from core.agent import research_agent
from core.memory import memory_manager
from tools.web_search import web_search_tool
from tools.summarizer import summarizer_tool
from services.llm_service import llm_service

router = APIRouter()


# ------------------------------------------------------------------ #
#  Request / Response models                                          #
# ------------------------------------------------------------------ #


class ResearchRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500)
    max_sources: int = Field(default=10, ge=1, le=50)
    include_academic: bool = Field(
        default=True,
        description="Include academic sources (arXiv, Semantic Scholar, Wikipedia)",
    )
    include_analysis: bool = Field(default=True)


class ResearchResponse(BaseModel):
    research_id: str
    topic: str
    status: str
    message: str


# ------------------------------------------------------------------ #
#  Core research endpoints                                            #
# ------------------------------------------------------------------ #


@router.post("/start", response_model=ResearchResponse)
async def start_research(
    request: ResearchRequest, background_tasks: BackgroundTasks
):
    """
    Start a research job. Returns immediately with a research_id.
    Poll /status/{research_id} to track progress.
    Results are available at /results/{research_id} once status is 'complete'.
    """
    research_id = f"research_{uuid.uuid4().hex[:12]}"
    requirements = {
        "max_sources": request.max_sources,
        "include_academic": request.include_academic,
        "include_analysis": request.include_analysis,
    }

    # Store initial context immediately so /status works right away
    await memory_manager.store_context(
        research_id,
        {
            "topic": request.topic,
            "requirements": requirements,
            "status": "queued",
            "started_at": datetime.now().isoformat(),
            "research_id": research_id,
        },
    )

    background_tasks.add_task(
        research_agent.conduct_research,
        request.topic,
        requirements,
        research_id,
    )

    logger.info(f"Research queued: {research_id} — '{request.topic}'")
    return ResearchResponse(
        research_id=research_id,
        topic=request.topic,
        status="queued",
        message=f"Research started. Poll /status/{research_id} for progress.",
    )


@router.get("/status/{research_id}")
async def get_research_status(research_id: str):
    status = await research_agent.get_research_status(research_id)
    if status.get("not_found"):
        raise HTTPException(status_code=404, detail="Research session not found")
    return status


@router.get("/results/{research_id}")
async def get_research_results(research_id: str):
    context = await memory_manager.get_research_context(research_id)
    if not context:
        raise HTTPException(status_code=404, detail="Research session not found")

    current_status = context.get("status")
    if current_status not in ("complete", "error"):
        raise HTTPException(
            status_code=202,
            detail=f"Research is still '{current_status}'. Try again later.",
        )

    if current_status == "error":
        return {
            "research_id": research_id,
            "topic": context.get("topic"),
            "status": "error",
            "error": context.get("error"),
        }

    return await research_agent.get_research_results(research_id)


@router.delete("/session/{research_id}")
async def delete_research_session(research_id: str):
    context = await memory_manager.get_research_context(research_id)
    if not context:
        raise HTTPException(status_code=404, detail="Research session not found")
    await memory_manager.clear_research_session(research_id)
    research_agent._research_states.pop(research_id, None)
    return {"message": f"Session {research_id} deleted successfully"}


@router.get("/sessions")
async def list_sessions():
    sessions = [
        {
            "research_id": rid,
            "topic": ctx.get("topic"),
            "status": ctx.get("status"),
            "started_at": ctx.get("started_at"),
        }
        for rid, ctx in memory_manager.active_sessions.items()
    ]
    return {"sessions": sessions, "total": len(sessions)}


# ------------------------------------------------------------------ #
#  Test / diagnostic endpoints                                        #
# ------------------------------------------------------------------ #


@router.get("/test/llm")
async def test_llm():
    try:
        response = await llm_service.generate(
            prompt="Respond with exactly: LLM connection successful",
            temperature=0.0,
        )
        return {"success": True, "response": response, "model": llm_service.model}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/search")
async def test_search(
    query: str = Query(..., description="Search query"),
    max_results: int = Query(default=5, ge=1, le=20),
):
    result = await web_search_tool.execute({"query": query, "max_results": max_results})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/test/academic")
async def test_academic_search(
    query: str = Query(..., description="Academic search query"),
    max_results: int = Query(default=3, ge=1, le=10),
):
    from tools.academic_search import academic_search_tool
    result = await academic_search_tool.execute({"query": query, "max_results": max_results})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/query")
async def rag_query(
    question: str = Query(..., description="Research question to answer from the knowledge base"),
    top_k: int = Query(default=12, ge=3, le=30),
):
    """
    Direct RAG query against the indexed knowledge base.
    Run /start first to populate the knowledge base with content.
    Returns answer with inline citations, confidence score, and self-critique.
    """
    from services.rag_pipeline import rag_pipeline
    from dataclasses import asdict
    response = await rag_pipeline.query(question, top_k=top_k)
    return {
        "question": question,
        "answer": response.answer,
        "citations": response.citations,
        "confidence": response.confidence,
        "sources_used": response.sources_used,
        "verified": response.verified,
        "critique": response.critique,
    }


@router.post("/crawl")
async def focused_crawl(
    background_tasks: BackgroundTasks,
    urls: list[str] = Query(..., description="Seed URLs to crawl"),
    topic: str = Query(..., description="Research topic (used for keyword relevance filtering)"),
    max_pages: int = Query(default=20, ge=1, le=100),
):
    """
    Trigger a focused crawl on given seed URLs.
    Crawled content is processed and indexed into the knowledge base.
    Use /query after crawling to ask questions against it.
    """
    import uuid
    crawl_id = f"crawl_{uuid.uuid4().hex[:8]}"

    async def _run_crawl():
        from tools.crawler.focused_crawler import AsyncFocusedCrawler
        from services.document_processor import document_processor
        from services.retrieval.hybrid_retriever import hybrid_retriever

        keywords = topic.lower().split()
        crawler = AsyncFocusedCrawler(
            topic_keywords=keywords,
            max_pages=max_pages,
            max_depth=2,
        )
        results = await crawler.crawl(urls)
        logger.info(f"[{crawl_id}] Crawled {len(results)} pages")

        all_chunks = []
        for page in results:
            raw = {
                "url": page.url,
                "title": page.title,
                "content": page.content,
                "crawled_at": page.crawled_at,
                "keyword_hits": page.keyword_hits,
                "source": "focused_crawl",
            }
            chunks = document_processor.process(raw)
            all_chunks.extend(chunks)

        if all_chunks:
            indexed = await hybrid_retriever.index_documents(all_chunks)
            logger.info(f"[{crawl_id}] Indexed {indexed} chunks from crawl")

    background_tasks.add_task(_run_crawl)
    return {
        "crawl_id": crawl_id,
        "status": "started",
        "seed_urls": urls,
        "topic": topic,
        "message": f"Crawling up to {max_pages} pages. Use /query to search after completion.",
    }


@router.post("/test/summarize")
async def test_summarize(
    content: str = Query(..., description="Text to summarize"),
    topic: str = Query(default="general", description="Research topic context"),
):
    result = await summarizer_tool.execute({"content": content, "topic": topic})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data
