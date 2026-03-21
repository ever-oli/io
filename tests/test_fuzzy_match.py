from io_ai.fuzzy_match import fuzzy_filter, fuzzy_match


def test_fuzzy_match_subsequence() -> None:
    m = fuzzy_match("cld", "claude-sonnet")
    assert m.matches


def test_fuzzy_filter_tokens() -> None:
    items = ["anthropic/claude-opus", "openai/gpt-5", "anthropic/claude-haiku"]
    out = fuzzy_filter(items, "anth claude", lambda x: x)
    assert out and out[0].startswith("anthropic")


def test_fuzzy_filter_empty_query_returns_all() -> None:
    items = ["a", "b"]
    assert fuzzy_filter(items, "", lambda x: x) == items
