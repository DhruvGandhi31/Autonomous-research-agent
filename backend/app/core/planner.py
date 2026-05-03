# backend/app/core/planner.py
from typing import Dict, Any, List
from datetime import datetime
import json
import uuid
from dataclasses import asdict, dataclass

from services.llm_service import llm_service
from loguru import logger

@dataclass
class ResearchTask:
    id: str
    name: str
    description: str
    tool: str
    parameters: Dict[str, Any]
    priority: int
    dependencies: List[str] = None
    estimated_time: int = 5  # minutes
    status: str = "pending"

class TaskPlanner:
    def __init__(self):
        self.planning_prompt = """You are a research planning AI. Given a research topic and requirements, create a detailed research plan.

Break down the research into specific, actionable tasks. Each task MUST use one of these available tools (no others exist):
- web_search: Search the web via DuckDuckGo and extract page content. Use for news, blogs, general info.
- academic_search: Search arXiv, Semantic Scholar, and Wikipedia. Use for scientific papers, encyclopedic context.
- summarizer: Synthesize and summarize gathered content. Use as a final task after collecting data.

Return your response as a JSON object with this structure:
{
    "research_strategy": "brief description of the overall approach",
    "key_questions": ["list of key questions to answer"],
    "tasks": [
        {
            "name": "task name",
            "description": "detailed description",
            "tool": "tool_name",
            "parameters": {"param1": "value1"},
            "priority": 1-10,
            "dependencies": ["task_id1", "task_id2"]
        }
    ],
    "expected_outcomes": ["list of expected outcomes"],
    "success_criteria": ["how to measure success"]
}

Topic: {topic}
Requirements: {requirements}

Be specific and actionable. Focus on finding authoritative sources and diverse perspectives."""

    async def create_research_plan(self, topic: str, requirements: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create a comprehensive research plan"""
        try:
            logger.info(f"Creating research plan for topic: {topic}")
            
            # Prepare requirements string
            req_str = json.dumps(requirements) if requirements else "None specified"
            
            # Generate plan using LLM
            plan_response = await llm_service.generate(
                prompt=self.planning_prompt.format(topic=topic, requirements=req_str),
                system_prompt="You are an expert research planner. Create detailed, actionable research plans.",
                temperature=0.3  # Lower temperature for more consistent planning
            )
            
            # Parse the response
            try:
                plan_data = json.loads(plan_response)
            except json.JSONDecodeError:
                # If JSON parsing fails, create a fallback plan
                logger.warning("LLM response was not valid JSON, creating fallback plan")
                plan_data = self._create_fallback_plan(topic, requirements)
            
            # Convert to structured tasks and assign IDs
            structured_plan = await self._structure_plan(plan_data, topic)
            
            logger.info(f"Created plan with {len(structured_plan['tasks'])} tasks")
            return structured_plan
            
        except Exception as e:
            logger.error(f"Error creating research plan: {e}")
            # Return fallback plan
            return self._create_fallback_plan(topic, requirements)
    
    async def _structure_plan(self, plan_data: Dict[str, Any], topic: str) -> Dict[str, Any]:
        """Structure the plan data and assign task IDs"""
        try:
            tasks = []
            task_id_map = {}
            
            for i, task_info in enumerate(plan_data.get("tasks", [])):
                task_id = f"task_{uuid.uuid4().hex[:8]}"
                task_id_map[i] = task_id
                
                task = ResearchTask(
                    id=task_id,
                    name=task_info.get("name", f"Task {i+1}"),
                    description=task_info.get("description", ""),
                    tool=task_info.get("tool", "web_search"),
                    parameters=task_info.get("parameters", {"query": topic}),
                    priority=task_info.get("priority", 5),
                    dependencies=task_info.get("dependencies", []),
                    estimated_time=task_info.get("estimated_time", 5)
                )
                tasks.append(task)
            
            return {
                "research_id": f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "topic": topic,
                "research_strategy": plan_data.get("research_strategy", "Comprehensive web-based research"),
                "key_questions": plan_data.get("key_questions", [topic]),
                "tasks": [asdict(task) for task in tasks],
                "expected_outcomes": plan_data.get("expected_outcomes", ["Comprehensive research report"]),
                "success_criteria": plan_data.get("success_criteria", ["Authoritative sources found", "Key questions answered"]),
                "created_at": datetime.now().isoformat(),
                "estimated_total_time": sum(task.estimated_time for task in tasks)
            }
            
        except Exception as e:
            logger.error(f"Error structuring plan: {e}")
            return self._create_fallback_plan(topic, {})
    
    def _create_fallback_plan(self, topic: str, requirements: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create a basic fallback research plan"""
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        
        return {
            "research_id": f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "topic": topic,
            "research_strategy": "Basic web search and analysis",
            "key_questions": [f"What is {topic}?", f"Current trends in {topic}", f"Key sources about {topic}"],
            "tasks": [
                {
                    "id": task_id,
                    "name": "Web Search",
                    "description": f"Search for comprehensive information about {topic}",
                    "tool": "web_search",
                    "parameters": {"query": topic, "max_results": 10},
                    "priority": 5,
                    "dependencies": [],
                    "estimated_time": 5,
                    "status": "pending"
                }
            ],
            "expected_outcomes": [f"Overview of {topic}", "Key sources and references"],
            "success_criteria": ["At least 5 relevant sources found", "Basic understanding established"],
            "created_at": datetime.now().isoformat(),
            "estimated_total_time": 5
        }
    
    async def update_task_status(self, research_id: str, task_id: str, status: str, result: Dict[str, Any] = None):
        """Update the status of a specific task"""
        try:
            # This would update the task in the stored plan
            # For now, we'll log the update
            logger.info(f"Task {task_id} status updated to {status} for research {research_id}")
            
            if result:
                await self.store_task_result(research_id, task_id, result)
                
        except Exception as e:
            logger.error(f"Error updating task status: {e}")

task_planner = TaskPlanner()