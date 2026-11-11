import pytest

from router import classify


@pytest.mark.parametrize("question, expected", [
    ("How many customers are in the database?", "haiku"),
    ("How many suppliers are there?", "haiku"),
    ("How many orders have status F?", "haiku"),
    ("How many orders were placed in 1994?", "haiku"),
    ("How many distinct regions are there?", "haiku"),
    ("What are the top 3 nations by number of customers?", "sonnet"),
    ("Which segment has the highest total order value?", "sonnet"),
    ("What percentage of customers have never placed an order?", "sonnet"),
    ("What is the total revenue lost due to discounts in 1995?", "sonnet"),
    ("What ship mode has the highest average discount?", "sonnet"),
    ("Revenue per year", "sonnet"),
])
def test_classify(question, expected):
    assert classify(question) == expected


@pytest.mark.parametrize("question", [
    "How many operations are logged?",     # 'per' inside a word
    "How many separate suppliers exist?",  # 'rate' inside a word
])
def test_signals_match_whole_words_only(question):
    # None of these contain a complex signal as a whole word.
    assert classify(question) == "haiku"


def test_case_insensitive():
    assert classify("TOP 5 CUSTOMERS") == "sonnet"
