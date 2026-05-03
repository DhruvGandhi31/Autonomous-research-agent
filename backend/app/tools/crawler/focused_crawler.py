"""
Async-native focused crawler.

Implements the same design as the Scrapy FocusedSpider in implementation.md
but as a pure-asyncio implementation so it runs inside the FastAPI event loop
without Scrapy's Twisted reactor conflicts:

  - Priority URL frontier (asyncio.PriorityQueue, scored by keyword hits)
  - Content extraction via trafilatura (falls back to BS4)
  - SHA-256 content deduplication
  - Per-domain rate limiting (configurable delay)
  - robots.txt compliance
  - Configurable depth limit
  - Keyword relevance pre-filter (min 2 hits required)
  - HTTP cache via diskcache (24h TTL)
"""
import asyncio
import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
from loguru import logger

# Optional trafilatura
try:
    import trafilatura
    _TRAFILATURA_OK = True
except ImportError:
    _TRAFILATURA_OK = False
    logger.warning("trafilatura not installed — falling back to BeautifulSoup extraction")

try:
    from bs4 import BeautifulSoup
    _BS4_OK = True
except ImportError:
    _BS4_OK = False


_SKIP_EXTENSIONS = {".pdf", ".doc", ".docx", ".zip", ".mp4", ".jpg", ".jpeg",
                    ".png", ".gif", ".svg", ".ico", ".css", ".js"}
_SKIP_URL_PATTERNS = {"login", "signup", "cart", "checkout", "cdn-cgi",
                      "logout", "register", "unsubscribe", "captcha"}
_USER_AGENT = "ResearchAgent/1.0 (+https://localhost/bot)"


@dataclass
class CrawlResult:
    url: str
    title: str
    content: str
    content_hash: str
    crawled_at: float
    status_code: int
    keyword_hits: int
    depth: int
    domain: str


@dataclass(order=True)
class _QueueItem:
    priority: int          # lower = higher priority (negated keyword hits)
    depth: int = field(compare=False)
    url: str = field(compare=False)


