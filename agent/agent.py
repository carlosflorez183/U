from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanStep:
    description: str
    status: str = "pending"


@dataclass
class Agent:
    """A small task-oriented agent template for this workspace."""

    name: str = "StarterAgent"
    instructions: list[str] = field(
        default_factory=lambda: [
            "Break the request into clear, testable steps.",
            "Act conservatively and verify the outcome before finishing.",
        ]
    )

    def plan(self, goal: str) -> list[PlanStep]:
        if not goal or not goal.strip():
            raise ValueError("goal cannot be empty")

        cleaned_goal = goal.strip()
        return [
            PlanStep(f"Clarify the objective: {cleaned_goal}"),
            PlanStep(f"Define the minimal execution plan for: {cleaned_goal}"),
            PlanStep(f"Validate the result against: {cleaned_goal}"),
        ]

    def run(self, goal: str) -> dict[str, Any]:
        steps = self.plan(goal)
        return {
            "agent": self.name,
            "goal": goal,
            "plan": [step.description for step in steps],
            "status": "ready",
        }
