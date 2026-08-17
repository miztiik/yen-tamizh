"""Turn one derived-wordlist row into a playable ``anagram-puzzle`` payload.

The Game (Row 12) knows how to play an anagram; this knows how to BUILD one. It
takes a word the derived layer already vouched for, scrambles its ezhuthu, and
attaches the rules the config declares - attempts, a time limit, a head start,
the ladder of hints the row can honestly answer, what the word means, and the
other words its tiles spell.

Three guarantees this module owns:

- **The scramble is never the answer.** A pre-solved puzzle is not a puzzle
  (Palm). The seeded shuffle is rotated until it differs from the solved order.
- **A tile is an ezhuthu.** Tiles come from the row's ``ezhuthu`` array (Row 6
  segmentation), never from a code-point split, so they rejoin to exactly the
  answer word.
- **A hint is honest, Tamil, and never the answer.** A rung this row cannot
  answer is dropped rather than invented, a phrase carrying Latin script is
  never sold, and a rendered rung that would spell the answer out is dropped
  too.

Difficulty lives here too, and it reads TWO axes: how many tiles a word has and
how familiar it is. Length alone is anti-correlated at both tails.
"""

from __future__ import annotations

from collections.abc import Iterable
from string import Formatter

from yen_tamizh_backend.contracts.anagram_puzzle import AnagramPuzzle
from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.common import Hint
from yen_tamizh_backend.contracts.daily_generator import GameGeneration
from yen_tamizh_backend.contracts.game_wordlist import GameWord
from yen_tamizh_backend.generate.seed import seeded_shuffle

_SCHEMA_VERSION = "2026-08-17T18:00"
_CHANGELOG = [
    ChangelogEntry(
        version=_SCHEMA_VERSION,
        change=(
            "Added the optional meaning, translationEn and alsoValid fields to "
            "the baked payload."
        ),
        why=(
            "Row 14 - a player who solves a word should learn what it means, "
            "and the summary is where that costs nothing. All three are "
            "RESOLVED here rather than shipped as inputs: the generator holds "
            "the lexicon columns and the whole served wordlist, so the player "
            "downloads finished display values instead of the arrays they came "
            "from. translationEn is the summary's demoted second line and "
            "never a hint, which is what gives the lexicon's English column a "
            "reader without putting English on the stage. alsoValid has to be "
            "baked at all because the Game cannot derive it - anagramFanOut is "
            "a count, and reading a wordlist at runtime is forbidden - and "
            "without it an arrangement that is real Tamil gets a flat "
            "rejection instead of 'that is a word, but not today's'. All three "
            "are absent on a row that has none, so every day baked before this "
            "still validates."
        ),
    ),
    ChangelogEntry(
        version="2026-08-13",
        change="Initial baked anagram payload: scrambled ezhuthu tiles plus rules.",
        why="Row 13 - the daily engine's first Game payload.",
    ),
]

# The CLOSED vocabulary a hint template may name. A template naming anything
# else is a typo in config and fails the bake; a template naming one of these
# that a particular ROW cannot fill has its rung skipped for that row.
#
# ``length`` is deliberately absent. The rung that charged for the tile count
# already on the player's screen was deleted, and leaving the field fillable
# would let one config line put it back.
HINT_FIELDS = frozenset({"firstEzhuthu", "category", "meaning"})


def scramble(ezhuthu: list[str], seed_text: str) -> list[str]:
    """Deterministically reorder the ezhuthu so the tray is never pre-solved.

    A rotation is enough to break the (rare) case where the seeded shuffle lands
    back on the solved order; a word whose ezhuthu are all identical has no other
    arrangement, and is returned unchanged rather than looping forever.
    """
    order = seeded_shuffle(ezhuthu, seed_text)
    for _ in range(len(order)):
        if order != ezhuthu:
            return order
        order = order[1:] + order[:1]
    return order


def _template_fields(template: str) -> set[str]:
    """Every field name a hint template names, positional ones included as ``""``."""
    return {name for _, name, _, _ in Formatter().parse(template) if name is not None}


def category_tag(row: GameWord, spec: GameGeneration) -> str | None:
    """The bare Tamil tag for this row's category, or ``None`` if it has no rung.

    The lexicon's categories are English slugs, so the Tamil comes from the
    generator config beside the hint wording. Categories are read in the row's
    own sorted order and the first one the config names AND that does not spell
    the answer out wins, so which tag a word gets is a pure function of the data
    rather than of dict order.

    ``None`` is the common answer: barely one served word in fifteen carries a
    category at all, which is exactly why a missing rung is skipped rather than
    raised.
    """
    for slug in row.categories or ():
        label = spec.categoryLabels.get(slug)
        if label is not None and row.word not in label:
            return label
    return None


def _meaning_candidates(row: GameWord) -> list[str]:
    """What this row could display as its meaning, best first.

    A Tamil SYNONYM leads, because it is the shortest true answer to "what does
    this mean" and it reads as Tamil rather than as a dictionary. The sense
    follows. English never appears: ``translationEn`` is not a candidate here at
    all, since a rung the player cannot read is a rung that stole score.
    """
    candidates = list(row.synonymsTa or ())
    if row.definitionTa is not None:
        candidates.append(row.definitionTa)
    return candidates


def _is_sellable(value: str, word: str) -> bool:
    """Whether this phrase may be CHARGED for as the meaning of ``word``.

    Two disqualifications, both of them "the player pays and gets nothing":

    - it spells the answer out, which is the ladder taking three points for the
      word the player is trying to build;
    - it carries Latin script. Some lexicon glosses glue a romanisation onto the
      Tamil - ``aruke`` beside its own headword - and English on a paid rung is
      banned outright, because a hint half the audience cannot read is a hint
      that stole score. The rung is dropped rather than answered in English.
    """
    if word in value:
        return False
    return not any(char.isascii() and char.isalpha() for char in value)


