"""The per-Game derived wordlist contract (Row 9; cut over to the lexicon in row 12).

A ``game-wordlist`` is what one Game's generator draws its words from: the
subset of the published lexicon (row 11) that the Game's serving gates keep. It
is a BUILD ARTIFACT - regenerated in full by ``rebuild_wordlists``, never hand
edited - and it is not served: the game downloads the puzzles the daily engine
bakes (Row 13), not the wordlist they were baked from.

The document is a pure function of its inputs. There is deliberately no
wall-clock ``generatedAt`` field anywhere in it - not on the document and not on
``source`` either: a timestamp would make two runs over the same lexicon produce
different bytes, which is the opposite of what a reproducible derived artifact
means. ``source`` pins the exact lexicon the rows came from by CONTENT - the
meta document's path, its schema version, its sha256 and its published row count
- and git history records when the file changed (CLAUDE.md section 5). One
digest still pins a partitioned input, because ``lexicon.meta.json`` itself
carries the sha256 of every published file.

``counters`` is the integrity Oracle, enforced by the model itself, with one
bucket per serving gate, one per selection dimension, one for each of the two
derivable exclusions, and one for the curated deny-list that runs last::

    lexiconRows - outsideClass - outsideCategories - outsidePos - outsideLength
                - belowAttestations - belowFrequency - withoutMeaning
                - obscene - participial - denylisted - capped
                == rowsKept == len(words)

Every published lexicon row is accounted for by exactly one outcome, so a
selection bug cannot quietly drop words and a gate cannot quietly do nothing.
The two dimension buckets are 0 on every set that names no dimension, which is
every ordinary set - a themed set is where they carry the weight.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import QUARTILES, GameId, RelPath
from yen_tamizh_backend.contracts.derived_wordlists import DerivedSelection

_SHA256 = r"^[0-9a-f]{64}$"
_DATESTAMP = r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?$"


class GameWordHints(BaseModel):
    """The honest hint material a word's own SPELLING yields.

    Both fields are recomputed from ``ezhuthu`` on every rebuild and validated
    against it, so precomputing them cannot drift.

    ``length`` no longer feeds a hint - a rung that charges for the tile count
    already on screen was deleted - but it stays as the cheapest integrity check
    the row has: it is validated against the live segmentation, so a row whose
    parts and count disagree can never reach a generator.

    What a word MEANS is not spelling, so it is not here: those fields sit on
    ``GameWord`` itself, where the generator resolves them into rendered text.
    """

    model_config = ConfigDict(extra="forbid")

    firstEzhuthu: str = Field(min_length=1)
    length: int = Field(ge=1)


class GameWord(BaseModel):
    """One word a Game may build a puzzle from.

    ``frequency`` is the lexicon's raw count, carried through unchanged. It is
    what ``minFrequency`` gates on and what the difficulty curve reads, and it
    replaces the old rank-relative band: a band computed over a population where
    thousands of rows appear zero times is a different filter wearing the same
    name.

    ``frequencyStratum`` is which quarter of THIS SET the row's frequency puts
    it in, 1 being the most familiar. It is computed over the SERVED rows and
    nothing wider - a quartile taken over millions of lexicon surfaces would say
    nothing about the words a player is actually offered. It is the second axis
    of difficulty: length alone is anti-correlated at both tails, because long
    Tamil headwords are mostly compounds that decompose while short rare words
    are brutal.

    ``anagramFanOut`` counts how many SERVED rows share this row's ezhuthu
    multiset, including the row itself - so a word whose tiles spell nothing
    else carries ``1``, never ``0``. It is a recorded signal, not an admission
    test: a Game that knows a submitted arrangement is a different served word
    can answer "that is a word, but not today's" instead of a flat rejection,
    which is the difference between a player learning something and a player
    concluding the game cheated. It is a COUNT and stays one - the partner WORDS
    are computed at bake time, because a row carrying its own partner list would
    duplicate thousands of word lists into a committed artifact.

    The four MEANING columns are what a hint and a summary are rendered from.
    They are carried raw so the RULE that turns them into one display string
    lives in the generator, where the wording already lives, rather than being
    frozen into this artifact:

    - ``definitionTa`` is the lexicon's FIRST sense, not its list of senses. The
      lexicon orders senses most-authoritative-first and a Game has exactly one
      display slot, so senses two and beyond have no reader here while costing
      4.89 MB across the served set - a build artifact holding 34 senses so that
      one can be shown is bytes for nothing.
    - ``synonymsTa`` travels WHOLE, because it is not a ranked list: every
      member is an equally correct answer to "what does this mean", so there is
      no principled first element to keep and no principled remainder to drop -
      and the generator reads down it, because a synonym that spells out the
      answer or carries a Latin-script romanisation cannot be sold as a hint.
    - ``categories`` are the lexicon's own English slugs. The Tamil a player
      reads is hint WORDING and lives in ``config/daily-generator.json`` beside
      the templates, never here: baking a Tamil label into a dataset would mean
      correcting a word by rebuilding the set.
    - ``translationEn`` is carried for the summary's demoted second line. It is
      never a hint: a paid rung the player cannot read is a rung that stole
      score, so the meaning rung is omitted rather than answered in English.
    """

    model_config = ConfigDict(extra="forbid")

    word: str = Field(min_length=1)
    ezhuthu: list[str] = Field(min_length=1)
    frequency: int = Field(ge=0)
    frequencyStratum: int = Field(ge=1, le=QUARTILES)
    anagramFanOut: int = Field(ge=1)
    definitionTa: str | None = Field(default=None, min_length=1)
    translationEn: str | None = Field(default=None, min_length=1)
    synonymsTa: list[str] | None = Field(default=None, min_length=1)
    categories: list[str] | None = Field(default=None, min_length=1)
    hints: GameWordHints | None = None

    @model_validator(mode="after")
    def _row_is_self_consistent(self) -> Self:
        # Segmentation is non-destructive (Row 6), so a row whose parts do not
        # rebuild its word is corrupt and must never reach a generator.
        if "".join(self.ezhuthu) != self.word:
            raise ValueError(f"ezhuthu does not rejoin to {self.word!r}")
        if self.hints is None:
            return self
        if self.hints.firstEzhuthu != self.ezhuthu[0]:
            raise ValueError(
                f"hints.firstEzhuthu {self.hints.firstEzhuthu!r} != "
                f"{self.ezhuthu[0]!r} for {self.word!r}"
            )
        if self.hints.length != len(self.ezhuthu):
            raise ValueError(
                f"hints.length {self.hints.length} != ezhuthu count "
                f"{len(self.ezhuthu)} for {self.word!r}"
            )
        return self


class DerivedSource(BaseModel):
    """The exact lexicon a derived set was cut from, pinned by content.

    ``metaPath`` names ``lexicon.meta.json`` rather than the directory of
    published files, and ``sha256`` digests that one document - which itself
    carries the sha256 of every partition, so a single digest still pins a
    partitioned input. ``rows`` is the lexicon's PUBLISHED row count, which is
    what the ledger reconciles against.
    """

    model_config = ConfigDict(extra="forbid")

    metaPath: RelPath
    version: str = Field(pattern=_DATESTAMP)
    sha256: str = Field(pattern=_SHA256)
    rows: int = Field(ge=1)


class DerivedCounters(BaseModel):
    """The reconciliation ledger for one derive run - one bucket per gate.

    The buckets are listed in the order the identity is read, and a row that
    fails more than one gate is counted under the first one that stopped it.
    ``outsideClass`` comes off the lexicon's own partition table rather than
    from reading those files: selection is an allow-list, so the derived layer
    opens only the classes it serves, and the classes it will not serve are
    counted from what the meta document declares about them.

    ``outsideCategories`` and ``outsidePos`` are the two SELECTION dimensions
    rather than gates: they are 0 unless the set asked to be themed, and they
    are charged before the gates so a themed ledger reads as "of the rows this
    theme covers, here is what each gate then removed" rather than burying the
    theme's own reach inside ``outsideLength``.

    ``obscene`` and ``participial`` are the two exclusions the registry's
    ``servingRules`` derive from the row itself, charged after every gate and
    before the curated list. ``obscene`` runs first of the two because it is the
    graver reason: a surface that is both an obscenity and a participle should
    be counted where the stronger refusal is. Both sit BEFORE ``denylisted`` so
    the hand-curated list is charged only for what nothing automatic caught,
    which is what makes its number the honest measure of how much curation the
    set still needs.

    ``denylisted`` is the curated exclusion, and it is charged LAST of the
    row-level buckets - after every automatic gate and before the cap. A word an
    automatic gate already stopped is charged to that gate, so this bucket
    counts only the words the deny-list ALONE keeps off the board: how much
    hand curation the set actually needed, which is the number that says whether
    an entry still earns its line.
    """

    model_config = ConfigDict(extra="forbid")

    lexiconRows: int = Field(ge=0)
    outsideLength: int = Field(ge=0)
    outsideClass: int = Field(ge=0)
    outsideCategories: int = Field(ge=0)
    outsidePos: int = Field(ge=0)
    belowAttestations: int = Field(ge=0)
    belowFrequency: int = Field(ge=0)
    withoutMeaning: int = Field(ge=0)
    obscene: int = Field(ge=0)
    participial: int = Field(ge=0)
    denylisted: int = Field(ge=0)
    capped: int = Field(ge=0)
    rowsKept: int = Field(ge=0)

    @model_validator(mode="after")
    def _counters_reconcile(self) -> Self:
        accounted = (
            self.outsideLength
            + self.outsideClass
            + self.outsideCategories
            + self.outsidePos
            + self.belowAttestations
            + self.belowFrequency
            + self.withoutMeaning
            + self.obscene
            + self.participial
            + self.denylisted
            + self.capped
            + self.rowsKept
        )
        if accounted != self.lexiconRows:
            raise ValueError(
                f"outsideLength {self.outsideLength} + outsideClass "
                f"{self.outsideClass} + outsideCategories {self.outsideCategories} "
                f"+ outsidePos {self.outsidePos} + belowAttestations "
                f"{self.belowAttestations} + belowFrequency {self.belowFrequency} "
                f"+ withoutMeaning {self.withoutMeaning} + obscene {self.obscene} "
                f"+ participial {self.participial} + denylisted "
                f"{self.denylisted} + capped {self.capped} "
                f"+ rowsKept {self.rowsKept} != lexiconRows {self.lexiconRows}"
            )
        return self


class GameWordlist(SchemaModel):
    """One Game's derived wordlist, with the lexicon and selection that made it."""

    gameId: GameId
    source: DerivedSource
    selection: DerivedSelection
    counters: DerivedCounters
    words: list[GameWord]

    @model_validator(mode="after")
    def _rows_kept_matches_the_words(self) -> Self:
        if self.counters.rowsKept != len(self.words):
            raise ValueError(
                f"counters.rowsKept {self.counters.rowsKept} != {len(self.words)} words"
            )
        if self.counters.lexiconRows != self.source.rows:
            raise ValueError(
                f"counters.lexiconRows {self.counters.lexiconRows} != source.rows "
                f"{self.source.rows}"
            )
        return self

    @model_validator(mode="after")
    def _strata_are_the_quartiles_of_this_set(self) -> Self:
        # Recomputed rather than trusted, like every other derived field here.
        # The order is frequency descending with the word as the tie-break, so
        # it is total and the strata are reproducible; a value-based cut would
        # collapse whenever a frequency repeats, which on the rare tail it does
        # thousands of times.
        total = len(self.words)
        if total == 0:
            return self
        order = sorted(self.words, key=lambda row: (-row.frequency, row.word))
        for position, row in enumerate(order):
            expected = position * QUARTILES // total + 1
            if row.frequencyStratum != expected:
                raise ValueError(
                    f"frequencyStratum {row.frequencyStratum} != {expected} for "
                    f"{row.word!r} at position {position} of {total} served rows"
                )
        return self

    @model_validator(mode="after")
    def _fan_out_matches_the_served_rows(self) -> Self:
        # Recomputed rather than trusted, like every other derived field here:
        # a stale fan-out would have a Game tell a player their arrangement is
        # another word when this set no longer serves one.
        served: dict[tuple[str, ...], int] = {}
        for row in self.words:
            key = tuple(sorted(row.ezhuthu))
            served[key] = served.get(key, 0) + 1
        for row in self.words:
            expected = served[tuple(sorted(row.ezhuthu))]
            if row.anagramFanOut != expected:
                raise ValueError(
                    f"anagramFanOut {row.anagramFanOut} != {expected} served rows "
                    f"sharing the ezhuthu of {row.word!r}"
                )
        return self
