"""Maidie 生产 Brain 管线的公共入口。

本包把意图识别、结构化规划、受控执行和结果合成分成独立阶段；上层
``PetController``/Session 只依赖这里导出的稳定组件，而不直接耦合各实现文件。
"""

from core.brain.executor import BrainExecutor
from core.brain.intent_classifier import IntentClassifier
from core.brain.llm_router import LLMIntentRouter
from core.brain.planner import BrainPlanner
from core.brain.problem_analyzer import ProblemAnalyzer, ProblemContext
from core.brain.router import BrainRouter
from core.brain.synthesizer import Synthesizer

__all__ = ["BrainExecutor", "BrainPlanner", "BrainRouter", "IntentClassifier", "LLMIntentRouter",
           "ProblemAnalyzer", "ProblemContext", "Synthesizer"]
