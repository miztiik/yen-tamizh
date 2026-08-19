"""The hint ladder every Game's generator renders its rungs from.

A rung is the same idea whichever Game asks for it: take what the lexicon
already knows about a served row, render one honest sentence in Tamil, and
charge for it - or, when the row cannot answer that rung, drop it rather than
invent one. None of that reasoning is about tiles or blanks, so it lives here
and each Game brings two things of its own:

- **its FIELD VOCABULARY** - which of the fields a served row can fill this
  Game is allowed to sell. That is not decoration. The anagram sells the first
  ezhuthu because its tiles are shuffled and knowing which one leads is real
  progress; the missing-letters board has already PRINTED every ezhuthu it is
  not hiding, so the same rung is either a fact on screen or the answer itself.
  A vocabulary per Game is what keeps a config template from selling either.
- **the VALUES** it can fill for a particular row and a particular kind of day.

Two mistakes stay carefully distinct, because they mean opposite things. A
template naming a field OUTSIDE its Game's vocabulary fails the bake loudly - it
is a typo in config, and a typo that silently shortened the ladder would never
be found. A template naming a field INSIDE the vocabulary that this ROW cannot
fill has its rung skipped and the next rung moves up - that is the honest state
of a lexicon where barely one word in fifteen carries a category.
"""

from __future__ import annotations

from collections.abc import Mapping
from string import Formatter

from yen_tamizh_backend.contracts.common import Hint
from yen_tamizh_backend.contracts.daily_generator import GameGeneration
from yen_tamizh_backend.contracts.game_wordlist import GameWord


def template_fields(template: str) -> set[str]:
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


def build_hints(
    row: GameWord,
    spec: GameGeneration,
    limit: int,
    values: Mapping[str, str],
    vocabulary: frozenset[str],
) -> list[Hint]:
    """Render the first ``limit`` rungs this row can HONESTLY answer.

    Not the first ``limit`` CONFIGURED rungs. A rung whose template names a
    field absent from ``values`` is skipped and the next rung moves up - a
    ladder that is sometimes two rungs is correct.

    A rendered rung containing the answer word is dropped as well. Tamil
    synonymy is dense enough that a gloss occasionally spells its own headword,
    and a paid hint that prints the answer is worse than no hint at all.

    ``limit`` is the app config's per-Game allowance, so a day never bakes more
    help than the game is willing to offer.
    """
    if limit <= 0:
        return []
    hints: list[Hint] = []
    for spec_hint in spec.hints:
        fields = template_fields(spec_hint.template)
        unknown = fields - vocabulary
        if unknown:
            raise KeyError(
                f"hint {spec_hint.kind!r} names {sorted(unknown)}, which {spec.gameId!r} "
                f"cannot sell: {sorted(vocabulary)}"
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
