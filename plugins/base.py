# src/plugins/base.py

from dataclasses import dataclass, field
from typing import List, Dict, Any, Iterator

@dataclass
class Entry:
    """
    Represents a single piece of data processed by the pipeline.
    This is the common data structure passed between plugins.
    """
    id: str
    source: str
    content: str
    vector: List[float] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: int = 0


class BasePlugin:
    """Base class for all plugins."""
    name = "BasePlugin"
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def execute(self, *args, **kwargs):
        raise NotImplementedError(
            f"Plugin {self.name} must implement the 'execute' method."
        )


class SubscriptionPlugin(BasePlugin):
    """Base class for plugins that subscribe to data sources."""
    def execute(self) -> Iterator[Entry]:
        """Subscribes to a data source and yields Entry objects."""
        raise NotImplementedError(
            f"SubscriptionPlugin {self.name} must implement 'execute' to yield Entries."
        )
        yield


class FilterPlugin(BasePlugin):
    """Base class for plugins that filter or transform entries."""
    def execute(self, entries: Iterator[Entry]) -> Iterator[Entry]:
        """Receives, processes, and yields Entry objects."""
        raise NotImplementedError(
            f"FilterPlugin {self.name} must implement 'execute' to process and yield Entries."
        )
        yield


class PublishPlugin(BasePlugin):
    """Base class for plugins that publish entries to a destination."""
    def execute(self, entries: Iterator[Entry]):
        """Receives Entry objects and publishes them."""
        raise NotImplementedError(
            f"PublishPlugin {self.name} must implement 'execute' to publish Entries."
        )
