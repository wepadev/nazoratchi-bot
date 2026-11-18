import pytest

from bot.answers import AnswerError, grade, mistakes, parse_answers


@pytest.mark.parametrize("text", ["abcd", "A B C D", "a,b,c,d", "1a 2b 3c 4d", "4d 3c 2b 1a",
                                  "1-a, 2-b, 3) c, 4.d", "абсд", "1а 2б 3с 4д"])
def test_formats(text):
    assert parse_answers(text, 4) == "ABCD"


def test_blanks():
    assert parse_answers("1a 3c", 4) == "A-C-"
    assert parse_answers("axcx", 4) == "A-C-"


@pytest.mark.parametrize("text,n", [("abce", 4), ("abc", 4), ("1a 2b 5c", 4), ("1a 1b", 4), ("", 4), ("1a x", 4)])
def test_errors(text, n):
    with pytest.raises(AnswerError):
        parse_answers(text, n)


def test_key_without_blanks():
    assert parse_answers("1a 2b 3c") == "ABC"
    with pytest.raises(AnswerError):
        parse_answers("1a 3c", allow_blank=False)


def test_grade():
    assert grade("AB-D", "ABCC") == 2
    assert mistakes("AB-D", "ABCC") == [(3, "-", "C"), (4, "D", "C")]
