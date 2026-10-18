from __future__ import annotations

import argparse
import json

from agent import Agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the starter agent.")
    parser.add_argument("goal", nargs="?", default="Build a useful feature", help="Goal for the agent to plan.")
    parser.add_argument("--name", default="StarterAgent", help="Name assigned to the agent.")
    args = parser.parse_args()

    agent = Agent(name=args.name)
    result = agent.run(args.goal)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
