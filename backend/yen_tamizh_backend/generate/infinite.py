"""Bake one Game's Infinite pool: many boards, and the index over them (Row 22).

The Infinite Mode is an endless stream and there is no runtime generator (Holy
Law #1), so "endless" has to be spelled out in advance: every board the stream
can ever deal is baked here into ``frontend/public/pool/<gameId>/``, one puzzle
per file, with a small index beside them.

Like the Journey, this module is deliberately thin. Which boards a Game can
build, how hard each one is and what its payload looks like are all answered by
the day loop's own registry (``daily.BUILDERS``); registering a Game there is
still the whole cost of giving it a pool. What this module owns is the three
ways a pool is not a day:

- **A pool is a DEPTH, not a playlist.** A day deals one word per slot; a pool
  walks a whole difficulty bucket and takes rows until it hits the configured
  ceiling or the bucket runs out of usable ones. ``poolPerBand`` is therefore a
  ceiling rather than a quota - a band that cannot fill it stops early and the
  index says so, because a pool padded out with a repeat would be an endless
  stream that deals the same board twice under two names.
- **The ledger is POOL-local, and per Game.** A word may not be asked for twice
  inside one Game's pool, and the bank is not consulted in either direction -
  for the Journey's reason: a pool that avoided every word the Daily had ever
  served would stop being reproducible the moment the cron ran, and a Daily that
  avoided every pooled word would shrink for a reason the player cannot see. Two
  different Games may hold the same word, because meeting a word as a scramble
  and later as a crossword clue is two puzzles, not one repeated.
- **A pool is seeded by its own address, never by a date.** The seed text is
  ``pool|<gameId>``, so re-baking a year later gives the same boards in the same
  order and the same file gets the same id. That is what makes the bake
  idempotent and what makes a player's ``seenInfiniteIds`` mean anything across
  releases.

Nothing here reads a clock or writes a file; the entry point in
``scripts/generate_infinite.py`` owns those edges.
"""

from __future__ import annotations

from collections.abc import Mapping

from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.daily_generator import DailyGenerator
from yen_tamizh_backend.contracts.game_wordlist import GameWordlist
from yen_tamizh_backend.contracts.pool_index import PoolEntry, PoolIndex, PoolItem
from yen_tamizh_backend.generate import Unbuildable, daily

POOL_INDEX_VERSION = "2026-08-21T22:00"
POOL_INDEX_CHANGELOG = [
    ChangelogEntry(
        version=POOL_INDEX_VERSION,
        change="Initial pool index: every pooled puzzle of one Game, with its band.",
        why=(
            "Row 22 - the Infinite Mode plays a pre-generated pool because there "
            "is no runtime generator (Holy Law #1), and a stream that fetched the "
            "whole pool to start would be the opposite of endless on a phone. The "
            "index is the smallest thing that can answer 'what may I play next': "
            "an id and a band per item, so the Mode can honour the player's "
            "difficulty filter and its own anti-repeat window without opening a "
            "single board it is not about to play."
        ),
    )
]

# The seed every pooled board is built from. A constant rather than a date: a
# pool is content, and content that drifted on every rebuild could not keep the
# promise that item 00042 of a Game is the same puzzle it was last release.
POOL_SEED = "pool"

# How wide a pool id is rendered; the contract pins the same width.
_ID_WIDTH = 5


def pool_seed(game_id: str) -> str:
    """The seed text one Game's whole pool is built from."""
    return f"{POOL_SEED}|{game_id}"


def pool_id(ordinal: int) -> str:
    """The id (and file stem) of the ordinal-th item of a pool."""
    return f"{ordinal:0{_ID_WIDTH}d}"


def build_pool(
    game_id: str,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: Mapping[str, GameWordlist],
    per_band: int | None = None,
) -> list[PoolItem]:
    """Bake one Game's whole pool, easy band first, in a stable order.

    The bands are walked in the order the registry declares them, and within a
    band the rows come from the same stratified draw the Daily uses - so any
    prefix of a band's pool is a proportional sample of how familiar its words
    are, and a player who only ever plays the first few dozen is not handed the
    rarest quarter of the language.

    A row is skipped, never retried, when the Game cannot build it or when the
    board it produces would ask for a word this pool has already asked for. That
    is the same treatment ``pick_words`` gives an unbuildable row, one layer in:
    the pool has no slot it must fill, so it can afford to be strict where a day
    has to fall back.
    """
    specs = {spec.gameId: spec for spec in generator.games}
    spec = specs.get(game_id)
    if spec is None:
        raise ValueError(f"{game_id!r} has no generator: {sorted(specs)}")
    ceiling = generator.poolPerBand if per_band is None else per_band

    wordlist = wordlists[spec.wordlist]
    prepared = daily.builder_for(game_id).prepare(wordlist, spec)
    hint_limit = daily.hint_limit_for(app_config, game_id)
    seed = pool_seed(game_id)
    buckets = daily.bucket_candidates(wordlist.words, spec)

    ledger: set[str] = set()
    items: list[PoolItem] = []
    for band in spec.difficulties:
        made = 0
        if ceiling == 0:
            break
        for row in daily.stratified_order(buckets[band.id], f"{seed}|{band.id}"):
            if made >= ceiling:
                break
            if row.word in ledger:
                continue
            try:
                item = daily.build_item(
                    row,
                    spec,
                    seed,
                    hint_limit,
                    band.id,
                    False,
                    prepared,
                    frozenset(ledger),
                )
            except Unbuildable:
                continue
            words = daily.answer_words(item.payload)
            # A multi-word board is allowed to REPEAT a served word rather than
            # ship short (daily.py's degrade policy), and inside a pool that
            # would be a second copy of a word the stream has already asked for.
            # A day has no alternative; a pool does - take the next row.
            if any(word in ledger for word in words):
                continue
            ledger.update(words)
            items.append(
                PoolItem(
                    id=pool_id(len(items)),
                    gameId=item.gameId,
                    packId=item.packId,
                    difficulty=item.difficulty,
                    payload=item.payload,
                )
            )
            made += 1
    return items


def build_index(game_id: str, items: list[PoolItem]) -> PoolIndex:
    """The manifest over one Game's baked pool."""
    return PoolIndex(
        version=POOL_INDEX_VERSION,
        changelog=POOL_INDEX_CHANGELOG,
        gameId=game_id,
        totalCount=len(items),
        items=[PoolEntry(id=item.id, difficulty=item.difficulty) for item in items],
    )


def pool_games(app_config: AppConfig) -> list[str]:
    """The Games a pool is baked for: the Daily's own ring.

    Reusing that ring rather than minting a second list is deliberate. It is
    already the answer to "which Games are live", the frontend already reads it,
    and a separate roster would let a Game be dealt by one Mode and not the
    other for no reason a player could see - or worse, let the Infinite stream
    ask for a pool nobody baked.
    """
    return list(app_config.daily.games)
