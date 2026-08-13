"""Whether a token ENDS the way a real Tamil word ends.

Tamil orthography constrains the last unit of a word: it is a vowel-bearing
ezhuthu (uyir or uyirmei), or one of eight mei consonants - ``m``, ``n``,
``N``, ``l``, ``L``, ``r``, ``zh``, ``y`` (Tolkappiyam's word-final set). A
token ending in any OTHER pure mei - ``k``, ``ch``, ``t``, ``th``, ``p``,
``tr``, or a grantha letter - is not a standalone word in running text. It is
one of two things:

- a SANDHI artifact, where the euphonic doubling that belongs to the NEXT word
  was tokenized onto this one (``atharku-k kodu`` scraped as ``atharkuk``);
- an English loanword transliterated with its final stop kept (``David``,
  ``ticket``, ``edit``, ``state``).

Neither is a word a Tamil speaker would recognise as a puzzle ANSWER, and a
scraped corpus is full of both. This is the cheapest honest test that separates
them from real words, and it costs no dictionary.

It lives in the ezhuthu package because it is a fact about Tamil letters, not
about any one Game's selection - the derived layer turns it ON with a config
knob (``requireValidWordFinal``), and later generators reuse the same rule. It
has no TypeScript twin on purpose: word selection happens at build time, and the
browser only ever plays the words that already passed.
"""

from __future__ import annotations

from collections.abc import Sequence

from yen_tamizh_backend.ezhuthu.classify import classify

# The eight mei a Tamil word may end in.
FINAL_MEI: frozenset[str] = frozenset(
    {
        "\u0bae\u0bcd",  # m
        "\u0ba9\u0bcd",  # n (final)
        "\u0ba3\u0bcd",  # N (retroflex)
        "\u0bb2\u0bcd",  # l
        "\u0bb3\u0bcd",  # L (retroflex)
        "\u0bb0\u0bcd",  # r
        "\u0bb4\u0bcd",  # zh
        "\u0baf\u0bcd",  # y
    }
)


def is_word_final(ezhuthu: str) -> bool:
    """Whether one ezhuthu may legally end a Tamil word."""
    # Anything carrying a vowel (uyir, uyirmei) ends a word freely; only a bare
    # mei is restricted. Aytham and non-Tamil units are left to the caller's
    # other filters rather than being judged here.
    if classify(ezhuthu) != "mei":
        return True
    return ezhuthu in FINAL_MEI


def ends_like_a_word(ezhuthu: Sequence[str]) -> bool:
    """Whether a segmented token ends the way a real Tamil word ends."""
    if not ezhuthu:
        return False
    return is_word_final(ezhuthu[-1])
