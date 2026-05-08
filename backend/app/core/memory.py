# backend/app/core/memory.py
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
import asyncio
from loguru import logger

@dataclass
class MemoryItem:
    id: str
    type: str  # "context", "plan", "task_result", "insight"
    content: Dict[str, Any]
    research_id: str
    timestamp: datetime
    metadata: Dict[str, Any] = None

class MemoryManager:
    def __init__(self, data_dir: str = "./app/data"):
        self.data_dir = Path(data_dir)
        self.memory_dir = self.data_dir / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache for active research sessions
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.memory_items: Dict[str, MemoryItem] = {}
    
    async def store_context(self, research_id: str, context: Dict[str, Any]):
        """Store research context"""
        memory_item = MemoryItem(
            id=f"{research_id}_context",
            type="context",
            content=context,
            research_id=research_id,
            timestamp=datetime.now(),
            metadata={"session_start": True}
        )
        
        await self._save_memory_item(memory_item)
        self.active_sessions[research_id] = context
        logger.info(f"Stored context for research session: {research_id}")
    
    async def store_plan(self, research_id: str, plan: Dict[str, Any]):
        """Store research plan"""
        memory_item = MemoryItem(
            id=f"{research_id}_plan",
            type="plan",
            content=plan,
            research_id=research_id,
            timestamp=datetime.now(),
            metadata={"total_tasks": len(plan.get("tasks", []))}
        )
        
        await self._save_memory_item(memory_item)
        logger.info(f"Stored research plan for: {research_id}")
    
    async def store_task_result(self, research_id: str, task_id: str, result: Dict[str, Any]):
        """Store individual task results"""
        memory_item = MemoryItem(
            id=f"{research_id}_{task_id}_result",
            type="task_result",
            content=result,
            research_id=research_id,
            timestamp=datetime.now(),
            metadata={"task_id": task_id}
        )
        
        await self._save_memory_item(memory_item)
        logger.info(f"Stored task result: {task_id} for research: {research_id}")
    
    async def store_insight(self, research_id: str, insight: Dict[str, Any]):
        """Store research insights and findings"""
        insight_id = f"{research_id}_insight_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        memory_item = MemoryItem(
            id=insight_id,
            type="insight",
            content=insight,
            research_id=research_id,
            timestamp=datetime.now(),
            metadata={"insight_type": insight.get("type", "general")}
        )
        
        await self._save_memory_item(memory_item)
        logger.info(f"Stored insight for research: {research_id}")
    
    async def get_research_context(self, research_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve research context"""
        if research_id in self.active_sessions:
            return self.active_sessions[research_id]
        
        # Load from disk if not in memory
        context_item = await self._load_memory_item(f"{research_id}_context")
        if context_item:
            self.active_sessions[research_id] = context_item.content
            return context_item.content
        return None
    
    async def get_research_plan(self, research_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve research plan"""
        plan_item = await self._load_memory_item(f"{research_id}_plan")
        return plan_item.content if plan_item else None
    
    async def get_task_results(self, research_id: str) -> List[Dict[str, Any]]:
        """Get all task results for a research session."""
        results = []
        cached_ids = set()
        for item_id, item in self.memory_items.items():
            if item.research_id == research_id and item.type == "task_result":
                results.append(item.content)
                cached_ids.add(item_id)

        # Also load any results that landed on disk but are not yet in cache.
        memory_files = await asyncio.to_thread(
            lambda: list(self.memory_dir.glob(f"{research_id}_*_result.json"))
        )
        for file_path in memory_files:
            if file_path.stem not in cached_ids:
                item = await self._load_memory_item(file_path.stem)
                if item:
                    results.append(item.content)

        return results
    
    async def get_research_summary(self, research_id: str) -> Dict[str, Any]:
        """Get comprehensive summary of research session"""
        context = await self.get_research_context(research_id)
        plan = await self.get_research_plan(research_id)
        task_results = await self.get_task_results(research_id)
        
        return {
            "research_id": research_id,
            "context": context,
            "plan": plan,
            "task_results": task_results,
            "total_tasks": len(task_results),
            "status": context.get("status", "unknown") if context else "unknown"
        }
    
    async def _save_memory_item(self, item: MemoryItem):
        """Persist a memory item to the in-memory cache and disk (non-blocking)."""
        try:
            self.memory_items[item.id] = item

            file_path = self.memory_dir / f"{item.id}.json"
            item_dict = asdict(item)
            item_dict["timestamp"] = item.timestamp.isoformat()

            def _write():
                with open(file_path, "w") as f:
                    json.dump(item_dict, f, indent=2)

            await asyncio.to_thread(_write)
        except Exception as e:
            logger.error(f"Error saving memory item {item.id}: {e}")
            raise

    async def _load_memory_item(self, item_id: str) -> Optional[MemoryItem]:
        """Load a memory item from disk (non-blocking)."""
        try:
            file_path = self.memory_dir / f"{item_id}.json"
            if not file_path.exists():
                return None

            def _read():
                with open(file_path, "r") as f:
                    return json.load(f)

            item_dict = await asyncio.to_thread(_read)
            item_dict["timestamp"] = datetime.fromisoformat(item_dict["timestamp"])
            memory_item = MemoryItem(**item_dict)
            self.memory_items[item_id] = memory_item
            return memory_item
        except Exception as e:
            logger.error(f"Error loading memory item {item_id}: {e}")
            return None
    
    async def clear_research_session(self, research_id: str):
        """Delete all in-memory and on-disk data for a research session."""
        self.active_sessions.pop(research_id, None)

        to_remove = [
            item_id
            for item_id, item in self.memory_items.items()
            if item.research_id == research_id
        ]
        for item_id in to_remove:
            del self.memory_items[item_id]

        def _delete_files():
            for file_path in self.memory_dir.glob(f"{research_id}_*.json"):
                file_path.unlink(missing_ok=True)

        await asyncio.to_thread(_delete_files)
        logger.info(f"Cleared memory for research session: {research_id}")

# Global memory manager instance
memory_manager = MemoryManager()