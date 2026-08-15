"""What SHAPE a Tamil word may have - the orthotactics, as facts about letters.

Tamil constrains where each ezhuthu may stand in a word, and three rules cover
it. Each is a fact about the script rather than a preference any Game holds:

- **which ezhuthu may BEGIN a word** - any of the twelve uyir, and ten of the
  eighteen consonants. A word never opens on a bare mei, on the aytham, or on
  one of the other eight consonants (``d``, ``N``, ``r``, ``l``, ``zh``, ``L``,
  ``tr``, ``n``);
- **which ezhuthu may END a word** - a vowel-bearing ezhuthu, or one of eight
  mei (``FINAL_MEI``, Tolkappiyam's word-final set);
- **which mei may be followed by which consonant** - the cluster table, stated
  over the three consonant classes the way Tamil grammar states it, rather than
  pair by pair.

A token failing one of them is not a Tamil word, and a scraped corpus is full of
the two things that fail them: SANDHI artifacts, where the euphonic doubling
belonging to the NEXT word was tokenized onto this one (``atharku-k kodu``
scraped as ``atharkuk``), and transliterated loanwords keeping a shape Tamil
does not build (``David``, ``ticket``, ``state``).

Grantha is the deliberate exception. Its five consonants were added to write
Sanskrit and foreign sounds and are not among the 247 ezhuthu, so carrying one
is not a defect - it is positive evidence that a surface is a LOANWORD.
``analyse`` therefore RECORDS grantha rather than penalising it, and a grantha
cluster is not judged against a table describing native letters.

This module holds no thresholds and no weights. It answers what Tamil allows;
what an allowance is WORTH belongs to the word-hood signal
(``docs/architecture/lexicon/word-hood.md``) and its knobs are config, never a
Python literal (Holy Law #6). It lives in the ezhuthu package because it is a
fact about Tamil letters, and it has no TypeScript twin on purpose: word
selection happens at build time, and the browser only ever plays the words that
already passed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from yen_tamizh_backend.ezhuthu.classify import classify
from yen_tamizh_backend.ezhuthu.segment import segment

PULLI: Final = "\u0bcd"
AYTHAM: Final = "\u0b83"

# The twelve uyir, listed rather than ranged: U+0B85..U+0B94 holds four
# unassigned code points, and a range would put them in the inventory.
UYIR: Final[tuple[str, ...]] = (
    "\u0b85",  # a
    "\u0b86",  # aa
    "\u0b87",  # i
    "\u0b88",  # ii
    "\u0b89",  # u
    "\u0b8a",  # uu
    "\u0b8e",  # e
    "\u0b8f",  # ee
    "\u0b90",  # ai
    "\u0b92",  # o
    "\u0b93",  # oo
    "\u0b94",  # au
)

# The eleven vowel signs. With the bare consonant, which carries the inherent
# /a/, these give each consonant its twelve uyirmei forms.
MATRA: Final[tuple[str, ...]] = (
    "\u0bbe",  # aa
    "\u0bbf",  # i
    "\u0bc0",  # ii
    "\u0bc1",  # u
    "\u0bc2",  # uu
    "\u0bc6",  # e
    "\u0bc7",  # ee
    "\u0bc8",  # ai
    "\u0bca",  # o
    "\u0bcb",  # oo
    "\u0bcc",  # au
)

# The three consonant classes. Every cluster rule below is stated over these,
# because that is how the grammar states them - a pair-by-pair table would be
# the same facts with 324 more places to be wrong.
VALLINAM: Final[tuple[str, ...]] = (
    "\u0b95",  # k
    "\u0b9a",  # ch
    "\u0b9f",  # d
    "\u0ba4",  # th
    "\u0baa",  # p
    "\u0bb1",  # tr
)
MELLINAM: Final[tuple[str, ...]] = (
    "\u0b99",  # ng
    "\u0b9e",  # nj
    "\u0ba3",  # N
    "\u0ba8",  # nh
    "\u0bae",  # m
    "\u0ba9",  # n
)
IDAIYINAM: Final[tuple[str, ...]] = (
    "\u0baf",  # y
    "\u0bb0",  # r
    "\u0bb2",  # l
    "\u0bb5",  # v
    "\u0bb4",  # zh
    "\u0bb3",  # L
)

# The eighteen native consonants, in the traditional order.
CONSONANTS: Final[tuple[str, ...]] = tuple(
    "\u0b95\u0b99\u0b9a\u0b9e\u0b9f\u0ba3\u0ba4\u0ba8\u0baa\u0bae"
    "\u0baf\u0bb0\u0bb2\u0bb5\u0bb4\u0bb3\u0bb1\u0ba9"
)

# Grantha - NOT among the 247. Borrowed to write Sanskrit and foreign sounds,
# so a surface carrying one is a loanword rather than a defect. The two borrowed
# COMPOUNDS need no entry of their own: ksha is k + ssa and shri is sa or sha
# plus rii, so whichever spelling a source used, one of these bases is in it.
GRANTHA: Final[frozenset[str]] = frozenset(
    {
        "\u0b9c",  # ja
        "\u0bb6",  # sha
        "\u0bb7",  # ssa
        "\u0bb8",  # sa
        "\u0bb9",  # ha
    }
)

# The 247: twelve uyir, eighteen mei, eighteen by twelve uyirmei, the aytham.
EZHUTHU_INVENTORY: Final[tuple[str, ...]] = (
    *UYIR,
    *(f"{base}{PULLI}" for base in CONSONANTS),
    *(f"{base}{matra}" for base in CONSONANTS for matra in ("", *MATRA)),
    AYTHAM,
)

# The ten consonants a Tamil word may open on. The other eight never begin a
# native word; a surface opening on one is a loanword or a fragment, which is
# exactly what the signal exists to notice.
INITIAL_CONSONANTS: Final[frozenset[str]] = frozenset(
    {
        "\u0b95",  # k
        "\u0b9a",  # ch
        "\u0b99",  # ng
        "\u0b9e",  # nj
        "\u0ba4",  # th
        "\u0ba8",  # nh
        "\u0baa",  # p
        "\u0bae",  # m
        "\u0baf",  # y
        "\u0bb5",  # v
    }
)

# ra and zha are the two consonants that do not double.
_NO_GEMINATE: Final[frozenset[str]] = frozenset({"\u0bb0", "\u0bb4"})

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


def _cluster_followers() -> Mapping[str, frozenset[str]]:
    """Which consonant may follow each mei, derived from the three classes.

    - a VALLINAM mei is followed by a vallinam: its own letter doubled, or
      another hard consonant (``kth``, ``dch``, ``trk``, ``trp``);
    - a MELLINAM mei is followed by any vallinam - its own homorganic stop
      first, but ``nk``, ``Np`` and ``nch`` are ordinary Tamil too - by its own
      letter doubled, and by ``m``, ``y``, ``v``;
    - an IDAIYINAM mei is the permissive class and takes any consonant.

    ``ra`` and ``zha`` are removed from their own entry because they are the two
    consonants that do not double. Every one of the eighteen mei gets an entry,
    so the table is exhaustive by construction rather than by anyone remembering
    to extend it.
    """
    vallinam = frozenset(VALLINAM)
    mellinam = frozenset(MELLINAM)
    idaiyinam = frozenset(IDAIYINAM)
    soft = frozenset({"\u0bae", "\u0baf", "\u0bb5"})  # m, y, v
    followers: dict[str, frozenset[str]] = {}
    for base in CONSONANTS:
        if base in vallinam:
            allowed = vallinam
        elif base in mellinam:
            allowed = vallinam | soft | {base}
        else:
            allowed = vallinam | mellinam | idaiyinam
        if base in _NO_GEMINATE:
            allowed = allowed - {base}
        followers[f"{base}{PULLI}"] = allowed
    return followers


CLUSTER_FOLLOWERS: Final[Mapping[str, frozenset[str]]] = _cluster_followers()


@dataclass(frozen=True, slots=True)
class WordShape:
    """What Tamil's own rules say about one surface, as separated facts.

    Separated rather than summed, because the classifier reads them for
    different verdicts: an illegal opening says loanword or fragment, an illegal
    ending says sandhi artifact, and grantha says loanword outright. What each
    fact is WORTH is config, never this dataclass.
    """

    ezhuthu: tuple[str, ...]
    initialLegal: bool
    finalLegal: bool
    clustersLegal: bool
    hasGrantha: bool
    hasNonTamil: bool


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


def begins_like_a_word(ezhuthu: Sequence[str]) -> bool:
    """Whether a segmented token opens the way a real Tamil word opens."""
    if not ezhuthu:
        return False
    first = ezhuthu[0]
    kind = classify(first)
    if kind == "uyir":
        return True
    if kind != "uyirmei":
        # A bare mei and the aytham both fail - neither can carry a word's first
        # sound - and a non-Tamil unit is not a Tamil opening at all.
        return False
    return first[0] in INITIAL_CONSONANTS


def cluster_is_legal(mei: str, following: str) -> bool:
    """Whether ``mei`` may be followed by the ezhuthu ``following``.

    A pair with grantha on either side answers True: grantha is not among the
    247, so a table describing how native letters meet has nothing to say about
    it, and its loanword evidence is carried by ``WordShape.hasGrantha``.
    """
    followers = CLUSTER_FOLLOWERS.get(mei)
    if followers is None:
        return True
    if not following or following[0] in GRANTHA:
        return True
    if classify(following) not in ("mei", "uyirmei"):
        # A mei cannot be followed by an independent vowel or by the aytham:
        # Tamil writes a vowel after a consonant as a matra ON that consonant,
        # so this shape is a join that was never made.
        return False
    return following[0] in followers


def analyse(word: str) -> WordShape:
    """Segment ``word`` and answer every orthotactic question about it once.

    One segmentation pass for all five facts, because this runs over every
    staged surface and segmenting four more times would be four times the cost
    for the same answer.
    """
    units = tuple(segment(word))
    if not units:
        return WordShape((), False, False, False, False, True)
    kinds = [classify(unit) for unit in units]
    return WordShape(
        ezhuthu=units,
        initialLegal=begins_like_a_word(units),
        finalLegal=ends_like_a_word(units),
        clustersLegal=all(
            cluster_is_legal(left, right)
            for left, right, kind in zip(units, units[1:], kinds)
            if kind == "mei"
        ),
        hasGrantha=any(unit[0] in GRANTHA for unit in units),
        hasNonTamil=any(kind == "other" for kind in kinds),
    )
