"""
Academic search tool — queries arXiv, Semantic Scholar, and Wikipedia concurrently.
No API keys required. Free-tier rate limits apply to Semantic Scholar (~100 req/5 min).
"""
import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import quote_plus

import aiohttp
from loguru import logger

from config.settings import settings
from tools.base_tool import BaseTool, ToolResult

_ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


class AcademicSearchTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="academic_search",
            description=(
                "Search academic databases (arXiv, Semantic Scholar) and Wikipedia. "
                "Returns papers with credibility scores and citation counts."
            ),
        )
        self.session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------ #
    #  Public interface                                                    #
    # ------------------------------------------------------------------ #

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        query = parameters.get("query", "").strip()
        sources = parameters.get("sources", ["arxiv", "semantic_scholar", "wikipedia", "google_scholar"])
        max_results = int(parameters.get("max_results", 5))

        if not query:
            return ToolResult(success=False, error="query parameter is required")

        await self._ensure_session()

        tasks = []
        if "arxiv" in sources:
            tasks.append(self._search_arxiv(query, max_results))
        if "semantic_scholar" in sources:
            tasks.append(self._search_semantic_scholar(query, max_results))
        if "wikipedia" in sources:
            tasks.append(self._search_wikipedia(query, min(2, max_results)))
        if "google_scholar" in sources and settings.serpapi_key:
            tasks.append(self._search_google_scholar(query, max_results))

        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: List[Dict[str, Any]] = []
        for result in gathered:
            if isinstance(result, list):
                all_results.extend(result)

        # Sort by credibility desc
        all_results.sort(key=lambda r: r.get("credibility_score", 0), reverse=True)

        return ToolResult(
            success=True,
            data={
                "query": query,
                "results": all_results,
                "total": len(all_results),
                "retrieved_at": datetime.now().isoformat(),
            },
            sources=[
                {
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "source": r.get("source", ""),
                    "type": r.get("type", "academic"),
                    "credibility_score": r.get("credibility_score", 0.5),
                }
                for r in all_results
            ],
            summaries=[
                r["snippet"] for r in all_results if r.get("snippet")
            ],
        )

    # ------------------------------------------------------------------ #
    #  arXiv                                                               #
    # ------------------------------------------------------------------ #

    async def _search_arxiv(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        url = (
            f"http://export.arxiv.org/api/query"
            f"?search_query=all:{quote_plus(query)}"
            f"&start=0&max_results={max_results}"
            f"&sortBy=relevance&sortOrder=descending"
        )
        for attempt in range(3):
            try:
                async with self.session.get(url) as resp:
                    if resp.status == 429:
                        wait = int(resp.headers.get("Retry-After", 5 * (attempt + 1)))
                        logger.warning(f"arXiv rate-limited (attempt {attempt + 1}/3); retrying in {wait}s")
                        await asyncio.sleep(wait)
                        continue
                    if resp.status != 200:
                        logger.warning(f"arXiv returned {resp.status}")
                        return []
                    text = await resp.text()
                    return self._parse_arxiv(text)
            except Exception as e:
                logger.warning(f"arXiv error (attempt {attempt + 1}/3): {e}")
                if attempt < 2:
                    await asyncio.sleep(3)  # arXiv docs recommend 3s between calls
        return []

    def _parse_arxiv(self, xml_text: str) -> List[Dict[str, Any]]:
        try:
            root = ET.fromstring(xml_text)
            results = []
            for entry in root.findall("atom:entry", _ARXIV_NS):
                title_el = entry.find("atom:title", _ARXIV_NS)
                summary_el = entry.find("atom:summary", _ARXIV_NS)
                id_el = entry.find("atom:id", _ARXIV_NS)
                published_el = entry.find("atom:published", _ARXIV_NS)
                authors = [
                    a.find("atom:name", _ARXIV_NS).text
                    for a in entry.findall("atom:author", _ARXIV_NS)
                    if a.find("atom:name", _ARXIV_NS) is not None
                ]
                if title_el is None or id_el is None:
                    continue
                results.append({
                    "title": title_el.text.strip().replace("\n", " "),
                    "url": id_el.text.strip(),
                    "snippet": summary_el.text.strip()[:600] if summary_el is not None else "",
                    "authors": authors[:3],
                    "published": published_el.text if published_el is not None else "",
                    "source": "arXiv",
                    "type": "academic_paper",
                    "credibility_score": 0.85,
                })
            return results
        except Exception as e:
            logger.warning(f"arXiv parse error: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  Semantic Scholar                                                    #
    # ------------------------------------------------------------------ #

    async def _search_semantic_scholar(
        self, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        fields = "title,abstract,url,year,authors,citationCount,venue"
        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/search"
            f"?query={quote_plus(query)}&limit={max_results}&fields={fields}"
        )
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"Semantic Scholar returned {resp.status}")
                    return []
                data = await resp.json()
        except Exception as e:
            logger.warning(f"Semantic Scholar search error: {e}")
            return []

        results = []
        for paper in data.get("data", []):
            citations = paper.get("citationCount") or 0
            # credibility scales with citation count, capped at 0.95
            credibility = min(0.95, 0.60 + min(citations / 500, 1.0) * 0.35)
            paper_id = paper.get("paperId", "")
            results.append({
                "title": paper.get("title", ""),
                "url": paper.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}",
                "snippet": (paper.get("abstract") or "")[:600],
                "authors": [a.get("name", "") for a in (paper.get("authors") or [])[:3]],
                "year": paper.get("year"),
                "citations": citations,
                "venue": paper.get("venue", ""),
                "source": "Semantic Scholar",
                "type": "academic_paper",
                "credibility_score": credibility,
            })
        return results

    # ------------------------------------------------------------------ #
    #  Wikipedia                                                           #
    # ------------------------------------------------------------------ #

    async def _search_wikipedia(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        url = (
            f"https://en.wikipedia.org/w/api.php"
            f"?action=query&list=search&srsearch={quote_plus(query)}"
            f"&srlimit={max_results}&format=json"
        )
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception as e:
            logger.warning(f"Wikipedia search error: {e}")
            return []

        results = []
        for item in data.get("query", {}).get("search", []):
            title = item.get("title", "")
            results.append({
                "title": title,
                "url": f"https://en.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}",
                "snippet": _strip_html(item.get("snippet", ""))[:400],
                "source": "Wikipedia",
                "type": "encyclopedia",
                "credibility_score": 0.70,
            })
        return results

    # ------------------------------------------------------------------ #
    #  Google Scholar (via SerpApi)                                        #
    # ------------------------------------------------------------------ #

    async def _search_google_scholar(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        params = {
            "engine": "google_scholar",
            "q": query,
            "num": min(max_results, 10),  # SerpApi caps at 20; 10 is a safe ceiling
            "api_key": settings.serpapi_key,
            "as_vis": "1",               # exclude citation-only stub entries
        }
        try:
            async with self.session.get("https://serpapi.com/search", params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"SerpApi returned {resp.status}")
                    return []
                data = await resp.json()
        except Exception as e:
            logger.warning(f"Google Scholar search error: {e}")
            return []

        results = []
        for item in data.get("organic_results", []):
            cited_by = (item.get("inline_links") or {}).get("cited_by", {}).get("total", 0) or 0
            # credibility baseline 0.65, scales with citation count up to 0.95
            credibility = min(0.95, 0.65 + min(cited_by / 500, 1.0) * 0.30)
            pub_info = item.get("publication_info") or {}
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": (item.get("snippet") or "")[:600],
                "authors": [a.get("name", "") for a in pub_info.get("authors", [])[:3]],
                "published": pub_info.get("summary", ""),
                "citations": cited_by,
                "source": "Google Scholar",
                "type": "academic_paper",
                "credibility_score": credibility,
            })
        return results

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    async def _ensure_session(self):
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "ResearchAgent/1.0 (academic research tool)"},
            )

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def _get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["arxiv", "semantic_scholar", "wikipedia", "google_scholar"],
                    },
                    "default": ["arxiv", "semantic_scholar", "wikipedia", "google_scholar"],
                },
                "max_results": {
                    "type": "integer",
                    "default": 5,
                    "description": "Results per source",
                },
            },
            "required": ["query"],
        }


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


academic_search_tool = AcademicSearchTool()
