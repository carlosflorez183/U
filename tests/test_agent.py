from agent import Agent


def test_agent_has_default_name_and_plan():
    agent = Agent()
    assert agent.name == "StarterAgent"
    plan = agent.plan("Build a dashboard")
    assert len(plan) >= 2
    assert plan[0].description


def test_agent_run_returns_goal_and_status():
    agent = Agent(name="DemoAgent")
    result = agent.run("Ship a release")
    assert result["agent"] == "DemoAgent"
    assert result["goal"] == "Ship a release"
    assert result["status"] == "ready"
