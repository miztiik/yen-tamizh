"""The derived-wordlist registry contract (Row 9; re-pointed at the lexicon in row 12).

``config/derived-wordlists.json`` is the declarative registry the derive step
reads. It is the whole extensibility story for the DERIVED layer, mirroring what
``config/lexicon-sources.json`` is for the lexicon pipeline: adding another
Game's wordlist is a DATA change here plus a re-run of ``rebuild_wordlists`` -
never a code rewrite, and never a change to the lexicon above it or to the daily
puzzle engine below it (lexicon -> derived per-Game sets -> daily puzzles).

The selection knobs live here rather than as literals in
``wordsmith/derive.py`` because they are tunable game-balance numbers (Holy Law
#6): which ezhuthu lengths make a good puzzle, how much attestation a word needs
before a player is asked to spell it, and whether a Game serves a word whose
meaning nobody can state are design decisions, and a designer must be able to
move them without touching Python. What stays in code is the MECHANISM that
interprets them. A Game whose set needs a predicate these knobs cannot express is
the one case that costs code.

The serving GATES deliberately carry NO defaults. The defaults ARE the design
decision, and a knob that lands unset is the failure mode: a registry entry that
forgot to say what it serves must fail to validate rather than quietly serve
everything. The two selection DIMENSIONS are the exception and default to
absent, because absent means the dimension is not applied - the opposite failure
mode, where a set that never meant to be themed silently narrows to a few
hundred rows.

``denylistPath`` names the one input the knobs cannot express: the curated list
of words that are real Tamil and still make a bad puzzle (row 16). It hangs off
the registry rather than off a set, because it is true of every Game.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import GameId, RelPath
from yen_tamizh_backend.contracts.lexicon import PartOfSpeech

# The word classes a Game may EVER be configured to serve - deliberately a
# strict subset of the lexicon's ten-member ``WordClass``.
#
# Selection is an allow-list of classes, so a class absent from this type can
# never reach a player, not even through a one-line config edit. The eight
# excluded classes are excluded for reasons no Game overrides: ``properNoun`` is
# a person or a party and is never a puzzle answer; ``unclassified`` is an
# ABSENT verdict and ``notAWord`` a confident negative; ``suspectedTypo``,
# ``sandhiArtifact`` and ``boundStem`` are scrape damage and fragments;
# ``inflected`` hands the player its own suffix as a visible tile; ``loanword``
# has orthography no more settled than a colloquial form. Widening this type is
# a reviewed contract change, which is exactly the ceremony that the proper
# nouns previously served by the anagram never got.
#
# ``headword`` is what the anagram serves: the player must PRODUCE an exact
# ezhuthu sequence, and only a settled dictionary spelling can be asked for.
# ``colloquial`` is here for the Games where a player RECOGNISES a spelling
# rather than producing it (word-search, missing-letters); the anagram's
# registry entry does not name it.
ServableWordClass = Literal["headword", "colloquial"]


class DerivedSelection(BaseModel):
    """Which lexicon rows a derived set SERVES. Every knob is tunable data.

    The lexicon is everything the pipeline knows; this is the far smaller set a
    player is actually asked to spell. PRESENT and SERVED are different
    populations on purpose, and these knobs are the whole difference.

    ``wordClasses`` is an ALLOW-LIST, never a deny-list, so a word the
    classifier could not place cannot reach a player by omission.
    ``minLength`` / ``maxLength`` count EZHUTHU, not code points - the unit
    every Game plays in (Row 6). ``minAttestations`` together with
    ``minTier1Attestations`` is the composition rule: how many word-hood
    authorities called this a word, and how many of those were dictionaries
    rather than bare listings. Two bare wordlists agreeing is not evidence - a
    spellchecker list is several times the size of the largest dictionary and
    co-occurs with nearly any orthographically legal string. ``minFrequency`` is
    the absolute floor that keeps a museum piece off the board.
    ``requireMeaning`` keeps out words the game could not explain once the
    player had solved them. ``maxWords`` caps the committed artifact (``null``
    means uncapped); a derived set is a build artifact in git, so an uncapped one
    is an unbounded commit.

    There is deliberately no anagram knob. Whether a word's tiles also spell
    something else is RECORDED on the emitted row as ``anagramFanOut``, never
    used to admit or reject: a scramble of a word with no second arrangement is
    a perfectly ordinary puzzle, and demanding a partner cut the served set by
    two orders of magnitude while selecting for bound stems, because fragments
    are what collide with real words.

    ``categories`` and ``pos`` are the two SELECTION DIMENSIONS, and they are a
    different kind of knob from the six gates above. Each keeps the rows whose
    own set-valued column INTERSECTS the one named here - a row tagged both
    ``birds`` and ``animals`` satisfies a selection naming either. Both are
    OPTIONAL, and absent means the dimension is not applied at all: that is the
    only honest default, because neither may ever gate admission for an ordinary
    set. Fewer than 3,000 published headwords carry a category, and how far
    ``pos`` reaches over the served set is unmeasured, so a set that named one by
    accident would collapse to a few hundred rows or to none. A set that names
    one is a THEMED set, drawn only on the days a whole themed playlist can be
    filled from it.

    This model is shared: the registry declares it and the emitted wordlist
    echoes back the selection that produced it, so a reviewer reading a diff can
    see which knob moved. Defining it once is why the two cannot disagree.
    """

    model_config = ConfigDict(extra="forbid")

    wordClasses: list[ServableWordClass] = Field(min_length=1)
    minLength: int = Field(ge=1)
    maxLength: int = Field(ge=1)
    minAttestations: int = Field(ge=0)
    minTier1Attestations: int = Field(ge=0)
    minFrequency: int = Field(ge=0)
    requireMeaning: bool
    maxWords: int | None = Field(default=None, ge=1)
    # The normalized theme tags of config/lexicon-sources.json's categoryAliases
    # - which is what lets a theme be renamed, widened or narrowed without a
    # code change (a theme ships as a GROUP of categories, never a single one:
    # the largest single theme is a couple of hundred rows before the gates).
    categories: list[str] | None = Field(default=None, min_length=1)
    pos: list[PartOfSpeech] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _selection_is_coherent(self) -> Self:
        if self.minLength > self.maxLength:
            raise ValueError(
                f"minLength {self.minLength} must be <= maxLength {self.maxLength}"
            )
        if len(set(self.wordClasses)) != len(self.wordClasses):
            raise ValueError(f"wordClasses has a repeated entry: {self.wordClasses}")
        for name, dimension in (("categories", self.categories), ("pos", self.pos)):
            if dimension is None:
                continue
            # A set written as a list: the order it is written in must not be
            # information, and a repeat would look like it weighted a tag.
            if list(dimension) != sorted(set(dimension)):
                raise ValueError(f"{name} must be sorted and deduped: {dimension}")
            if any(not str(entry).strip() for entry in dimension):
                raise ValueError(f"{name} has a blank entry: {dimension}")
        # The row shape already refuses a row whose tier-1 count exceeds its
        # total, so a tier-1 requirement above the total is unsatisfiable
        # arithmetic that would silently serve nothing.
        if self.minTier1Attestations > self.minAttestations:
            raise ValueError(
                f"minTier1Attestations {self.minTier1Attestations} exceeds "
                f"minAttestations {self.minAttestations}, which no row can satisfy"
            )
        return self


class DerivedSet(BaseModel):
    """One registered derived set: who consumes it and where it lands.

    ``gameId`` is the registry's unique key. A Game that runs themed days
    registers more than one set - its ordinary one plus a themed variant per
    theme - so a themed set's id names the THEME (``themed-nature``) while the
    Game that draws it is named in ``config/daily-generator.json``, which is the
    file that decides which set a day is filled from.
    """

    model_config = ConfigDict(extra="forbid")

    gameId: GameId
    out: RelPath
    selection: DerivedSelection
    note: str | None = None


class DerivedWordlists(SchemaModel):
    """The registry: one lexicon in, one derived set out per registered Game."""

    # The lexicon META document, not the directory holding the published files.
    # Every partition is resolved from that document's own table, so the derived
    # layer never globs a directory and never guesses a filename.
    lexiconPath: RelPath
    # The curated served deny-list. It sits on the REGISTRY rather than on a
    # set, because it is not a selection knob: what makes a word unservable -
    # that it is Tamil grammar, or a surname a news corpus made frequent - is
    # true of every Game, and a per-set deny-list would let the next set opt
    # out of it by omission. Config rather than a Python literal for the same
    # reason ``lexiconPath`` is (Holy Law #6).
    denylistPath: RelPath
    sets: list[DerivedSet] = Field(min_length=1)

    @model_validator(mode="after")
    def _sets_are_distinct(self) -> Self:
        # A repeated gameId or output path means one set silently overwrites
        # another - a whole Game's wordlist vanishing without an error.
        for field_name in ("gameId", "out"):
            seen = [getattr(entry, field_name) for entry in self.sets]
            if len(set(seen)) != len(seen):
                raise ValueError(f"derived sets have a repeated {field_name}")
        return self
