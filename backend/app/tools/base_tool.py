from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolResult:
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    sources: List[Dict[str, Any]] = field(default_factory=list)
    summaries: List[str] = field(default_factory=list)


class BaseTool(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        pass

    @abstractmethod
    def _get_parameters_schema(self) -> Dict[str, Any]:
        pass

    async def close(self):
        pass

    def get_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self._get_parameters_schema(),
        }