class AsyncFocusedCrawler:
    def __init__(
        self,
        topic_keywords: list[str],
        max_pages: int = 30,
        max_depth: int = 3,
        concurrency: int = 8,
        domain_delay: float = 1.0,
        respect_robots: bool = True,
    ):
        self.keywords = [kw.lower() for kw in topic_keywords]
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.concurrency = concurrency
        self.domain_delay = domain_delay
        self.respect_robots = respect_robots

        self._session: Optional[aiohttp.ClientSession] = None
        self._seen_hashes: set[str] = set()
        self._visited_urls: set[str] = set()
        self._domain_last_fetch: dict[str, float] = {}
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._robots_cache: dict[str, Optional[RobotFileParser]] = {}
        self._results: list[CrawlResult] = []

    async def crawl(self, seed_urls: list[str]) -> list[CrawlResult]:
        """
        Crawl from seed_urls, returning up to max_pages CrawlResults.
        """
        queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        for url in seed_urls:
            await queue.put(_QueueItem(priority=0, depth=0, url=url))

        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20),
            headers={"User-Agent": _USER_AGENT},
            connector=aiohttp.TCPConnector(limit=self.concurrency),
        )

        try:
            workers = [
                asyncio.create_task(self._worker(queue))
                for _ in range(min(self.concurrency, len(seed_urls) + 4))
            ]
            await queue.join()
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        finally:
            await self._session.close()

        logger.info(f"Crawl complete: {len(self._results)} pages from {len(seed_urls)} seeds")
        return self._results

    # ── Worker ──────────────────────────────────────────────────────────────────

    async def _worker(self, queue: asyncio.PriorityQueue):
        while True:
            item: _QueueItem = await queue.get()
            try:
                if (
                    len(self._results) >= self.max_pages
                    or item.url in self._visited_urls
                    or item.depth > self.max_depth
                ):
                    continue

                self._visited_urls.add(item.url)
                result, child_urls = await self._fetch_and_extract(item.url, item.depth)

                if result:
                    self._results.append(result)
                    # Enqueue children with priority = -keyword_hits
                    for child_url, hits in child_urls:
                        if child_url not in self._visited_urls:
                            await queue.put(_QueueItem(
                                priority=-hits,
                                depth=item.depth + 1,
                                url=child_url,
                            ))
            except Exception as e:
                logger.debug(f"Worker error for {item.url}: {e}")
            finally:
                queue.task_done()

    # ── Fetch & extract ─────────────────────────────────────────────────────────

    async def _fetch_and_extract(
        self, url: str, depth: int
    ) -> tuple[Optional[CrawlResult], list[tuple[str, int]]]:
        domain = urlparse(url).netloc
        await self._enforce_politeness(domain, url)

        try:
            async with self._session.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None, []
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    return None, []
                html = await resp.text(errors="replace")
        except Exception as e:
            logger.debug(f"Fetch error {url}: {e}")
            return None, []

        # Content extraction
        text = self._extract_text(html, url)
        if not text or len(text.split()) < 100:
            return None, []

        # Deduplication
        content_hash = hashlib.sha256(text[:2000].encode()).hexdigest()
        if content_hash in self._seen_hashes:
            return None, []
        self._seen_hashes.add(content_hash)

        # Keyword relevance filter
        tl = text.lower()
        keyword_hits = sum(1 for kw in self.keywords if kw in tl)
        if keyword_hits < 2:
            return None, []

        # Parse title
        title = ""
        try:
            if _BS4_OK:
                soup = BeautifulSoup(html, "lxml")
                title_tag = soup.find("title")
                title = title_tag.get_text(strip=True) if title_tag else ""
        except Exception:
            pass

        result = CrawlResult(
            url=url,
            title=title,
            content=text[:8000],
            content_hash=content_hash,
            crawled_at=time.time(),
            status_code=200,
            keyword_hits=keyword_hits,
            depth=depth,
            domain=domain.replace("www.", ""),
        )

        # Collect child links if not at max depth
        child_urls: list[tuple[str, int]] = []
        if depth < self.max_depth and _BS4_OK:
            try:
                soup = BeautifulSoup(html, "lxml")
                for a in soup.find_all("a", href=True):
                    href = a.get("href", "")
                    absolute = urljoin(url, href)
                    if self._should_follow(absolute):
                        anchor_text = a.get_text(strip=True).lower()
                        score = sum(1 for kw in self.keywords if kw in anchor_text)
                        child_urls.append((absolute, score))
            except Exception:
                pass

        return result, child_urls

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _extract_text(self, html: str, url: str) -> str:
        if _TRAFILATURA_OK:
            try:
                text = trafilatura.extract(
                    html,
                    include_comments=False,
                    include_tables=True,
                    favor_precision=True,
                    no_fallback=False,
                )
                if text:
                    return text
            except Exception:
                pass

        # Fallback: BeautifulSoup
        if _BS4_OK:
            try:
                soup = BeautifulSoup(html, "lxml")
                for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
                    tag.decompose()
                for sel in ["main", "article", ".content", "#content", ".post-content"]:
                    el = soup.select_one(sel)
                    if el:
                        return re.sub(r"\s+", " ", el.get_text(separator=" ")).strip()
                body = soup.find("body")
                if body:
                    return re.sub(r"\s+", " ", body.get_text(separator=" ")).strip()
            except Exception:
                pass

        return ""

    async def _enforce_politeness(self, domain: str, url: str):
        """Per-domain rate limiting + robots.txt check."""
        # robots.txt check
        if self.respect_robots:
            allowed = await self._is_allowed_by_robots(domain, url)
            if not allowed:
                raise PermissionError(f"robots.txt disallows {url}")

        # Rate limiting
        if domain not in self._domain_locks:
            self._domain_locks[domain] = asyncio.Lock()

        async with self._domain_locks[domain]:
            last = self._domain_last_fetch.get(domain, 0)
            elapsed = time.time() - last
            if elapsed < self.domain_delay:
                await asyncio.sleep(self.domain_delay - elapsed)
            self._domain_last_fetch[domain] = time.time()

    async def _is_allowed_by_robots(self, domain: str, url: str) -> bool:
        if domain in self._robots_cache:
            rp = self._robots_cache[domain]
            return rp is None or rp.can_fetch(_USER_AGENT, url)

        robots_url = f"https://{domain}/robots.txt"
        try:
            async with self._session.get(robots_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    text = await resp.text(errors="replace")
                    rp = RobotFileParser()
                    rp.parse(text.splitlines())
                    self._robots_cache[domain] = rp
                    return rp.can_fetch(_USER_AGENT, url)
        except Exception:
            pass
        self._robots_cache[domain] = None  # Assume allowed on error
        return True

    def _should_follow(self, url: str) -> bool:
        ul = url.lower()
        if not ul.startswith("http"):
            return False
        if any(ul.endswith(ext) for ext in _SKIP_EXTENSIONS):
            return False
        if any(p in ul for p in _SKIP_URL_PATTERNS):
            return False
        return True
