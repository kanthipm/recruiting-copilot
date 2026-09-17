"""Collector registry. To add a source type: write a Collector subclass and register it here."""
from .ashby import AshbyCollector
from .base import Collector, Job
from .greenhouse import GreenhouseCollector
from .lever import LeverCollector

COLLECTORS: dict[str, type[Collector]] = {
    GreenhouseCollector.name: GreenhouseCollector,
    LeverCollector.name: LeverCollector,
    AshbyCollector.name: AshbyCollector,
}


def get_collector(name: str) -> Collector:
    try:
        return COLLECTORS[name]()
    except KeyError:
        raise ValueError(f"Unknown collector '{name}'. Known: {sorted(COLLECTORS)}")


__all__ = ["COLLECTORS", "Collector", "Job", "get_collector"]
