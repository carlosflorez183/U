# Agent instructions

This repository now includes a starter agent package under the `agent/` directory.

## Purpose

The agent provides a small, task-oriented workflow for planning and validating work before finishing.

## How to run

```bash
python -m agent "Build a dashboard"
```

## Core behavior

- Accept a user goal and turn it into a plan.
- Keep the workflow explicit and verifiable.
- Return a structured result with agent name, goal, plan, and status.
