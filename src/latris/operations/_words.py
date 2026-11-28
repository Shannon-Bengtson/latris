"""Small wording helpers for generated messages."""

from __future__ import annotations

# Vowel letters sounded as a consonant ("a uniform", "a one-off") and silent h's ("an hour").
_A_DESPITE_VOWEL = ("uni", "use", "usu", "uti", "eu", "one", "once")
_AN_DESPITE_CONSONANT = ("hour", "honest", "honour", "honor", "heir")
# Initialisms said letter by letter that start with a vowel sound ("an SD model", "an MCDA").
_AN_LETTERS = "AEFHILMNORSX"


def a_or_an(phrase: str) -> str:
    """``phrase`` with its indefinite article: "an end state", "a uniform range", "an 'edge' ID"."""
    word = phrase.lstrip("'\"`(“‘").split(" ", 1)[0]
    if not word:
        return f"a {phrase}"
    if len(word) > 1 and word.isupper():
        return f"{'an' if word[0] in _AN_LETTERS else 'a'} {phrase}"
    low = word.lower()
    if low.startswith(_AN_DESPITE_CONSONANT):
        return f"an {phrase}"
    if low[0] in "aeiou" and not low.startswith(_A_DESPITE_VOWEL):
        return f"an {phrase}"
    return f"a {phrase}"
