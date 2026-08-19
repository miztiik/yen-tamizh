"""Tests for the derived layer after the row 12 cutover: lexicon -> served wordlists.

Real files and real fixtures throughout, no mocks (Holy Law #7). Tamil is written
with ``\\uXXXX`` escapes so this source stays ASCII (CLAUDE.md section 5) and so
the composed form of every test word is unambiguous. The synthetic lexicons the
unit tests read are written by the REAL publisher's own address and render
functions, so a test lexicon is addressed exactly the way the committed one is.

Six things are proven:

1. **The four serving gates** - class, attestation with its tier-1 leg,
   frequency and meaning each reject for their own reason, and the counters
   reconcile against the lexicon's published row count with no silent drops -
   **the two selection dimensions**, ``categories`` and ``pos``, which keep
   the rows their own set-valued column intersects, are charged before the
   gates, and never apply to a set that did not ask for them - **the two
   derivable exclusions** of defect 2, the participial suffix and the source's
   own obscenity label, each with its own bucket and each asserted against the
   words it must NOT take - and **the curated deny-list**, which runs last,
   matches a WHOLE word and never a prefix, and carries its own ledger bucket.
2. **Resolution by the meta document** - the derived layer opens the files the
   partition table names and NOTHING else, so a stray file in the published
   directory cannot reach a player and a class the lexicon does not publish is a
   loud error rather than an empty set.
3. **Determinism** - ``rebuild`` writes byte-identical output from identical
   input, and the COMMITTED ``anagram.json`` and ``themed-nature.json`` are
   exactly what a fresh rebuild from the committed lexicon produces. That second
   assertion is the hand-edit gate: a derived set is a build artifact, so any
   hand edit fails here.
4. **The Oracles over the REAL committed artifacts** - every row satisfies all
   four gates; the three words this cutover exists to remove are absent, as are
   the four participial adjectives and the one labelled obscenity of defect 2;
   no denied word survives in either set while every word deliberately KEPT is
   still served; every ``anagramFanOut`` equals the number of served rows
   sharing its ezhuthu multiset; every ``frequencyStratum`` is the quartile of
   THIS set; and the themed set is EXACTLY the rows the theme covers that the
   gates keep, no more and no fewer, computed independently of the code that cut
   it.
5. **Coverage + schema** - the committed set is non-empty at every target ezhuthu
   length, clears the served-set floor, and validates row by row.
6. **Rejection** - a malformed row, an incoherent selection, an unsorted
   dimension, a colliding registry, a registry naming no deny-list or no
   serving rules, an unsorted or blank obscenity marker, a suffix with a blank
   ezhuthu or no stem floor, an unsorted or duplicated or unexplained deny-list,
   and a class no Game may ever serve all fail validation rather than being
   silently accepted.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from yen_tamizh_backend.contracts import DerivedWordlists, GameWordlist
from yen_tamizh_backend.contracts.common import QUARTILES
from yen_tamizh_backend.contracts.derived_wordlists import (
    DerivedSelection,
    DerivedSet,
    ParticipialSuffix,
    ServableWordClass,
    ServingRules,
)
from yen_tamizh_backend.contracts.game_wordlist import (
    DerivedCounters,
    GameWord,
    GameWordHints,
)
from yen_tamizh_backend.contracts.lexicon import (
    PARTITION_KEYS,
    Lexicon,
    LexiconEntry,
    PartOfSpeech,
    WordClass,
)
from yen_tamizh_backend.contracts.served_denylist import DeniedWord, ServedDenylist
from yen_tamizh_backend.ezhuthu import classify, ezhuthu_roman, segment
from yen_tamizh_backend.scripts.rebuild_wordlists import rebuild
from yen_tamizh_backend.wordsmith import derive
from yen_tamizh_backend.wordsmith.artifact import sha256_of
from yen_tamizh_backend.wordsmith.publish import (
    BY_CLASS,
    META_NAME,
    partition_hex,
    partition_path,
)
from yen_tamizh_backend.wordsmith.publish import render as render_row

_REPO_ROOT = Path(__file__).resolve().parents[2]
_META = _REPO_ROOT / "datasets" / "lexicon" / "lexicon.meta.json"
_REGISTRY = _REPO_ROOT / "config" / "derived-wordlists.json"
_DENYLIST = _REPO_ROOT / "config" / "served-denylist.json"
_ANAGRAM = _REPO_ROOT / "datasets" / "wordlists" / "derived" / "anagram.json"
_THEMED = _REPO_ROOT / "datasets" / "wordlists" / "derived" / "themed-nature.json"

# The theme's own registry id, and the share of the servable set a theme must
# exclude before it is worth naming (row 15 decision 11).
_THEMED_GAME_ID = "themed-nature"
_THEME_EXCLUSION_FLOOR = 0.90

# A real anagram pair: vaasal (doorway) and savaal (challenge) are the same three
# ezhuthu in a different order.
VAASAL = "\u0bb5\u0bbe\u0b9a\u0bb2\u0bcd"
SAVAAL = "\u0b9a\u0bb5\u0bbe\u0bb2\u0bcd"

# A real SOLITARY word: ithazh (petal) has no anagram, so it must be SERVED and
# must carry a fan-out of exactly 1.
ITHAZH = "\u0b87\u0ba4\u0bb4\u0bcd"

# A real 2-ezhuthu word (oru) - inside every other gate, outside the lengths.
ORU = "\u0b92\u0bb0\u0bc1"

# The three words this cutover exists to stop serving. asura is a bound stem the
# dictionary lists as an entry; the other two are a political party and a sitting
# politician, and the committed set served both.
ASURA = "\u0b85\u0b9a\u0bc1\u0bb0"
DMK = "\u0ba4\u0bbf\u0bae\u0bc1\u0b95"
STALIN = "\u0bb8\u0bcd\u0b9f\u0bbe\u0bb2\u0bbf\u0ba9\u0bcd"

# Defect 2's own four: participial adjectives the board dealt as answers.
# mozhiyaana (linguistic), migudhiyaana (abundant), urundaiyaana (round) and
# thavaRillaadha (faultless) are peyareccham built on mozhi, migudhi, urundai
# and thavaRu - inflected forms, not headwords a dictionary lists.
MOZHIYAANA = "\u0bae\u0bca\u0bb4\u0bbf\u0baf\u0bbe\u0ba9"
MIGUDHIYAANA = "\u0bae\u0bbf\u0b95\u0bc1\u0ba4\u0bbf\u0baf\u0bbe\u0ba9"
URUNDAIYAANA = "\u0b89\u0bb0\u0bc1\u0ba3\u0bcd\u0b9f\u0bc8\u0baf\u0bbe\u0ba9"
THAVARILLAADHA = "\u0ba4\u0bb5\u0bb1\u0bbf\u0bb2\u0bcd\u0bb2\u0bbe\u0ba4"
PAYANULLA = "\u0baa\u0baf\u0ba9\u0bc1\u0bb3\u0bcd\u0bb3"  # payanulla - useful

# Real vocabulary that ENDS the same way and must survive the suffix rule.
# vaan (sky) and aakiya are inside the -aana / -iya shapes; kolla, mella, kulla
# and kalla are the words a bare -lla match would have taken; indhiya, pudhiya,
# periya, siRiya, ariya, iniya and dhesiya are why the -iya ending was measured
# and rejected outright.
VAAN = "\u0bb5\u0bbe\u0ba9"
KOLLA = "\u0b95\u0bca\u0bb3\u0bcd\u0bb3"
MELLA = "\u0bae\u0bc6\u0bb3\u0bcd\u0bb3"
KULLA = "\u0b95\u0bc1\u0bb3\u0bcd\u0bb3"
KALLA = "\u0b95\u0bb3\u0bcd\u0bb3"
_ENDS_THE_SAME_WAY = (
    KOLLA,
    MELLA,
    KULLA,
    KALLA,
    "\u0b87\u0ba8\u0bcd\u0ba4\u0bbf\u0baf",  # indhiya
    "\u0baa\u0bc1\u0ba4\u0bbf\u0baf",  # pudhiya
    "\u0baa\u0bc6\u0bb0\u0bbf\u0baf",  # periya
    "\u0b9a\u0bbf\u0bb1\u0bbf\u0baf",  # siRiya
    "\u0b85\u0bb0\u0bbf\u0baf",  # ariya
    "\u0b87\u0ba9\u0bbf\u0baf",  # iniya
    "\u0ba4\u0bc7\u0b9a\u0bbf\u0baf",  # dhesiya
)

# The obscenity the source labels, and the four surfaces a looser marker takes
# with it: aruvaruppu (disgust) and pachchai (green) whose glosses MENTION
# obscenity, vanmai (harshness) whose later sense discusses coarse speech, and
# paasisam (fascism) whose gloss says the word became a term of abuse.
PUNDAI = "\u0baa\u0bc1\u0ba3\u0bcd\u0b9f\u0bc8"
_NOT_OBSCENE = (
    "\u0b85\u0bb0\u0bc1\u0bb5\u0bb0\u0bc1\u0baa\u0bcd\u0baa\u0bc1",  # aruvaruppu
    "\u0baa\u0b9a\u0bcd\u0b9a\u0bc8",  # pachchai
    "\u0bb5\u0ba9\u0bcd\u0bae\u0bc8",  # vanmai
    "\u0baa\u0bbe\u0b9a\u0bbf\u0b9a\u0bae\u0bcd",  # paasisam
)

# The 27 words reviewed alongside the row 16 deny-list and deliberately KEPT -
# appa, amma, arasu, pakkam, maathiri, konjam, niraiya, the numerals one to five
# and thousand, inru, piragu, adutthu, arugil, ethiraaga, kaaranamaaga,
# udanadiyaaga, ippadi, eppadi, and the given names selvan, aadhavan, nambi,
# agil and indhu. Every one of them is real vocabulary a cruder rule - a
# part-of-speech filter, or a "looks grammatical" sweep - would have taken.
_KEPT = (
    "\u0b85\u0baa\u0bcd\u0baa\u0bbe",
    "\u0b85\u0bae\u0bcd\u0bae\u0bbe",
    "\u0b85\u0bb0\u0b9a\u0bc1",
    "\u0baa\u0b95\u0bcd\u0b95\u0bae\u0bcd",
    "\u0bae\u0bbe\u0ba4\u0bbf\u0bb0\u0bbf",
    "\u0b95\u0bca\u0b9e\u0bcd\u0b9a\u0bae\u0bcd",
    "\u0ba8\u0bbf\u0bb1\u0bc8\u0baf",
    "\u0b92\u0ba9\u0bcd\u0bb1\u0bc1",
    "\u0b87\u0bb0\u0ba3\u0bcd\u0b9f\u0bc1",
    "\u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1",
    "\u0ba8\u0bbe\u0ba9\u0bcd\u0b95\u0bc1",
    "\u0b90\u0ba8\u0bcd\u0ba4\u0bc1",
    "\u0b86\u0baf\u0bbf\u0bb0\u0bae\u0bcd",
    "\u0b87\u0ba9\u0bcd\u0bb1\u0bc1",
    "\u0baa\u0bbf\u0bb1\u0b95\u0bc1",
    "\u0b85\u0b9f\u0bc1\u0ba4\u0bcd\u0ba4\u0bc1",
    "\u0b85\u0bb0\u0bc1\u0b95\u0bbf\u0bb2\u0bcd",
    "\u0b8e\u0ba4\u0bbf\u0bb0\u0bbe\u0b95",
    "\u0b95\u0bbe\u0bb0\u0ba3\u0bae\u0bbe\u0b95",
    "\u0b89\u0b9f\u0ba9\u0b9f\u0bbf\u0baf\u0bbe\u0b95",
    "\u0b87\u0baa\u0bcd\u0baa\u0b9f\u0bbf",
    "\u0b8e\u0baa\u0bcd\u0baa\u0b9f\u0bbf",
    "\u0b9a\u0bc6\u0bb2\u0bcd\u0bb5\u0ba9\u0bcd",
    "\u0b86\u0ba4\u0bb5\u0ba9\u0bcd",
    "\u0ba8\u0bae\u0bcd\u0baa\u0bbf",
    "\u0b85\u0b95\u0bbf\u0bb2\u0bcd",
    "\u0b87\u0ba8\u0bcd\u0ba4\u0bc1",
)

# A Tamil meaning, so a row can satisfy requireMeaning without inventing English.
MEANING = "\u0b92\u0bb0\u0bc1 \u0baa\u0bca\u0bb0\u0bc1\u0bb3\u0bcd"
SENSES = [MEANING]

_SHA = "0" * 64

# Row 12 decision 15's floor, in the units it was stated in.
_SERVED_FLOOR = 6000


def _entry(
    word: str,
    *,
    wordClass: WordClass = "headword",
    frequency: int = 100,
    attestations: int = 3,
    tier1Attestations: int = 2,
    definitionTa: list[str] | None = SENSES,
    translationEn: str | None = None,
    synonymsTa: list[str] | None = None,
    categories: list[str] | None = None,
    pos: list[PartOfSpeech] | None = None,
) -> LexiconEntry:
    """One lexicon row, with every gate satisfied unless a test moves a knob."""
    return LexiconEntry(
        word=word,
        wordClass=wordClass,
        length=len(segment(word)),
        frequency=frequency,
        attestations=attestations,
        tier1Attestations=tier1Attestations,
        definitionTa=definitionTa,
        translationEn=translationEn,
        synonymsTa=synonymsTa,
        categories=categories,
        pos=pos,
    )


def _write_lexicon(repo_root: Path, rows: list[LexiconEntry]) -> Path:
    """Write a real published lexicon - partition files plus the meta document.

    Addressed through the publisher's own ``partition_hex`` / ``partition_path``,
    so a fixture lexicon is laid out exactly the way the committed one is and a
    change to the address breaks both together.
    """
    directory = repo_root / "datasets" / "lexicon"
    cells: dict[tuple[str, str], list[LexiconEntry]] = {}
    for row in rows:
        key = (row.wordClass, partition_hex(segment(row.word)[0][0]))
        cells.setdefault(key, []).append(row)

    partitions: list[dict[str, Any]] = []
    index: dict[str, dict[str, str]] = {}
    for (word_class, hex_key), cell_rows in sorted(cells.items()):
        path = partition_path(directory / BY_CLASS, word_class, hex_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(
            render_row(row) for row in sorted(cell_rows, key=lambda r: r.word)
        )
        path.write_text(body, encoding="utf-8", newline="\n")
        digest, size = sha256_of(path)
        partitions.append(
            {
                "path": path.relative_to(repo_root).as_posix(),
                "wordClass": word_class,
                "baseEzhuthu": hex_key,
                "rows": len(cell_rows),
                "bytes": size,
                "sha256": digest,
            }
        )
        letter = segment(cell_rows[0].word)[0][0]
        index[hex_key] = {
            "ezhuthu": letter,
            "roman": ezhuthu_roman(letter),
            "kind": classify(letter),
        }

    census = {
        "rows": len(rows),
        "byClass": {
            name: sum(1 for row in rows if row.wordClass == name)
            for name in get_args(WordClass)
        },
    }
    meta_path = directory / META_NAME
    meta_path.write_text(
        json.dumps(
            {
                "version": "2026-08-16T23:00",
                "changelog": [
                    {"version": "2026-08-16T23:00", "change": "test", "why": "test"}
                ],
                "partitionKeys": list(PARTITION_KEYS),
                "provenance": [
                    {
                        "id": "test-source",
                        "name": "test source",
                        "origin": "test",
                        "path": "datasets/lexicon/sources/test-source/source.txt",
                        "bytes": 1,
                        "sha256": _SHA,
                        "observations": len(rows),
                        "facts": len(rows),
                    }
                ],
                "counters": {"classified": census, "published": census},
                "partitions": partitions,
                "ezhuthuIndex": index,
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    return meta_path


def _sample_rows() -> list[LexiconEntry]:
    """A lexicon holding one anagram pair, one solitary word, one short word."""
    return [
        _entry(VAASAL, frequency=400),
        _entry(ITHAZH, frequency=300),
        _entry(ORU, frequency=200),
        _entry(SAVAAL, frequency=100),
    ]


def _selection(**overrides: Any) -> DerivedSelection:
    base: dict[str, Any] = {
        "wordClasses": ["headword"],
        "minLength": 3,
        "maxLength": 6,
        "minAttestations": 2,
        "minTier1Attestations": 1,
        "minFrequency": 1,
        "requireMeaning": True,
        "maxWords": None,
    }
    base.update(overrides)
    return DerivedSelection.model_validate(base)


def _spec(out: str, **overrides: Any) -> dict[str, Any]:
    return {
        "gameId": "anagram",
        "out": out,
        "selection": _selection(**overrides).model_dump(),
    }


# The REAL shipped serving rules, so a fixture cut is refused exactly what the
# committed set is refused - and so tuning the config moves the tests with it.
_RULES = derive.load_registry(_REGISTRY).servingRules


def _cut(
    repo_root: Path,
    rows: list[LexiconEntry],
    denied: frozenset[str] = frozenset(),
    rules: ServingRules = _RULES,
    **overrides: Any,
) -> GameWordlist:
    """Publish a fixture lexicon and cut one set out of it, end to end."""
    meta_path = _write_lexicon(repo_root, rows)
    meta = derive.load_meta(meta_path)
    spec = DerivedSet.model_validate(
        _spec("datasets/wordlists/derived/anagram.json", **overrides)
    )
    source = derive.describe_source(
        meta, meta_path, "datasets/lexicon/lexicon.meta.json"
    )
    streamed = derive.read_rows(meta, repo_root, spec.selection.wordClasses)
    return derive.derive(meta, streamed, source, spec, denied, rules)


@pytest.fixture(scope="module")
def committed_meta() -> Lexicon:
    """The REAL committed lexicon meta document, parsed once for every Oracle."""
    return derive.load_meta(_META)


@pytest.fixture(scope="module")
def committed_anagram() -> GameWordlist:
    """The REAL committed anagram set, validated against its contract."""
    return GameWordlist.model_validate_json(_ANAGRAM.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def committed_themed() -> GameWordlist:
    """The REAL committed themed set - the first set cut on a dimension."""
    return GameWordlist.model_validate_json(_THEMED.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 1. The four serving gates
# --------------------------------------------------------------------------


def test_multiset_key_is_order_free_over_ezhuthu() -> None:
    assert derive.multiset_key(segment(VAASAL)) == derive.multiset_key(segment(SAVAAL))
    assert derive.multiset_key(segment(VAASAL)) != derive.multiset_key(segment(ITHAZH))


def test_group_by_multiset_puts_anagrams_together() -> None:
    groups = derive.group_by_multiset([VAASAL, ITHAZH, SAVAAL])
    assert sorted(groups[derive.multiset_key(segment(VAASAL))]) == sorted(
        [VAASAL, SAVAAL]
    )
    assert groups[derive.multiset_key(segment(ITHAZH))] == [ITHAZH]


def test_the_class_gate_is_an_allow_list_and_counts_from_the_partition_table(
    tmp_path: Path,
) -> None:
    """A class the selection does not name is counted, never opened, never served."""
    rows = [
        _entry(VAASAL),
        _entry(DMK, wordClass="properNoun"),
        _entry(STALIN, wordClass="properNoun"),
    ]
    wordlist = _cut(tmp_path, rows)

    assert [row.word for row in wordlist.words] == [VAASAL]
    assert wordlist.counters.outsideClass == 2
    assert wordlist.counters.lexiconRows == 3


def test_each_gate_rejects_for_its_own_reason(tmp_path: Path) -> None:
    rows = [
        _entry(VAASAL),
        _entry(ORU),  # 2 ezhuthu - outside the length band
        _entry(ITHAZH, attestations=1, tier1Attestations=1),  # too thin
        _entry(SAVAAL, frequency=0),  # never occurs
        _entry(ASURA, definitionTa=None),  # nobody can say what it means
        _entry(DMK, wordClass="properNoun"),
    ]
    wordlist = _cut(tmp_path, rows)
    counters = wordlist.counters

    assert [row.word for row in wordlist.words] == [VAASAL]
    assert counters.outsideLength == 1
    assert counters.outsideClass == 1
    assert counters.belowAttestations == 1
    assert counters.belowFrequency == 1
    assert counters.withoutMeaning == 1
    assert counters.rowsKept == 1
    assert counters.lexiconRows == 6


def test_two_bare_attestations_without_a_dictionary_are_not_enough(
    tmp_path: Path,
) -> None:
    """The composition rule: a spellchecker agreeing with a wordlist says nothing."""
    rows = [
        _entry(VAASAL, attestations=2, tier1Attestations=1),
        _entry(ITHAZH, attestations=5, tier1Attestations=0),
    ]
    wordlist = _cut(tmp_path, rows)

    assert [row.word for row in wordlist.words] == [VAASAL]
    assert wordlist.counters.belowAttestations == 1


def test_a_participial_adjective_is_demoted_and_a_lookalike_is_not(
    tmp_path: Path,
) -> None:
    """Defect 2's own four, beside the words that merely END the same way.

    Both halves matter. A rule that keeps mozhiyaana off the board and takes
    vaan (sky) or kolla with it has traded one defect for a worse one, so the
    lookalikes are asserted as loudly as the participles.
    """
    participles = [
        MOZHIYAANA,
        MIGUDHIYAANA,
        URUNDAIYAANA,
        THAVARILLAADHA,
        PAYANULLA,
    ]
    lookalikes = [VAAN, KOLLA, MELLA, KULLA, KALLA]
    wordlist = _cut(
        tmp_path,
        [_entry(word) for word in (*participles, *lookalikes)],
        minLength=2,
    )

    assert {row.word for row in wordlist.words} == set(lookalikes)
    assert wordlist.counters.participial == len(participles)


def test_an_obscenity_the_source_labels_is_never_served(tmp_path: Path) -> None:
    """The refusal reads the SOURCE's own usage label, not a curated rude-word list.

    Two near misses are asserted with it, because both were measured as real
    false positives of the looser markers that were rejected: a gloss that
    MENTIONS obscenity is not an obscenity, and a label on a later sense marks a
    marginal reading rather than the word.
    """
    labelled = f"{MEANING} (\u0b86\u0baa\u0bbe\u0b9a\u0b9a\u0bcd\u0b9a\u0bca\u0bb2\u0bcd)"
    discusses = f"\u0b86\u0baa\u0bbe\u0b9a\u0bae\u0bcd {MEANING}"
    wordlist = _cut(
        tmp_path,
        [
            _entry(PUNDAI, definitionTa=[labelled]),
            _entry(VAASAL, definitionTa=[discusses]),
            _entry(ITHAZH, definitionTa=[MEANING, labelled]),
        ],
    )

    assert {row.word for row in wordlist.words} == {VAASAL, ITHAZH}
    assert wordlist.counters.obscene == 1


def test_rows_come_out_most_frequent_first(tmp_path: Path) -> None:
    wordlist = _cut(tmp_path, _sample_rows())
    frequencies = [row.frequency for row in wordlist.words]
    assert frequencies == sorted(frequencies, reverse=True)
    assert [row.word for row in wordlist.words] == [VAASAL, ITHAZH, SAVAAL]


def test_the_cap_trims_the_rarest_and_reports_what_it_cut(tmp_path: Path) -> None:
    wordlist = _cut(tmp_path, _sample_rows(), maxWords=2)

    assert [row.word for row in wordlist.words] == [VAASAL, ITHAZH]
    assert wordlist.counters.capped == 1
    assert wordlist.counters.rowsKept == 2


def test_the_cap_is_applied_before_the_signals_are_counted(tmp_path: Path) -> None:
    """Fan-out and strata count SERVED rows, and a capped row is not served."""
    wordlist = _cut(tmp_path, [_entry(VAASAL), _entry(SAVAAL, frequency=50)], maxWords=1)

    assert [(row.word, row.anagramFanOut) for row in wordlist.words] == [(VAASAL, 1)]


def test_a_solitary_word_is_served_with_a_fan_out_of_one(tmp_path: Path) -> None:
    """The number the Oracle names: a word counts ITSELF, so 1 means unique."""
    wordlist = _cut(tmp_path, [_entry(ITHAZH), _entry(VAASAL)])

    assert {row.word: row.anagramFanOut for row in wordlist.words} == {
        ITHAZH: 1,
        VAASAL: 1,
    }


def test_fan_out_counts_the_served_rows_that_share_a_multiset(tmp_path: Path) -> None:
    wordlist = _cut(tmp_path, _sample_rows())

    assert {row.word: row.anagramFanOut for row in wordlist.words} == {
        VAASAL: 2,
        ITHAZH: 1,
        SAVAAL: 2,
    }


def test_fan_out_ignores_rows_a_gate_dropped(tmp_path: Path) -> None:
    """A partner nobody is served cannot be the answer a Game offers back."""
    rows = [_entry(VAASAL), _entry(ITHAZH), _entry(SAVAAL, frequency=0)]
    wordlist = _cut(tmp_path, rows)

    assert {row.word: row.anagramFanOut for row in wordlist.words} == {
        VAASAL: 1,
        ITHAZH: 1,
    }


def test_strata_are_the_quartiles_of_the_served_set(tmp_path: Path) -> None:
    """Four served rows, one per quarter - and the quarters are of THIS set."""
    wordlist = _cut(
        tmp_path,
        [
            _entry(VAASAL, frequency=400),
            _entry(ITHAZH, frequency=300),
            _entry(SAVAAL, frequency=200),
            _entry(ASURA, frequency=100),
        ],
    )

    assert [(row.word, row.frequencyStratum) for row in wordlist.words] == [
        (VAASAL, 1),
        (ITHAZH, 2),
        (SAVAAL, 3),
        (ASURA, 4),
    ]


# --------------------------------------------------------------------------
# 1a. The two selection dimensions (row 15)
# --------------------------------------------------------------------------


def test_the_categories_dimension_keeps_the_rows_that_intersect_it(
    tmp_path: Path,
) -> None:
    """A dimension is an INTERSECTION: one shared tag is enough to be in the theme."""
    rows = [
        _entry(VAASAL, categories=["birds"]),
        _entry(ITHAZH, categories=["animals", "nature"]),
        _entry(SAVAAL, categories=["tools"]),
        _entry(ASURA),
    ]
    wordlist = _cut(tmp_path, rows, categories=["birds", "nature"])

    assert sorted(row.word for row in wordlist.words) == sorted([VAASAL, ITHAZH])
    assert wordlist.counters.outsideCategories == 2
    assert wordlist.counters.outsidePos == 0


def test_a_row_the_lexicon_never_tagged_can_never_join_a_theme(
    tmp_path: Path,
) -> None:
    """Fewer than 3,000 published rows carry a category - the rest are not the theme."""
    wordlist = _cut(tmp_path, [_entry(VAASAL)], categories=["nature"])

    assert wordlist.words == []
    assert wordlist.counters.outsideCategories == 1


def test_the_pos_dimension_is_the_same_intersection_over_a_different_column(
    tmp_path: Path,
) -> None:
    rows = [
        _entry(VAASAL, pos=["noun", "verb"]),
        _entry(ITHAZH, pos=["noun"]),
        _entry(SAVAAL),
    ]
    wordlist = _cut(tmp_path, rows, pos=["verb"])

    assert [row.word for row in wordlist.words] == [VAASAL]
    assert wordlist.counters.outsidePos == 2
    assert wordlist.counters.outsideCategories == 0


def test_a_set_naming_no_dimension_charges_nothing_to_either_bucket(
    tmp_path: Path,
) -> None:
    """Neither dimension may ever gate an ordinary set - absent means not applied."""
    wordlist = _cut(tmp_path, _sample_rows())

    assert wordlist.selection.categories is None
    assert wordlist.selection.pos is None
    assert wordlist.counters.outsideCategories == 0
    assert wordlist.counters.outsidePos == 0
    assert wordlist.counters.rowsKept == 3


def test_a_dimension_is_charged_before_the_gates_that_would_also_stop_a_row(
    tmp_path: Path,
) -> None:
    """A row off the theme is off the theme, whatever else is also wrong with it."""
    rows = [
        _entry(VAASAL, categories=["nature"]),
        _entry(ORU, frequency=0),  # too short, never occurs, AND off the theme
    ]
    wordlist = _cut(tmp_path, rows, categories=["nature"])

    assert wordlist.counters.outsideCategories == 1
    assert wordlist.counters.outsideLength == 0
    assert wordlist.counters.belowFrequency == 0


def test_both_dimensions_narrow_together(tmp_path: Path) -> None:
    rows = [
        _entry(VAASAL, categories=["birds"], pos=["noun"]),
        _entry(ITHAZH, categories=["birds"], pos=["verb"]),
        _entry(SAVAAL, categories=["tools"], pos=["noun"]),
    ]
    wordlist = _cut(tmp_path, rows, categories=["birds"], pos=["noun"])

    assert [row.word for row in wordlist.words] == [VAASAL]
    assert wordlist.counters.outsideCategories == 1
    assert wordlist.counters.outsidePos == 1


# --------------------------------------------------------------------------
# 1b. The curated deny-list (row 16)
# --------------------------------------------------------------------------


def test_a_denied_word_is_not_served_and_is_charged_to_its_own_bucket(
    tmp_path: Path,
) -> None:
    """Every gate passes and the word still does not reach the board."""
    rows = [_entry(VAASAL), _entry(ITHAZH), _entry(SAVAAL)]
    wordlist = _cut(tmp_path, rows, denied=frozenset({SAVAAL}))

    assert sorted(row.word for row in wordlist.words) == sorted([VAASAL, ITHAZH])
    assert wordlist.counters.denylisted == 1
    assert wordlist.counters.rowsKept == 2


def test_the_deny_list_matches_a_WHOLE_word_and_never_a_prefix(
    tmp_path: Path,
) -> None:
    """VAASAL denied must not take VAASALIL with it - Tamil agglutinates."""
    inflected = VAASAL + "\u0bbf\u0bb2\u0bcd"
    wordlist = _cut(
        tmp_path, [_entry(VAASAL), _entry(inflected)], denied=frozenset({VAASAL})
    )

    assert [row.word for row in wordlist.words] == [inflected]
    assert wordlist.counters.denylisted == 1


def test_the_deny_list_is_charged_after_every_automatic_gate(tmp_path: Path) -> None:
    """Its number is what the LIST alone removed, not what a gate would have."""
    rows = [
        _entry(VAASAL),
        _entry(ORU),  # denied AND 2 ezhuthu, so the length gate stopped it first
        _entry(SAVAAL, frequency=0),  # denied AND never occurs
    ]
    wordlist = _cut(tmp_path, rows, denied=frozenset({ORU, SAVAAL}))

    assert [row.word for row in wordlist.words] == [VAASAL]
    assert wordlist.counters.denylisted == 0
    assert wordlist.counters.outsideLength == 1
    assert wordlist.counters.belowFrequency == 1


def test_a_denied_word_is_not_counted_by_the_signals_of_the_rows_that_remain(
    tmp_path: Path,
) -> None:
    """A word nobody is served cannot be the answer a Game offers back."""
    wordlist = _cut(
        tmp_path, [_entry(VAASAL), _entry(SAVAAL)], denied=frozenset({SAVAAL})
    )

    assert [(row.word, row.anagramFanOut) for row in wordlist.words] == [(VAASAL, 1)]


def test_rebuild_reads_the_deny_list_the_registry_names(tmp_path: Path) -> None:
    """The path is config, so a run cannot serve a denied word by forgetting it."""
    registry = _tmp_repo(
        tmp_path,
        [_spec("datasets/wordlists/derived/anagram.json")],
        denied=[VAASAL],
    )
    _, wordlist = rebuild(registry, tmp_path)[0]

    assert VAASAL not in {row.word for row in wordlist.words}
    assert wordlist.counters.denylisted == 1


# --------------------------------------------------------------------------
# 2. Resolution by the meta document, never by globbing
# --------------------------------------------------------------------------


def test_a_stray_file_the_meta_document_does_not_declare_is_never_read(
    tmp_path: Path,
) -> None:
    """The anti-glob Oracle: a file nothing vouches for cannot reach a player."""
    meta_path = _write_lexicon(tmp_path, [_entry(VAASAL)])
    stray = tmp_path / "datasets" / "lexicon" / BY_CLASS / "headword"
    (stray / "ffff.ndjson").write_text(
        render_row(_entry(STALIN)), encoding="utf-8", newline="\n"
    )

    meta = derive.load_meta(meta_path)
    served = [row.word for row in derive.read_rows(meta, tmp_path, ["headword"])]

    assert served == [VAASAL]


def test_a_class_the_lexicon_does_not_publish_is_a_loud_error(tmp_path: Path) -> None:
    """A selection that silently serves nothing looks identical to one that works."""
    meta_path = _write_lexicon(tmp_path, [_entry(VAASAL)])
    meta = derive.load_meta(meta_path)

    with pytest.raises(derive.DeriveError, match="colloquial"):
        list(derive.read_rows(meta, tmp_path, ["headword", "colloquial"]))


def test_rows_arrive_in_partition_table_order(tmp_path: Path) -> None:
    meta_path = _write_lexicon(tmp_path, _sample_rows())
    meta = derive.load_meta(meta_path)

    served = [row.word for row in derive.read_rows(meta, tmp_path, ["headword"])]

    assert served == [row.word for row in sorted(_sample_rows(), key=_address)]


def _address(row: LexiconEntry) -> tuple[str, str, str]:
    return (
        row.wordClass,
        partition_hex(segment(row.word)[0][0]),
        row.word,
    )


# --------------------------------------------------------------------------
# 3. Determinism
# --------------------------------------------------------------------------


def _tmp_repo(
    tmp_path: Path, sets: list[dict[str, Any]], denied: list[str] | None = None
) -> Path:
    """A miniature repo root: a real published lexicon, registry and deny-list."""
    _write_lexicon(tmp_path, _sample_rows())
    denylist = tmp_path / "config" / "served-denylist.json"
    denylist.parent.mkdir(parents=True)
    # A deny-list may not be empty, so a fixture that denies nothing still names
    # a word - one no test lexicon publishes.
    denylist.write_text(
        json.dumps(
            {
                "version": "2026-08-17",
                "changelog": [
                    {"version": "2026-08-17", "change": "test", "why": "test"}
                ],
                "note": "test deny-list",
                "functionWords": [
                    {"word": word, "reason": "test"}
                    for word in sorted(denied or [DMK])
                ],
                "properNouns": [{"word": STALIN, "reason": "test"}],
            }
        ),
        encoding="utf-8",
    )
    registry = tmp_path / "config" / "derived-wordlists.json"
    registry.write_text(
        json.dumps(
            {
                "version": "2026-08-16T23:30",
                "changelog": [
                    {
                        "version": "2026-08-16T23:30",
                        "change": "test registry",
                        "why": "test",
                    }
                ],
                "lexiconPath": "datasets/lexicon/lexicon.meta.json",
                "denylistPath": "config/served-denylist.json",
                "servingRules": _RULES.model_dump(),
                "sets": sets,
            }
        ),
        encoding="utf-8",
    )
    return registry


def test_rebuild_writes_every_registered_set(tmp_path: Path) -> None:
    registry = _tmp_repo(
        tmp_path,
        [
            _spec("datasets/wordlists/derived/anagram.json"),
            {
                **_spec("datasets/wordlists/derived/other.json", maxLength=5),
                "gameId": "wordle",
            },
        ],
    )
    written = rebuild(registry, tmp_path)

    assert [path.name for path, _ in written] == ["anagram.json", "other.json"]
    assert all(path.exists() for path, _ in written)
    assert [wordlist.gameId for _, wordlist in written] == ["anagram", "wordle"]


def test_rebuild_is_byte_identical_across_runs(tmp_path: Path) -> None:
    registry = _tmp_repo(tmp_path, [_spec("datasets/wordlists/derived/anagram.json")])
    out = rebuild(registry, tmp_path)[0][0]
    first = out.read_bytes()
    rebuild(registry, tmp_path)
    assert out.read_bytes() == first


def test_artifacts_carry_no_wall_clock(committed_anagram: GameWordlist) -> None:
    """A timestamp would make two runs over one lexicon differ - that is the point."""
    raw = json.loads(_ANAGRAM.read_text(encoding="utf-8"))
    assert "generatedAt" not in raw
    assert "generatedAt" not in raw["source"]


def test_committed_anagram_set_is_exactly_what_a_rebuild_produces(
    committed_meta: Lexicon,
) -> None:
    """The hand-edit gate: a derived set is a build artifact, never edited."""
    registry = derive.load_registry(_REGISTRY)
    spec = next(entry for entry in registry.sets if entry.gameId == "anagram")
    source = derive.describe_source(committed_meta, _META, registry.lexiconPath)
    rows = derive.read_rows(committed_meta, _REPO_ROOT, spec.selection.wordClasses)
    denied = derive.load_denylist(_REPO_ROOT / registry.denylistPath).words()

    rebuilt = derive.render(
        derive.derive(committed_meta, rows, source, spec, denied, registry.servingRules)
    )

    assert rebuilt == _ANAGRAM.read_text(encoding="utf-8")


def test_committed_set_pins_the_lexicon_it_was_cut_from(
    committed_anagram: GameWordlist, committed_meta: Lexicon
) -> None:
    digest, _ = sha256_of(_META)
    assert committed_anagram.source.sha256 == digest
    assert committed_anagram.source.metaPath == "datasets/lexicon/lexicon.meta.json"
    assert committed_anagram.source.version == committed_meta.version
    assert committed_anagram.source.rows == committed_meta.counters.published.rows


def test_committed_themed_set_is_exactly_what_a_rebuild_produces(
    committed_meta: Lexicon,
) -> None:
    """The hand-edit gate for the themed set: a theme is derived, never curated."""
    registry = derive.load_registry(_REGISTRY)
    spec = next(entry for entry in registry.sets if entry.gameId == _THEMED_GAME_ID)
    source = derive.describe_source(committed_meta, _META, registry.lexiconPath)
    rows = derive.read_rows(committed_meta, _REPO_ROOT, spec.selection.wordClasses)
    denied = derive.load_denylist(_REPO_ROOT / registry.denylistPath).words()

    rebuilt = derive.render(
        derive.derive(committed_meta, rows, source, spec, denied, registry.servingRules)
    )

    assert rebuilt == _THEMED.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 4. The Oracles over the real committed artifact
# --------------------------------------------------------------------------


def test_the_themed_set_is_exactly_the_rows_the_theme_covers_and_the_gates_keep(
    committed_meta: Lexicon, committed_themed: GameWordlist
) -> None:
    """THE row 15 Oracle, computed independently of select(): no more, no fewer.

    The expectation is built by walking the published lexicon and applying the
    theme and the gates by hand, so it agrees with the committed file only if
    the derived layer really did what the registry says.
    """
    selection = committed_themed.selection
    assert selection.categories is not None
    wanted = set(selection.categories)
    denied = derive.load_denylist(_DENYLIST).words()
    rules = derive.load_registry(_REGISTRY).servingRules
    expected = {
        row.word
        for row in derive.read_rows(committed_meta, _REPO_ROOT, selection.wordClasses)
        if wanted & set(row.categories or ())
        and selection.minLength <= row.length <= selection.maxLength
        and row.attestations >= selection.minAttestations
        and row.tier1Attestations >= selection.minTier1Attestations
        and row.frequency >= selection.minFrequency
        and row.definitionTa is not None
        and not derive.is_marked_obscene(row.definitionTa, rules.obscenityMarkers)
        and not derive.ends_in_participial_suffix(
            segment(row.word), rules.participialSuffixes
        )
        and row.word not in denied
    }

    assert {row.word for row in committed_themed.words} == expected
    assert committed_themed.counters.rowsKept == len(expected)


def test_the_theme_excludes_almost_all_of_the_servable_set(
    committed_anagram: GameWordlist, committed_themed: GameWordlist
) -> None:
    """Row 15 decision 11: a theme nobody could guess against is not a theme.

    A tag that excludes nothing - "nouns" - narrows nothing for a player told
    what the round is about, so knowing it would be worth no score at all.
    """
    excluded = 1 - len(committed_themed.words) / len(committed_anagram.words)
    assert excluded >= _THEME_EXCLUSION_FLOOR, f"excludes only {excluded:.4f}"


def test_every_themed_row_is_also_served_by_the_ordinary_set(
    committed_anagram: GameWordlist, committed_themed: GameWordlist
) -> None:
    """A themed day may never serve a word an ordinary day could not.

    The theme narrows the ordinary selection; it does not relax it. If a themed
    set ever carried a word the ordinary gates reject, a themed day would be the
    back door around the gates.
    """
    ordinary = {row.word for row in committed_anagram.words}
    off_gate = [row.word for row in committed_themed.words if row.word not in ordinary]
    assert off_gate == []


def test_the_themed_set_clears_the_weekly_growth_target(
    committed_themed: GameWordlist,
) -> None:
    """Row 15 decision 12: one themed Daily a week for a year is 52 x 3 rows."""
    assert len(committed_themed.words) >= 52 * 3


def test_the_themed_set_covers_every_difficulty_the_day_deals(
    committed_themed: GameWordlist,
) -> None:
    """A theme that cannot fill a band is a theme that never runs (decision 5)."""
    lengths = {len(row.ezhuthu) for row in committed_themed.words}
    assert {3, 4, 5, 6} <= lengths
    assert {row.frequencyStratum for row in committed_themed.words} == {1, 2, 3, 4}


def test_no_committed_row_fails_any_of_the_four_gates(
    committed_anagram: GameWordlist,
) -> None:
    selection = committed_anagram.selection
    allowed = set(selection.wordClasses)
    assert allowed == {"headword"}
    words = {row.word for row in committed_anagram.words}

    published = {
        row.word: row
        for row in derive.read_rows(
            derive.load_meta(_META), _REPO_ROOT, selection.wordClasses
        )
        if row.word in words
    }
    assert len(published) == len(words), "a served word is not a published headword"
    for row in published.values():
        assert selection.minLength <= row.length <= selection.maxLength
        assert row.attestations >= selection.minAttestations
        assert row.tier1Attestations >= selection.minTier1Attestations
        assert row.frequency >= selection.minFrequency
        assert row.definitionTa is not None


def test_the_three_words_this_cutover_removes_are_absent(
    committed_anagram: GameWordlist,
) -> None:
    """A bound stem, a political party, and a sitting politician. Named, not sampled."""
    served = {row.word for row in committed_anagram.words}
    for word in (ASURA, DMK, STALIN):
        assert word not in served, f"{word} is still served"


def test_the_four_participial_adjectives_the_board_dealt_are_absent(
    committed_anagram: GameWordlist,
) -> None:
    """Defect 2, named rather than sampled - baked days served all four."""
    served = {row.word for row in committed_anagram.words}
    for word in (MOZHIYAANA, MIGUDHIYAANA, URUNDAIYAANA, THAVARILLAADHA):
        assert word not in served, f"{word} is still served"


def test_no_committed_row_ends_in_a_participial_suffix(
    committed_anagram: GameWordlist, committed_themed: GameWordlist
) -> None:
    """THE defect-2 Oracle for the suffix rule, over both committed sets."""
    rules = derive.load_registry(_REGISTRY).servingRules
    for wordlist in (committed_anagram, committed_themed):
        left = [
            row.word
            for row in wordlist.words
            if derive.ends_in_participial_suffix(row.ezhuthu, rules.participialSuffixes)
        ]
        assert left == [], f"{wordlist.gameId} still serves {left[:10]}"


def test_a_word_that_merely_ends_the_same_way_is_still_served(
    committed_anagram: GameWordlist,
) -> None:
    """What the rule must NOT have cost: real vocabulary sharing the ending.

    kolla, mella, kulla and kalla are why -ulla carries a linking vowel and a
    stem floor; indhiya, pudhiya, periya, siRiya, ariya, iniya and dhesiya are
    why the -iya ending was measured at 202 served rows and rejected outright.
    """
    served = {row.word for row in committed_anagram.words}
    missing = [word for word in _ENDS_THE_SAME_WAY if word not in served]
    assert missing == [], f"the suffix rule took real vocabulary with it: {missing}"


def test_no_committed_row_carries_an_obscenity_label(
    committed_anagram: GameWordlist, committed_themed: GameWordlist
) -> None:
    """THE defect-2 Oracle for the obscenity rule: the board is not a place for one."""
    rules = derive.load_registry(_REGISTRY).servingRules
    for wordlist in (committed_anagram, committed_themed):
        left = [
            row.word
            for row in wordlist.words
            if row.definitionTa
            and derive.is_marked_obscene([row.definitionTa], rules.obscenityMarkers)
        ]
        assert left == [], f"{wordlist.gameId} still serves {left}"
    assert PUNDAI not in {row.word for row in committed_anagram.words}


def test_a_word_that_merely_discusses_obscenity_is_still_served(
    committed_anagram: GameWordlist,
) -> None:
    """A bare aabaasa substring was measured at 1 true hit in 12; these are four
    of the eleven it would have taken, and vanmai is why the marker reads sense
    zero rather than every sense."""
    served = {row.word for row in committed_anagram.words}
    missing = [word for word in _NOT_OBSCENE if word not in served]
    assert missing == [], f"the obscenity marker took ordinary vocabulary: {missing}"


def test_the_two_derivable_rules_did_the_work_the_ledger_claims(
    committed_anagram: GameWordlist,
) -> None:
    """Both buckets are measurements, recomputed here without calling select()."""
    rules = derive.load_registry(_REGISTRY).servingRules
    selection = committed_anagram.selection
    obscene = participial = 0
    for row in derive.read_rows(
        derive.load_meta(_META), _REPO_ROOT, selection.wordClasses
    ):
        if not (
            selection.minLength <= row.length <= selection.maxLength
            and row.attestations >= selection.minAttestations
            and row.tier1Attestations >= selection.minTier1Attestations
            and row.frequency >= selection.minFrequency
            and row.definitionTa is not None
        ):
            continue
        if derive.is_marked_obscene(row.definitionTa, rules.obscenityMarkers):
            obscene += 1
        elif derive.ends_in_participial_suffix(
            segment(row.word), rules.participialSuffixes
        ):
            participial += 1

    assert committed_anagram.counters.obscene == obscene
    assert committed_anagram.counters.participial == participial
    # The reach both rules were reviewed at, counted rather than sampled: 1,065
    # participles and 4 labelled rows out of the 32,122 served before them.
    assert committed_anagram.counters.participial == 1065
    assert committed_anagram.counters.obscene == 4


def test_the_committed_deny_list_validates_at_the_size_it_was_reviewed_at() -> None:
    """123 grammar words and 65 names - a curated list, counted, not sampled."""
    denylist = derive.load_denylist(_DENYLIST)

    assert len(denylist.functionWords) == 123
    assert len(denylist.properNouns) == 65
    assert len(denylist.words()) == 188
    assert denylist.note.strip()


def test_no_denied_word_survives_in_any_committed_set(
    committed_anagram: GameWordlist, committed_themed: GameWordlist
) -> None:
    """THE row 16 Oracle: the board is what this list says it is."""
    denied = derive.load_denylist(_DENYLIST).words()
    for wordlist in (committed_anagram, committed_themed):
        still_served = sorted(denied & {row.word for row in wordlist.words})
        assert still_served == [], f"{wordlist.gameId} still serves {still_served}"


def test_the_words_deliberately_kept_are_not_on_the_deny_list() -> None:
    """Real vocabulary a cruder rule would have taken; the note names them all.

    A part-of-speech rule was measured and rejected because ``pos`` is a UNION
    across 21 sources, so appa (father) and arasu (government) both carry
    ``interjection``. These words are the cost that rule would have had, and
    this test is what stops the next contributor re-discovering it.
    """
    denylist = derive.load_denylist(_DENYLIST)
    denied = denylist.words()

    for word in _KEPT:
        assert word not in denied, f"{word} is real vocabulary, not grammar"
        assert word in denylist.note, f"the note must name {word} as kept"


def test_every_kept_word_is_still_served(committed_anagram: GameWordlist) -> None:
    """Naming them in a note is cheap; the assertion is that they reached a player."""
    served = {row.word for row in committed_anagram.words}
    missing = [word for word in _KEPT if word not in served]
    assert missing == [], f"the deny-list took real vocabulary with it: {missing}"


def test_the_deny_list_did_the_work_the_ledger_claims(
    committed_anagram: GameWordlist,
) -> None:
    """The bucket is a measurement: it equals the denied words the gates let through.

    The two derivable rules run BEFORE the deny-list, so a denied surface they
    already stopped is charged to them - which is what keeps this bucket the
    honest measure of what hand curation ALONE still buys.
    """
    denied = derive.load_denylist(_DENYLIST).words()
    rules = derive.load_registry(_REGISTRY).servingRules
    selection = committed_anagram.selection
    stopped_here = {
        row.word
        for row in derive.read_rows(
            derive.load_meta(_META), _REPO_ROOT, selection.wordClasses
        )
        if row.word in denied
        and selection.minLength <= row.length <= selection.maxLength
        and row.attestations >= selection.minAttestations
        and row.tier1Attestations >= selection.minTier1Attestations
        and row.frequency >= selection.minFrequency
        and row.definitionTa is not None
        and not derive.is_marked_obscene(row.definitionTa, rules.obscenityMarkers)
        and not derive.ends_in_participial_suffix(
            segment(row.word), rules.participialSuffixes
        )
    }

    assert committed_anagram.counters.denylisted == len(stopped_here)


def test_no_committed_row_carries_a_zero_frequency(
    committed_anagram: GameWordlist,
) -> None:
    """minFrequency is the gate doing the most work; a zero would mean it slipped."""
    assert min(row.frequency for row in committed_anagram.words) >= 1


def test_every_committed_row_records_its_served_fan_out(
    committed_anagram: GameWordlist,
) -> None:
    served: dict[tuple[str, ...], list[str]] = {}
    for row in committed_anagram.words:
        served.setdefault(derive.multiset_key(row.ezhuthu), []).append(row.word)

    for row in committed_anagram.words:
        sharing = served[derive.multiset_key(row.ezhuthu)]
        assert row.anagramFanOut == len(sharing), row.word
        assert row.word in sharing

    # A word counts ITSELF, so the floor is 1 - a solitary word is served, not
    # rejected, and no row may claim 0.
    assert min(row.anagramFanOut for row in committed_anagram.words) == 1
    assert committed_anagram.words, "the anagram set is empty"


def test_the_committed_set_serves_both_solitary_and_shared_words(
    committed_anagram: GameWordlist,
) -> None:
    """Both populations exist, so a Game can rely on the signal being real."""
    fan_out = [row.anagramFanOut for row in committed_anagram.words]
    assert any(count == 1 for count in fan_out)
    assert any(count > 1 for count in fan_out)


def test_every_committed_stratum_is_a_quarter_of_the_committed_set(
    committed_anagram: GameWordlist,
) -> None:
    total = len(committed_anagram.words)
    order = sorted(committed_anagram.words, key=lambda row: (-row.frequency, row.word))
    for position, row in enumerate(order):
        assert row.frequencyStratum == position * QUARTILES // total + 1, row.word
    # Every quarter is occupied, or the difficulty bands have nothing to draw on.
    assert {row.frequencyStratum for row in committed_anagram.words} == {1, 2, 3, 4}


def test_committed_counters_account_for_every_published_lexicon_row(
    committed_anagram: GameWordlist,
    committed_themed: GameWordlist,
) -> None:
    for wordlist in (committed_anagram, committed_themed):
        counters = wordlist.counters
        assert counters.lexiconRows == (
            counters.outsideLength
            + counters.outsideClass
            + counters.outsideCategories
            + counters.outsidePos
            + counters.belowAttestations
            + counters.belowFrequency
            + counters.withoutMeaning
            + counters.obscene
            + counters.participial
            + counters.denylisted
            + counters.capped
            + counters.rowsKept
        )
        assert counters.rowsKept == len(wordlist.words)


# --------------------------------------------------------------------------
# 5. Coverage + schema over the real artifact
# --------------------------------------------------------------------------


def test_the_committed_set_clears_the_served_floor(
    committed_anagram: GameWordlist,
) -> None:
    """Row 12 decision 15, in the units it was stated in: 6,000 rows at 3-6 ezhuthu."""
    in_band = [row for row in committed_anagram.words if 3 <= len(row.ezhuthu) <= 6]
    assert len(in_band) == len(committed_anagram.words)
    assert len(in_band) >= _SERVED_FLOOR


def test_committed_set_is_non_empty_at_every_target_length(
    committed_anagram: GameWordlist,
) -> None:
    selection = committed_anagram.selection
    lengths = {len(row.ezhuthu) for row in committed_anagram.words}
    for target in range(selection.minLength, selection.maxLength + 1):
        assert target in lengths, f"no {target}-ezhuthu word in the anagram set"


def test_every_committed_row_validates_against_the_contract(
    committed_anagram: GameWordlist,
) -> None:
    for row in committed_anagram.words:
        # Re-validating each row proves the file's rows are the contract's rows,
        # not merely that the envelope parsed.
        GameWord.model_validate(row.model_dump())
        assert row.ezhuthu == segment(row.word)
        assert row.hints is not None
        assert row.hints.firstEzhuthu == row.ezhuthu[0]
        assert row.hints.length == len(row.ezhuthu)


def test_committed_rows_are_unique(committed_anagram: GameWordlist) -> None:
    words = [row.word for row in committed_anagram.words]
    assert len(set(words)) == len(words)


def test_committed_set_omits_an_invented_category(
    committed_anagram: GameWordlist,
) -> None:
    """The hints block carries only what a word's own SPELLING yields.

    A row carries the lexicon's English category SLUGS; the Tamil tag a player
    reads is hint wording and lives in config/daily-generator.json beside the
    templates. A Tamil label baked into a dataset could only be corrected by a
    rebuild.
    """
    raw = json.loads(_ANAGRAM.read_text(encoding="utf-8"))
    labels = json.loads(
        (_REPO_ROOT / "config" / "daily-generator.json").read_text(encoding="utf-8")
    )["games"][0]["categoryLabels"]
    for row in raw["words"]:
        assert set(row["hints"]) == {"firstEzhuthu", "length"}
        for category in row.get("categories", []):
            assert category not in labels.values()


def test_a_served_row_keeps_the_lexicons_first_sense_not_its_list(
    tmp_path: Path,
) -> None:
    """A Game has one display slot, so senses two and beyond have no reader.

    Sense zero is not an arbitrary pick: the lexicon orders senses
    most-authoritative-source first, so it is the value the single-slot rule
    published before the list existed.
    """
    senses = ["\u0baa\u0bca\u0bb0\u0bc1\u0bb3\u0bcd 1", "\u0baa\u0bca\u0bb0\u0bc1\u0bb3\u0bcd 2"]
    cut = _cut(tmp_path, [_entry(ITHAZH, definitionTa=senses)])

    assert [row.word for row in cut.words] == [ITHAZH]
    assert cut.words[0].definitionTa == senses[0]


def test_a_served_row_carries_the_meaning_columns_a_hint_is_built_from(
    tmp_path: Path,
) -> None:
    synonyms = ["\u0b85", "\u0b86"]
    cut = _cut(
        tmp_path,
        [
            _entry(
                ITHAZH,
                translationEn="petal",
                synonymsTa=synonyms,
                categories=["flowers"],
            )
        ],
    )

    row = cut.words[0]
    assert row.translationEn == "petal"
    assert row.synonymsTa == synonyms
    assert row.categories == ["flowers"]


def test_a_row_the_lexicon_says_nothing_about_carries_no_meaning_columns(
    tmp_path: Path,
) -> None:
    """An absent column is absent, never a defaulted empty list on every row."""
    cut = _cut(tmp_path, [_entry(ITHAZH)], requireMeaning=False)

    row = cut.words[0]
    assert row.translationEn is None
    assert row.synonymsTa is None
    assert row.categories is None
    assert "synonymsTa" not in row.model_dump(exclude_none=True)


def test_registered_paths_are_relative_and_posix() -> None:
    registry = derive.load_registry(_REGISTRY)
    for spec in registry.sets:
        assert not spec.out.startswith("/")
        assert "\\" not in spec.out
    assert not registry.lexiconPath.startswith("/")
    assert not registry.denylistPath.startswith("/")
    assert "\\" not in registry.denylistPath


def test_the_committed_registry_validates() -> None:
    registry = derive.load_registry(_REGISTRY)
    assert [spec.gameId for spec in registry.sets] == [
        "anagram",
        "missing-letters",
        "wordle",
        _THEMED_GAME_ID,
    ]
    assert registry.lexiconPath == "datasets/lexicon/lexicon.meta.json"
    assert registry.denylistPath == "config/served-denylist.json"
    for spec in registry.sets:
        assert spec.selection.wordClasses == ["headword"]


def test_the_missing_letters_set_moves_only_its_length_floor() -> None:
    """What makes a word fair to be ASKED FOR does not depend on the board.

    Every serving gate is the anagram's; the one knob that moves is the length
    floor, and it moves because the mechanic changes what the player is given -
    blanking one ezhuthu of a three-ezhuthu word leaves two letters of context,
    and fewer than half of those masks have a single served answer.
    """
    registry = derive.load_registry(_REGISTRY)
    ordinary = next(entry for entry in registry.sets if entry.gameId == "anagram")
    missing = next(entry for entry in registry.sets if entry.gameId == "missing-letters")

    assert missing.selection.minLength == 4
    assert ordinary.selection.minLength == 3
    assert missing.selection.model_dump(exclude={"minLength"}) == (
        ordinary.selection.model_dump(exclude={"minLength"})
    )


def test_the_wordle_set_moves_only_its_length_bounds() -> None:
    """Same gates again, and a length PINNED at both ends rather than ranged.

    A wordle's board, its keyboard readout and its shareable grid all assume one
    fixed width, so the set may not hold two. Six rather than the roadmap's five
    is a measurement that runs opposite to English: Tamil's alphabet stays
    effectively constant across lengths, so an extra position is an extra
    constraint rather than an extra degree of freedom, and the simulated median
    solve falls from 10 guesses at four ezhuthu to 7 at five and 5 at six.
    """
    registry = derive.load_registry(_REGISTRY)
    ordinary = next(entry for entry in registry.sets if entry.gameId == "anagram")
    wordle_set = next(entry for entry in registry.sets if entry.gameId == "wordle")

    assert wordle_set.selection.minLength == wordle_set.selection.maxLength == 6
    assert wordle_set.selection.model_dump(exclude={"minLength", "maxLength"}) == (
        ordinary.selection.model_dump(exclude={"minLength", "maxLength"})
    )


def test_the_themed_set_narrows_the_ordinary_selection_and_relaxes_nothing() -> None:
    """A theme is the same gates plus a dimension - never a gate moved sideways."""
    registry = derive.load_registry(_REGISTRY)
    ordinary = next(entry for entry in registry.sets if entry.gameId == "anagram")
    themed = next(entry for entry in registry.sets if entry.gameId == _THEMED_GAME_ID)

    assert themed.selection.categories, "a themed set must name its dimension"
    assert ordinary.selection.categories is None
    assert themed.selection.model_dump(
        exclude={"categories", "pos"}
    ) == ordinary.selection.model_dump(exclude={"categories", "pos"})


# --------------------------------------------------------------------------
# 6. Rejection
# --------------------------------------------------------------------------


def test_no_game_may_ever_be_configured_to_serve_a_proper_noun() -> None:
    """The narrowing is the point: this cannot become a one-line config edit."""
    servable = set(get_args(ServableWordClass))
    assert servable <= set(get_args(WordClass))
    assert servable.isdisjoint(
        {
            "properNoun",
            "unclassified",
            "notAWord",
            "suspectedTypo",
            "sandhiArtifact",
            "boundStem",
            "inflected",
            "loanword",
        }
    )
    with pytest.raises(ValidationError):
        _selection(wordClasses=["properNoun"])
    with pytest.raises(ValidationError):
        _selection(wordClasses=["unclassified"])


def test_a_row_whose_ezhuthu_do_not_rejoin_is_rejected() -> None:
    with pytest.raises(ValidationError, match="does not rejoin"):
        GameWord(
            word=VAASAL,
            ezhuthu=["\u0b95"],
            frequency=1,
            frequencyStratum=1,
            anagramFanOut=1,
        )


def test_a_row_claiming_a_fan_out_below_one_is_rejected() -> None:
    """A served row always shares its tiles with at least itself."""
    with pytest.raises(ValidationError):
        GameWord(
            word=VAASAL,
            ezhuthu=segment(VAASAL),
            frequency=1,
            frequencyStratum=1,
            anagramFanOut=0,
        )


def test_a_row_claiming_a_stratum_outside_the_quartiles_is_rejected() -> None:
    for stratum in (0, QUARTILES + 1):
        with pytest.raises(ValidationError):
            GameWord(
                word=VAASAL,
                ezhuthu=segment(VAASAL),
                frequency=1,
                frequencyStratum=stratum,
                anagramFanOut=1,
            )


def test_a_row_whose_hints_disagree_with_its_ezhuthu_is_rejected() -> None:
    ezhuthu = segment(VAASAL)
    with pytest.raises(ValidationError, match="firstEzhuthu"):
        GameWord(
            word=VAASAL,
            ezhuthu=ezhuthu,
            frequency=1,
            frequencyStratum=1,
            anagramFanOut=1,
            hints=GameWordHints(firstEzhuthu=ezhuthu[1], length=len(ezhuthu)),
        )
    with pytest.raises(ValidationError, match="hints.length"):
        GameWord(
            word=VAASAL,
            ezhuthu=ezhuthu,
            frequency=1,
            frequencyStratum=1,
            anagramFanOut=1,
            hints=GameWordHints(firstEzhuthu=ezhuthu[0], length=len(ezhuthu) + 1),
        )


def test_an_unknown_row_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        GameWord.model_validate(
            {
                "word": VAASAL,
                "ezhuthu": segment(VAASAL),
                "frequency": 1,
                "frequencyStratum": 1,
                "anagramFanOut": 1,
                "freqBand": "common",
            }
        )


def test_counters_that_do_not_reconcile_are_rejected() -> None:
    with pytest.raises(ValidationError, match="lexiconRows"):
        DerivedCounters(
            lexiconRows=10,
            outsideLength=1,
            outsideClass=1,
            outsideCategories=0,
            outsidePos=0,
            belowAttestations=1,
            belowFrequency=1,
            withoutMeaning=1,
            obscene=0,
            participial=0,
            denylisted=0,
            capped=0,
            rowsKept=1,
        )


def _wordlist_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "2026-08-16T23:30",
        "changelog": [
            {"version": "2026-08-16T23:30", "change": "test", "why": "test"}
        ],
        "gameId": "anagram",
        "source": {
            "metaPath": "datasets/lexicon/lexicon.meta.json",
            "version": "2026-08-16T23:00",
            "sha256": _SHA,
            "rows": 1,
        },
        "selection": _selection().model_dump(),
        "counters": {
            "lexiconRows": 1,
            "outsideLength": 0,
            "outsideClass": 0,
            "outsideCategories": 0,
            "outsidePos": 0,
            "belowAttestations": 0,
            "belowFrequency": 0,
            "withoutMeaning": 0,
            "obscene": 0,
            "participial": 0,
            "denylisted": 0,
            "capped": 0,
            "rowsKept": 1,
        },
        "words": [
            {
                "word": VAASAL,
                "ezhuthu": segment(VAASAL),
                "frequency": 1,
                "frequencyStratum": 1,
                "anagramFanOut": 1,
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_a_wordlist_whose_count_disagrees_with_its_rows_is_rejected() -> None:
    payload = _wordlist_payload()
    payload["counters"]["rowsKept"] = 2
    payload["counters"]["lexiconRows"] = 2
    payload["source"]["rows"] = 2
    with pytest.raises(ValidationError, match="rowsKept"):
        GameWordlist.model_validate(payload)


def test_a_wordlist_whose_fan_out_disagrees_with_its_rows_is_rejected() -> None:
    """The signal is recomputed on read, so a hand-edited count cannot survive."""
    payload = _wordlist_payload()
    payload["words"][0]["anagramFanOut"] = 2
    with pytest.raises(ValidationError, match="anagramFanOut"):
        GameWordlist.model_validate(payload)


def test_a_wordlist_whose_strata_are_not_its_own_quartiles_is_rejected() -> None:
    payload = _wordlist_payload()
    payload["words"][0]["frequencyStratum"] = 2
    with pytest.raises(ValidationError, match="frequencyStratum"):
        GameWordlist.model_validate(payload)


def test_a_wordlist_disagreeing_with_the_lexicon_it_names_is_rejected() -> None:
    payload = _wordlist_payload()
    payload["source"]["rows"] = 99
    with pytest.raises(ValidationError, match="lexiconRows"):
        GameWordlist.model_validate(payload)


def test_an_incoherent_selection_is_rejected() -> None:
    with pytest.raises(ValidationError, match="minLength"):
        _selection(minLength=7, maxLength=3)
    with pytest.raises(ValidationError, match="repeated"):
        _selection(wordClasses=["headword", "headword"])
    with pytest.raises(ValidationError):
        _selection(wordClasses=[])
    with pytest.raises(ValidationError, match="minTier1Attestations"):
        _selection(minAttestations=1, minTier1Attestations=2)


def test_an_incoherent_dimension_is_rejected() -> None:
    """A dimension is a SET written as a list, so order must not be information."""
    with pytest.raises(ValidationError, match="categories must be sorted"):
        _selection(categories=["nature", "birds"])
    with pytest.raises(ValidationError, match="categories must be sorted"):
        _selection(categories=["birds", "birds"])
    with pytest.raises(ValidationError, match="categories has a blank entry"):
        _selection(categories=[" "])
    with pytest.raises(ValidationError):
        _selection(categories=[])
    with pytest.raises(ValidationError, match="pos must be sorted"):
        _selection(pos=["verb", "noun"])
    with pytest.raises(ValidationError):
        # The closed vocabulary is the lexicon's; config cannot widen it.
        _selection(pos=["gerund"])


def test_a_dimension_that_is_simply_absent_is_the_ordinary_case() -> None:
    """The gates must be declared; a dimension must be OPT IN, or a set could \