def sellable_meaning(row: GameWord) -> str | None:
    """The meaning this row may be CHARGED for, or ``None`` if it has none.

    Candidates are read in order and the first sellable one wins, so a single
    unusable synonym costs the rung nothing - only a row where EVERY candidate
    is unusable loses it.
    """
    return next(
        (value for value in _meaning_candidates(row) if _is_sellable(value, row.word)),
        None,
    )


def display_meaning(row: GameWord) -> str | None:
    """The meaning shown FREE on the summary once the word is already revealed.

    It is the sellable one whenever there is one, so a player who bought the
    rung meets the same words again rather than a second, different gloss. When
    nothing is sellable there is nothing left to protect - the word is on the
    screen and the summary is not charging for it - so the first candidate is
    shown as it stands.
    """
    sellable = sellable_meaning(row)
    if sellable is not None:
        return sellable
    candidates = _meaning_candidates(row)
    return candidates[0] if candidates else None


def hint_values(row: GameWord, spec: GameGeneration, themed: bool) -> dict[str, str]:
    """Exactly the hint fields this row can honestly fill, on this kind of day.

    A field absent from this map is a rung the row does not get. On a THEMED day
    ``category`` is absent for every row, not just the ones without one: the
    theme is announced free in the round header, so the rung would charge for a
    fact already on screen - and because a missing rung shortens the ladder, a
    three-rung day beside an ordinary two-rung one would announce the theme
    before the player had spent anything.
    """
    values: dict[str, str] = {}
    if row.hints is not None:
        values["firstEzhuthu"] = row.hints.firstEzhuthu
    if not themed:
        category = category_tag(row, spec)
        if category is not None:
            values["category"] = category
    meaning = sellable_meaning(row)
    if meaning is not None:
        values["meaning"] = meaning
    return values


def build_hints(
    row: GameWord, spec: GameGeneration, limit: int, themed: bool = False
) -> list[Hint]:
    """Render the first ``limit`` rungs this row can HONESTLY answer.

    Not the first ``limit`` CONFIGURED rungs. A rung whose template names a
    field this row cannot fill is skipped, and the next rung moves up - a ladder
    that is sometimes two rungs is correct, because only about one served word
    in fifteen carries a category and a raising template would fail the bake on
    the other fourteen.

    A template naming a field outside ``HINT_FIELDS`` still fails loudly. The
    two mistakes are different: a row lacking a known field is the honest state
    of the lexicon, while a template naming an unknown one is a typo in config
    that would otherwise vanish into a silently shorter ladder.

    A rendered rung containing the answer word is dropped as well. Tamil
    synonymy is dense enough that a gloss occasionally spells its own headword,
    and a paid hint that prints the answer is worse than no hint at all.

    ``limit`` is the app config's per-Game allowance, so a day never bakes more
    help than the game is willing to offer.
    """
    if limit <= 0:
        return []
    values = hint_values(row, spec, themed)
    hints: list[Hint] = []
    for spec_hint in spec.hints:
        fields = _template_fields(spec_hint.template)
        unknown = fields - HINT_FIELDS
        if unknown:
            raise KeyError(
                f"hint {spec_hint.kind!r} names {sorted(unknown)}, which is not a "
                f"hint field: {sorted(HINT_FIELDS)}"
            )
        if not fields <= values.keys():
            continue
        text = spec_hint.template.format(**values)
        if row.word in text:
            continue
        hints.append(Hint(kind=spec_hint.kind, text=text, cost=spec_hint.cost))
        if len(hints) == limit:
            break
    return hints


def build_puzzle(
    row: GameWord,
    spec: GameGeneration,
    seed_text: str,
    hint_limit: int,
    themed: bool = False,
    also_valid: Iterable[str] = (),
) -> AnagramPuzzle:
    """Build one validated anagram puzzle from a derived-wordlist row.

    ``also_valid`` is the day loop's answer to "what else do these tiles
    spell" - the OTHER words the same served set holds for this multiset. It is
    passed in rather than derived, because only the caller holds the wordlist
    the day actually drew from, which on a themed day is the theme's own set.
    """
    return AnagramPuzzle(
        version=_SCHEMA_VERSION,
        changelog=_CHANGELOG,
        word=row.word,
        tiles=scramble(list(row.ezhuthu), seed_text),
        reveal=spec.reveal,
        timeLimitSec=spec.timeLimitSec,
        attempts=spec.attempts,
        hints=build_hints(row, spec, hint_limit, themed) or None,
        meaning=display_meaning(row),
        translationEn=row.translationEn,
        alsoValid=sorted(also_valid) or None,
    )



def difficulty_of(row: GameWord, spec: GameGeneration) -> str | None:
    """The first configured band that covers the word's LENGTH and its FAMILIARITY.

    Two axes, because length alone is anti-correlated at both tails: a long
    headword is usually a compound that decomposes and is easier than its tile
    count suggests, while a short rare word is brutal and a 3-ezhuthu one is
    brute-forceable by shuffling. Bands overlap on length and tile on
    familiarity, so which band claims a word is mostly a question of how well the
    player knows it.

    ``None`` when no band claims the row - typically a short word outside the
    familiar quarters. That is a real answer, not a failure: the wordlist says
    what is SERVABLE and the bands say what is DRAWABLE, and inventing a
    difficulty for a row no band wants would put exactly the museum piece on the
    board that the second axis exists to keep off it.
    """
    length = len(row.ezhuthu)
    for band in spec.difficulties:
        if (
            band.minLength <= length <= band.maxLength
            and row.frequencyStratum <= band.maxStratum
        ):
            return band.id
    return None
