from types import SimpleNamespace

import pytest

import agent
import config


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool(name, **inp):
    return SimpleNamespace(type="tool_use", id=f"id_{name}_{len(inp)}", name=name, input=inp)


def reply(*blocks, stop="tool_use", tokens=(100, 10)):
    usage = SimpleNamespace(input_tokens=tokens[0], output_tokens=tokens[1],
                            cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(content=list(blocks), stop_reason=stop, usage=usage)


class FakeClient:
    """Scripted replacement for anthropic.Anthropic(); records every request."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        # snapshot: the agent mutates the same list between calls
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.replies.pop(0)


@pytest.fixture
def fake(db, monkeypatch):
    def install(*replies):
        client = FakeClient(replies)
        monkeypatch.setattr(agent, "get_client", lambda: client)
        return client
    return install


COUNT = "SELECT COUNT(*) AS n FROM customer"


def test_simple_question_uses_haiku(fake):
    client = fake(
        reply(tool("run_sql", query=COUNT)),
        reply(text("There are 4 customers."), stop="end_turn"),
    )
    result = agent.run_agent("How many customers are there?")
    assert result["answer"] == "There are 4 customers."
    assert result["error"] is None
    assert result["routed_to"] == "haiku" and result["model"] == config.MODEL_PRIMARY
    assert result["model_label"] == "Haiku 4.5"
    assert result["sql"] == COUNT and result["iterations"] == 2
    assert [s["tool"] for s in result["steps"]] == ["run_sql"]
    assert client.calls[0]["model"] == config.MODEL_PRIMARY


def test_system_prompt_embeds_schema_and_is_cached(fake):
    client = fake(reply(text("ok"), stop="end_turn"))
    agent.run_agent("How many customers are there?")
    block = client.calls[0]["system"][0]
    assert "customer(c_custkey BIGINT" in block["text"]
    assert block["cache_control"] == {"type": "ephemeral"}


def test_complex_question_goes_straight_to_sonnet(fake):
    client = fake(reply(text("Brazil."), stop="end_turn"))
    result = agent.run_agent("Which nation has the highest balance?")
    assert result["routed_to"] == "sonnet" and result["model"] == config.MODEL_FALLBACK
    assert client.calls[0]["model"] == config.MODEL_FALLBACK


def test_usage_and_cost_are_tracked(fake):
    fake(reply(text("ok"), stop="end_turn", tokens=(1_000_000, 100_000)))
    result = agent.run_agent("How many customers are there?")
    assert result["usage"]["input_tokens"] == 1_000_000 and result["usage"]["output_tokens"] == 100_000
    price_in, price_out = config.MODEL_PRICING[config.MODEL_PRIMARY]
    assert result["cost_usd"] == pytest.approx(price_in + 0.1 * price_out)


def test_haiku_escalates_to_sonnet_in_same_conversation(fake, monkeypatch):
    monkeypatch.setattr(config, "HAIKU_MAX_ITERS", 2)
    client = fake(
        reply(tool("sample_table", table_name="customer")),
        reply(tool("sample_table", table_name="nation")),      # Haiku budget exhausted here
        reply(text("Done by Sonnet."), stop="end_turn"),
    )
    result = agent.run_agent("How many customers are there?")
    assert result["answer"] == "Done by Sonnet." and result["model"] == config.MODEL_FALLBACK
    assert result["routed_to"] == "haiku"
    assert [c["model"] for c in client.calls] == [config.MODEL_PRIMARY, config.MODEL_PRIMARY, config.MODEL_FALLBACK]
    assert result["iterations"] == 3
    assert len(client.calls[2]["messages"]) == 5  # question + 2 x (assistant, tool results)
    assert client.calls[2]["messages"][-1]["role"] == "user"


def test_sql_errors_are_marked_and_retried(fake):
    client = fake(
        reply(tool("run_sql", query="SELECT nope FROM customer")),
        reply(tool("run_sql", query=COUNT)),
        reply(text("4."), stop="end_turn"),
    )
    result = agent.run_agent("How many customers are there?")
    assert result["answer"] == "4."
    first_results = client.calls[1]["messages"][-1]["content"]
    assert first_results[0]["is_error"] is True
    assert "is_error" not in client.calls[2]["messages"][-1]["content"][0]


def test_gives_up_after_max_sql_errors(fake, monkeypatch):
    monkeypatch.setattr(config, "MAX_SQL_ERRORS", 3)
    fake(*[reply(tool("run_sql", query=f"SELECT bad{i} FROM customer")) for i in range(10)])
    result = agent.run_agent("Which nation has the highest balance?")
    assert "failed SQL attempts" in result["error"]
    assert result["answer"] == "" and result["iterations"] == 3


def test_max_iterations(fake):
    fake(*[reply(tool("sample_table", table_name="customer", limit=i + 1)) for i in range(10)])
    result = agent.run_agent("Which nation has the highest balance?", max_iterations=3)
    assert result["error"] == "Max iterations reached without a final answer."
    assert result["iterations"] == 3


def test_truncated_answer_is_an_error_not_a_result(fake):
    fake(reply(text("The answer is cut o"), stop="max_tokens"))
    result = agent.run_agent("Which nation has the highest balance?")
    assert "cut off" in result["error"] and result["answer"] == ""


def test_history_is_sent_as_prior_turns(fake):
    client = fake(reply(text("ok"), stop="end_turn"))
    history = [{"question": "How many customers?", "answer": "Four."}, {"question": "", "answer": "dropped"}]
    agent.run_agent("And nations?", history=history)
    assert client.calls[0]["messages"] == [
        {"role": "user", "content": "How many customers?"},
        {"role": "assistant", "content": "Four."},
        {"role": "user", "content": "And nations?"},
    ]


def test_history_is_trimmed(fake):
    client = fake(reply(text("ok"), stop="end_turn"))
    history = [{"question": f"q{i}", "answer": f"a{i}"} for i in range(20)]
    agent.run_agent("next?", history=history)
    assert len(client.calls[0]["messages"]) == config.MAX_HISTORY_TURNS * 2 + 1
    assert client.calls[0]["messages"][0]["content"] == f"q{20 - config.MAX_HISTORY_TURNS}"


def test_temperature_only_sent_when_set(fake):
    client = fake(reply(text("ok"), stop="end_turn"), reply(text("ok"), stop="end_turn"))
    agent.run_agent("How many customers are there?")
    agent.run_agent("How many customers are there?", temperature=0)
    assert "temperature" not in client.calls[0] and client.calls[1]["temperature"] == 0


def test_on_step_callback_and_answer_check(fake):
    seen = []
    fake(
        reply(tool("run_sql", query="SELECT 15000 AS n")),
        reply(text("There are 15,000 customers."), stop="end_turn"),
    )
    result = agent.run_agent("How many customers are there?", on_step=seen.append)
    assert [s["tool"] for s in seen] == ["run_sql"]
    assert result["answer_check"] == {"verified": True, "unmatched": []}
