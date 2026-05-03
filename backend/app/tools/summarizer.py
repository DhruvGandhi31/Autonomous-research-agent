# backend/app/tools/summarizer.py
from typing import Dict, Any, List
import re
from datetime import datetime

from tools.base_tool import BaseTool, ToolResult
from services.llm_service import llm_service
from loguru import logger

class SummarizerTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="summarizer", 
            description="Summarize documents, articles, and research content with key insights"
        )
        
        self.summary_prompt = """You are an expert research summarizer. Summarize the given content with these requirements:

1. **Executive Summary**: 2-3 sentences capturing the main point
2. **Key Points**: 3-5 bullet points of most important information
3. **Insights**: Notable patterns, trends, or surprising findings
4. **Credibility**: Assess the reliability and quality of the source
5. **Relevance**: How well does this relate to the research topic "{topic}"

Content to summarize:
{content}

Provide a structured, analytical summary that would be valuable for research purposes."""

        self.batch_summary_prompt = """You are analyzing multiple sources for research on "{topic}". 

Synthesize the following summaries into a coherent analysis:

{summaries}

Provide:
1. **Synthesis**: Common themes and patterns across sources
2. **Conflicting Views**: Any disagreements or contradictions found
3. **Research Gaps**: What important questions remain unanswered
4. **Source Quality**: Overall assessment of source credibility
5. **Key Insights**: Most important findings for understanding {topic}

Focus on creating a coherent narrative that advances understanding of the research topic."""
    
    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """Execute summarization"""
        try:
            content = parameters.get("content", "")
            documents = parameters.get("documents", [])
            topic = parameters.get("topic", "research topic")
            summary_type = parameters.get("type", "single")  # "single" or "batch"
            
            if summary_type == "batch" and documents:
                return await self._batch_summarize(documents, topic)
            elif content:
                return await self._single_summarize(content, topic)
            else:
                return ToolResult(success=False, error="No content or documents provided")
                
        except Exception as e:
            logger.error(f"Summarization error: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def _single_summarize(self, content: str, topic: str) -> ToolResult:
        """Summarize a single piece of content"""
        try:
            # Truncate content if too long
            max_content_length = 6000
            if len(content) > max_content_length:
                content = content[:max_content_length] + "..."
                logger.info("Content truncated for summarization")
            
            summary = await llm_service.generate(
                prompt=self.summary_prompt.format(content=content, topic=topic),
                system_prompt="You are an expert research analyst. Provide structured, insightful summaries.",
                temperature=0.3
            )
            
            # Parse summary into structured format
            structured_summary = self._parse_summary(summary)
            
            return ToolResult(
                success=True,
                data={
                    "summary": summary,
                    "structured": structured_summary,
                    "original_length": len(content),
                    "summary_length": len(summary),
                    "compression_ratio": len(summary) / len(content),
                    "topic": topic,
                    "created_at": datetime.now().isoformat()
                },
                summaries=[summary]
            )
            
        except Exception as e:
            logger.error(f"Single summarization error: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def _batch_summarize(self, documents: List[Dict[str, Any]], topic: str) -> ToolResult:
        """Summarize multiple documents and synthesize insights"""
        try:
            individual_summaries = []
            
            # Summarize each document individually first
            for i, doc in enumerate(documents):
                content = doc.get("content", "")
                if content:
                    summary_result = await self._single_summarize(content, topic)
                    if summary_result.success:
                        individual_summaries.append({
                            "source": doc.get("url", f"Document {i+1}"),
                            "title": doc.get("title", "Untitled"),
                            "summary": summary_result.data["summary"]
                        })
            
            if not individual_summaries:
                return ToolResult(success=False, error="No documents could be summarized")
            
            # Create synthesis of all summaries
            summaries_text = "\n\n".join([
                f"Source: {s['title']}\n{s['summary']}" for s in individual_summaries
            ])
            
            synthesis = await llm_service.generate(
                prompt=self.batch_summary_prompt.format(
                    summaries=summaries_text, 
                    topic=topic
                ),
                system_prompt="You are a research synthesis expert. Create coherent analyses from multiple sources.",
                temperature=0.4
            )
            
            return ToolResult(
                success=True,
                data={
                    "synthesis": synthesis,
                    "individual_summaries": individual_summaries,
                    "total_documents": len(documents),
                    "summarized_documents": len(individual_summaries),
                    "topic": topic,
                    "created_at": datetime.now().isoformat()
                },
                summaries=[synthesis] + [s["summary"] for s in individual_summaries]
            )
            
        except Exception as e:
            logger.error(f"Batch summarization error: {e}")
            return ToolResult(success=False, error=str(e))
    
    def _parse_summary(self, summary_text: str) -> Dict[str, Any]:
        """Parse summary text into structured components"""
        try:
            structured = {
                "executive_summary": "",
                "key_points": [],
                "insights": [],
                "credibility_assessment": "",
                "relevance_score": "medium"
            }
            
            # Use regex to extract sections
            sections = {
                "executive_summary": r"(?:Executive Summary|Summary):\s*(.*?)(?=\n.*?:|$)",
                "key_points": r"(?:Key Points|Main Points):\s*(.*?)(?=\n.*?:|$)",
                "insights": r"(?:Insights|Findings):\s*(.*?)(?=\n.*?:|$)",
                "credibility": r"(?:Credibility|Reliability):\s*(.*?)(?=\n.*?:|$)"
            }
            
            for key, pattern in sections.items():
                match = re.search(pattern, summary_text, re.DOTALL | re.IGNORECASE)
                if match:
                    content = match.group(1).strip()
                    if key == "key_points":
                        # Extract bullet points
                        points = re.findall(r'[•\-\*]\s*(.*?)(?=\n|$)', content)
                        structured["key_points"] = [p.strip() for p in points if p.strip()]
                    elif key == "insights":
                        insights = re.findall(r'[•\-\*]\s*(.*?)(?=\n|$)', content)
                        structured["insights"] = [i.strip() for i in insights if i.strip()]
                    elif key == "credibility":
                        structured["credibility_assessment"] = content
                    else:
                        structured["executive_summary"] = content
            
            # If no structured content found, use the whole summary as executive summary
            if not structured["executive_summary"]:
                structured["executive_summary"] = summary_text[:500]
            
            return structured
            
        except Exception as e:
            logger.warning(f"Error parsing summary structure: {e}")
            return {
                "executive_summary": summary_text[:500],
                "key_points": [],
                "insights": [],
                "credibility_assessment": "Unknown",
                "relevance_score": "medium"
            }
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Text content to summarize"
                },
                "documents": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of documents to batch summarize"
                },
                "topic": {
                    "type": "string",
                    "description": "Research topic for context"
                },
                "type": {
                    "type": "string",
                    "enum": ["single", "batch"],
                    "default": "single",
                    "description": "Type of summarization"
                }
            }
        }
    
    async def close(self):
        """Close resources"""
        if hasattr(self, 'session') and self.session:
            await self.session.close()

# Global summarizer tool instance
summarizer_tool = SummarizerTool()