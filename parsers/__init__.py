"""Parsers package for different test report frameworks."""

from .base_parser import BaseParser, TestResult, TestSuite, TestReport
from .mochawesome import MochawesomeParser
from .playwright import PlaywrightParser
from .pytest_parser import PytestParser

__all__ = [
    "BaseParser",
    "TestResult",
    "TestSuite",
    "TestReport",
    "MochawesomeParser",
    "PlaywrightParser",
    "PytestParser",
]
