"""Module registration registry."""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ModuleInfo:
    name: str
    version: str
    dependencies: List[str] = field(default_factory=list)


class ModuleRegistry:
    """Stores module metadata without loading business logic."""

    def __init__(self) -> None:
        self._modules: Dict[str, ModuleInfo] = {}

    def register(self, module_info: ModuleInfo) -> None:
        self._modules[module_info.name] = module_info

    def list_modules(self) -> List[ModuleInfo]:
        return list(self._modules.values())
