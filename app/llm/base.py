"""LLMProvider interface — every provider implementation must satisfy this."""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def ask(self, prompt: str) -> str:
        """Send prompt to the model, return its text response."""
        ...
