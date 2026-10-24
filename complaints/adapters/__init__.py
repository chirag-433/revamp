"""Local source adapters for demo and future approved integrations."""

from .mock_sources import MockPGRCAdapter, MockRBAdapter

ADAPTERS = {"rb": MockRBAdapter, "pgrc": MockPGRCAdapter}