narrow itself by accident."""
    payload = _selection().model_dump()
    assert payload["categories"] is None
    assert payload["pos"] is None
    for knob in ("categories", "pos"):
        without = {name: value for name, value in payload.items() if name != knob}
        assert getattr(DerivedSelection.model_validate(without), knob) is None


def test_a_selection_knob_that_is_simply_missing_is_rejected() -> None:
    """The defaults ARE the design decision; a knob landing unset is the failure."""
    for knob in (
        "wordClasses",
        "minAttestations",
        "minTier1Attestations",
        "minFrequency",
        "requireMeaning",
    ):
        payload = _selection().model_dump()
        del payload[knob]
        with pytest.raises(ValidationError, match=knob):
            DerivedSelection.model_validate(payload)


def test_two_sets_writing_to_one_path_are_rejected() -> None:
    base = {
        "version": "2026-08-16T23:30",
        "changelog": [
            {"version": "2026-08-16T23:30", "change": "test", "why": "test"}
        ],
        "lexiconPath": "datasets/lexicon/lexicon.meta.json",
        "denylistPath": "config/served-denylist.json",
        "servingRules": _RULES.model_dump(),
    }
    with pytest.raises(ValidationError, match="repeated out"):
        DerivedWordlists.model_validate(
            {
                **base,
                "sets": [
                    _spec("datasets/wordlists/derived/anagram.json"),
                    {
                        **_spec("datasets/wordlists/derived/anagram.json"),
                        "gameId": "wordle",
                    },
                ],
            }
        )
    with pytest.raises(ValidationError, match="repeated gameId"):
        DerivedWordlists.model_validate(
            {
                **base,
                "sets": [
                    _spec("datasets/wordlists/derived/anagram.json"),
                    _spec("datasets/wordlists/derived/other.json"),
                ],
            }
        )


def test_an_absolute_output_path_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DerivedWordlists.model_validate(
            {
                "version": "2026-08-16T23:30",
                "changelog": [
                    {"version": "2026-08-16T23:30", "change": "test", "why": "test"}
                ],
                "lexiconPath": "datasets/lexicon/lexicon.meta.json",
                "denylistPath": "config/served-denylist.json",
                "servingRules": _RULES.model_dump(),
                "sets": [_spec("/tmp/anagram.json")],
            }
        )


def test_a_missing_lexicon_fails_loudly(tmp_path: Path) -> None:
    registry = _tmp_repo(tmp_path, [_spec("datasets/wordlists/derived/anagram.json")])
    shutil.rmtree(tmp_path / "datasets")
    with pytest.raises(FileNotFoundError):
        rebuild(registry, tmp_path)


def test_a_registry_that_names_no_deny_list_is_rejected() -> None:
    """The knob cannot be forgotten: an absent deny-list serves denied words."""
    payload = {
        "version": "2026-08-16T23:30",
        "changelog": [
            {"version": "2026-08-16T23:30", "change": "test", "why": "test"}
        ],
        "lexiconPath": "datasets/lexicon/lexicon.meta.json",
        "servingRules": _RULES.model_dump(),
        "sets": [_spec("datasets/wordlists/derived/anagram.json")],
    }
    with pytest.raises(ValidationError, match="denylistPath"):
        DerivedWordlists.model_validate(payload)


def test_a_registry_that_names_no_serving_rules_is_rejected() -> None:
    """Same discipline as the deny-list: a forgotten rule serves what it refuses."""
    payload = {
        "version": "2026-08-16T23:30",
        "changelog": [
            {"version": "2026-08-16T23:30", "change": "test", "why": "test"}
        ],
        "lexiconPath": "datasets/lexicon/lexicon.meta.json",
        "denylistPath": "config/served-denylist.json",
        "sets": [_spec("datasets/wordlists/derived/anagram.json")],
    }
    with pytest.raises(ValidationError, match="servingRules"):
        DerivedWordlists.model_validate(payload)


def test_incoherent_serving_rules_are_rejected() -> None:
    payload = _RULES.model_dump()
    with pytest.raises(ValidationError, match="obscenityMarkers must be sorted"):
        ServingRules.model_validate({**payload, "obscenityMarkers": ["\u0baa", "\u0b85"]})
    with pytest.raises(ValidationError, match="obscenityMarkers must be sorted"):
        ServingRules.model_validate({**payload, "obscenityMarkers": ["\u0b85", "\u0b85"]})
    with pytest.raises(ValidationError, match="obscenityMarkers has a blank entry"):
        ServingRules.model_validate({**payload, "obscenityMarkers": [" "]})
    with pytest.raises(ValidationError):
        ServingRules.model_validate({**payload, "obscenityMarkers": []})
    with pytest.raises(ValidationError):
        ServingRules.model_validate({**payload, "participialSuffixes": []})
    with pytest.raises(ValidationError, match="tail has a blank ezhuthu"):
        ParticipialSuffix.model_validate(
            {"linkVowel": "\u0bbe", "tail": [" "], "minStemEzhuthu": 1, "note": "x"}
        )
    with pytest.raises(ValidationError, match="linkVowel is blank"):
        ParticipialSuffix.model_validate(
            {
                "linkVowel": " ",
                "tail": ["\u0ba9"],
                "minStemEzhuthu": 1,
                "note": "x",
            }
        )
    with pytest.raises(ValidationError):
        # A stem floor of zero would delete vaan (sky) along with the participles.
        ParticipialSuffix.model_validate(
            {
                "linkVowel": "\u0bbe",
                "tail": ["\u0ba9"],
                "minStemEzhuthu": 0,
                "note": "x",
            }
        )


def _denylist_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "2026-08-17",
        "changelog": [{"version": "2026-08-17", "change": "test", "why": "test"}],
        "note": "test deny-list",
        "functionWords": [{"word": ORU, "reason": "numeral used as an article"}],
        "properNouns": [{"word": STALIN, "reason": "given name"}],
    }
    payload.update(overrides)
    return payload


def test_the_committed_deny_list_is_the_shape_the_contract_describes() -> None:
    ServedDenylist.model_validate(
        json.loads(_DENYLIST.read_text(encoding="utf-8"))
    )


def test_an_unsorted_deny_list_is_rejected() -> None:
    """A set written as a list: the order it is written in must not be information."""
    with pytest.raises(ValidationError, match="functionWords must be sorted"):
        ServedDenylist.model_validate(
            _denylist_payload(
                functionWords=[
                    {"word": VAASAL, "reason": "test"},
                    {"word": ORU, "reason": "test"},
                ]
            )
        )


def test_a_word_denied_twice_is_rejected() -> None:
    """Within one array, and across both - two reviewers disagreeing about why."""
    with pytest.raises(ValidationError, match="denied more than once"):
        ServedDenylist.model_validate(
            _denylist_payload(
                functionWords=[
                    {"word": ORU, "reason": "test"},
                    {"word": ORU, "reason": "test"},
                ]
            )
        )
    with pytest.raises(ValidationError, match="denied more than once"):
        ServedDenylist.model_validate(
            _denylist_payload(properNouns=[{"word": ORU, "reason": "given name"}])
        )


def test_a_blank_deny_list_entry_is_rejected() -> None:
    with pytest.raises(ValidationError, match="blank word"):
        ServedDenylist.model_validate(
            _denylist_payload(functionWords=[{"word": " ", "reason": "test"}])
        )
    with pytest.raises(ValidationError, match="blank reason"):
        ServedDenylist.model_validate(
            _denylist_payload(functionWords=[{"word": ORU, "reason": " "}])
        )
    with pytest.raises(ValidationError):
        DeniedWord(word=ORU, reason="")


def test_a_deny_list_that_does_not_say_why_it_exists_is_rejected() -> None:
    """The words deliberately KEPT are the whole difference from a cruder rule."""
    payload = _denylist_payload()
    del payload["note"]
    with pytest.raises(ValidationError, match="note"):
        ServedDenylist.model_validate(payload)


def test_an_empty_deny_list_array_is_rejected() -> None:
    """An empty array and a forgotten file produce the same output; neither is a state."""
    with pytest.raises(ValidationError):
        ServedDenylist.model_validate(_denylist_payload(functionWords=[]))
    with pytest.raises(ValidationError):
        ServedDenylist.model_validate(_denylist_payload(properNouns=[]))


def test_an_unknown_deny_list_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ServedDenylist.model_validate(_denylist_payload(pos=["noun"]))
    with pytest.raises(ValidationError):
        DeniedWord.model_validate({"word": ORU, "reason": "test", "since": "2026"})
