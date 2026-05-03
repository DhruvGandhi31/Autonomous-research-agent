# backend/app/tools/web_search.py
import aiohttp
import asyncio
from typing import Dict, Any, List
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup
import re
from datetime import datetime

from tools.base_tool import BaseTool, ToolResult
from config.settings import settings
from loguru import logger

class WebSearchTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="web_search",
            description="Search the web using DuckDuckGo and extract relevant information"
        )
        self.session = None
        self.base_url = "https://html.duckduckgo.com/html/"
    
    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """Execute web search"""
        try:
            query = parameters.get("query", "")
            max_results = parameters.get("max_results", 10)
            
            if not query:
                return ToolResult(success=False, error="Query parameter is required")
            
            logger.info(f"Searching for: {query}")
            
            # Perform search
            search_results = await self._search_duckduckgo(query, max_results)
            
            if not search_results:
                return ToolResult(success=False, error="No search results found")
            
            # Extract and clean content from top results
            detailed_results = await self._extract_content_from_results(search_results[:5])
            
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "total_results": len(search_results),
                    "results": search_results,
                    "detailed_content": detailed_results
                },
                sources=[{"url": r["url"], "title": r["title"], "snippet": r["snippet"]} 
                        for r in search_results],
                summaries=[r.get("content", "")[:500] + "..." for r in detailed_results if r.get("content")]
            )
            
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def _search_duckduckgo(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Search DuckDuckGo and parse results"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=30),
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    }
                )
            
            # DuckDuckGo search URL
            search_url = f"{self.base_url}?q={quote_plus(query)}"
            
            async with self.session.get(search_url) as response:
                if response.status == 200:
                    html = await response.text()
                    return self._parse_duckduckgo_results(html, max_results)
                else:
                    logger.error(f"Search request failed with status: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return []
    
    def _parse_duckduckgo_results(self, html: str, max_results: int) -> List[Dict[str, Any]]:
        """Parse DuckDuckGo HTML results"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            results = []
            
            # Find result containers
            result_containers = soup.find_all('div', class_='result')
            
            for container in result_containers[:max_results]:
                try:
                    # Extract title and URL
                    title_elem = container.find('a', class_='result__a')
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    url = title_elem.get('href', '')
                    
                    # Extract snippet
                    snippet_elem = container.find('a', class_='result__snippet')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    
                    if title and url:
                        results.append({
                            "title": title,
                            "url": url,
                            "snippet": snippet,
                            "source": "DuckDuckGo",
                            "retrieved_at": datetime.now().isoformat()
                        })
                        
                except Exception as e:
                    logger.warning(f"Error parsing individual result: {e}")
                    continue
            
            logger.info(f"Parsed {len(results)} search results")
            return results
            
        except Exception as e:
            logger.error(f"Error parsing DuckDuckGo results: {e}")
            return []
    
    async def _extract_content_from_results(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract full content from search result URLs"""
        detailed_results = []
        
        for result in search_results:
            try:
                content = await self._fetch_page_content(result["url"])
                if content:
                    detailed_results.append({
                        **result,
                        "content": content,
                        "content_length": len(content),
                        "extracted_at": datetime.now().isoformat()
                    })
                    
                # Small delay to be respectful
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.warning(f"Failed to extract content from {result['url']}: {e}")
                # Still include the result without content
                detailed_results.append(result)
        
        return detailed_results
    
    async def _fetch_page_content(self, url: str) -> str:
        """Fetch and extract clean text content from a webpage"""
        try:
            async with self.session.get(url, timeout=15) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style", "nav", "footer", "aside"]):
                        script.decompose()
                    
                    # Try to find main content areas
                    content_selectors = [
                        'main', 'article', '.content', '.main-content', 
                        '.post-content', '.entry-content', '#content'
                    ]
                    
                    content_text = ""
                    for selector in content_selectors:
                        content_elem = soup.select_one(selector)
                        if content_elem:
                            content_text = content_elem.get_text(separator=' ', strip=True)
                            break
                    
                    # Fallback to body text if no main content found
                    if not content_text:
                        body = soup.find('body')
                        if body:
                            content_text = body.get_text(separator=' ', strip=True)
                    
                    # Clean up the text
                    content_text = re.sub(r'\s+', ' ', content_text)
                    content_text = content_text.strip()
                    
                    # Limit content length
                    return content_text[:8000] if content_text else ""
                    
        except Exception as e:
            logger.warning(f"Error fetching content from {url}: {e}")
            return ""
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "max_results": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of results to return"
                }
            },
            "required": ["query"]
        }
    
    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()

# Global web search tool instance
web_search_tool = WebSearchTool()