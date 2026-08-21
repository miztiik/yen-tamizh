"""Bake one Journey's nodes into playable boards (Row 17).

A Journey is a curated ORDER over the same Games the Daily deals, so this module
is deliberately thin: it owns the order and the ledger, and every question about
what a board looks like is answered by the day loop's own registry
(``daily.BUILDERS``). Registering a Game there is still the whole cost of adding
it to a Journey too - this module never asks which Game it is holding.

What it does own is the three ways a path is not a day:

- **A node is seeded by its own address, never by a date.** The seed text is
  ``<journeyId>|<nodeId>``, so a Journey is reproducible from its file alone and
  re-baking it a year later gives the same boards. A date would make a curated
  path drift every time it was rebuilt, which is the opposite of curated.
- **The ledger is JOURNEY-local.** A word may not appear twice inside one path,
  and the bank is not consulted in either direction: a Journey that avoided every
  word the Daily had ever served would stop being reproducible the moment the
  cron ran, and a Daily that avoided every Journey word would shrink for a reason
  the player cannot see. The two are separate content.
- **A node is dealt ONE band, and the path is the curve.** The Daily computes a
  ramp from the date; a Journey's ramp is authored, which is what a hand-made
  path is for.

Nothing here reads a clock or writes a file; the entry point in
``scripts/build_journeys.py`` owns those edges.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.daily_generator import DailyGenerator
from yen_tamizh_backend.contracts.game_wordlist import GameWordlist
from yen_tamizh_backend.contracts.journey import Journey, JourneyNode, UnlockRule
from yen_tamizh_backend.generate import daily

JOURNEY_VERSION = "2026-08-21T18:00"
JOURNEY_CHANGELOG = [
    ChangelogEntry(
        version=JOURNEY_VERSION,
        change="Initial Journey definition: an ordered path of nodes with their boards.",
        why=(
            "Row 17 - the Journey Mode walks a hand-authored path, and the path "
            "is data so that adding one is a file rather than a release. A node "
            "carries its own payload because there is no runtime generator "
            "(Holy Law #1) and a second baked file could disagree with the "
            "definition about how many nodes the path has."
        ),
    )
]

# The authored fields of a node - everything a person decides, and nothing a
# bake produces.
_SPEC_KEYS = ("id", "gameId", "difficulty", "unlockRule")


@dataclass(frozen=True)
class NodeSpec:
    """One authored level: which Game, how hard, and what opens it."""

    id: str
    gameId: str
    difficulty: str
    unlockRule: UnlockRule


@dataclass(frozen=True)
class JourneyPlan:
    """A Journey as a PERSON writes it: the path, with no boards in it yet."""

    id: str
    titleTa: str
    theme: str
    nodes: tuple[NodeSpec, ...]


def read_plan(document: Mapping[str, Any]) -> JourneyPlan:
    """Read the authored half of a journey document, ignoring any baked payloads.

    Lenient ON PURPOSE, and only here: a freshly authored file has no payloads
    and therefore cannot yet validate as a ``Journey``, so requiring one would
    make the first bake of a new path impossible. Every field it does read is
    required, so a typo is a loud failure rather than a silently short path -
    and the OUTPUT is validated by the model, which is where the guarantee
    belongs.
    """
    nodes = document.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("a journey plan needs a non-empty 'nodes' list")
    specs: list[NodeSpec] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, Mapping):
            raise ValueError(f"node {index} is not an object")
        missing = [key for key in _SPEC_KEYS if key not in node]
        if missing:
            raise ValueError(f"node {index} is missing {missing}")
        specs.append(
            NodeSpec(
                id=str(node["id"]),
                gameId=str(node["gameId"]),
                difficulty=str(node["difficulty"]),
                unlockRule=node["unlockRule"],
            )
        )
    for key in ("id", "titleTa", "theme"):
        if key not in document:
            raise ValueError(f"a journey plan needs {key!r}")
    return JourneyPlan(
        id=str(document["id"]),
        titleTa=str(document["titleTa"]),
        theme=str(document["theme"]),
        nodes=tuple(specs),
    )


def build_journey(
    plan: JourneyPlan,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: Mapping[str, GameWordlist],
) -> Journey:
    """Turn an authored path into a validated, playable Journey.

    Every node is dealt from its Game's ORDINARY wordlist. A themed set is
    deliberately not reachable from here: a theme is a claim about a whole
    playlist that the Daily makes and announces, while a Journey's claim is its
    order, and mixing the two would give a path two different reasons to hold
    the word it holds.
    """
    specs = {spec.gameId: spec for spec in generator.games}
    prepared: dict[str, Any] = {}
    ledger: set[str] = set()
    nodes: list[JourneyNode] = []

    for node in plan.nodes:
        spec = specs.get(node.gameId)
        if spec is None:
            raise ValueError(
                f"journey {plan.id!r} node {node.id!r} names {node.gameId!r}, which "
                f"has no generator: {sorted(specs)}"
            )
        bands = {band.id for band in spec.difficulties}
        if node.difficulty not in bands:
            raise ValueError(
                f"journey {plan.id!r} node {node.id!r} asks {spec.gameId!r} for the "
                f"{node.difficulty!r} band, which it does not register: {sorted(bands)}"
            )
        if node.gameId not in prepared:
            prepared[node.gameId] = daily.builder_for(node.gameId).prepare(
                wordlists[spec.wordlist], spec
            )
        index = prepared[node.gameId]
        hint_limit = daily.hint_limit_for(app_config, node.gameId)
        seed = f"{plan.id}|{node.id}"
        frozen = frozenset(ledger)
        picks = daily.pick_words(
            wordlists[spec.wordlist].words,
            spec,
            seed,
            [node.difficulty],
            ledger,
            daily.buildability_probe(spec, seed, hint_limit, False, index, frozen),
        )
        row, difficulty = picks[0]
        item = daily.build_item(
            row, spec, seed, hint_limit, difficulty, False, index, frozen
        )
        ledger.update(daily.answer_words(item.payload))
        nodes.append(
            JourneyNode(
                id=node.id,
                gameId=item.gameId,
                packId=item.packId,
                difficulty=item.difficulty,
                unlockRule=node.unlockRule,
                payload=item.payload,
            )
        )

    return Journey(
        version=JOURNEY_VERSION,
        changelog=JOURNEY_CHANGELOG,
        id=plan.id,
        titleTa=plan.titleTa,
        theme=plan.theme,
        nodes=nodes,
    )


def answer_words(journey: Journey) -> list[str]:
    """Every word a Journey asks for, in walking order."""
    return [word for node in journey.nodes for word in daily.answer_words(node.payload)]


def wordlist_paths(plan: JourneyPlan, generator: DailyGenerator) -> Sequence[str]:
    """The ordinary wordlists this plan draws from, in a stable order."""
    specs = {spec.gameId: spec for spec in generator.games}
    return sorted(
        {specs[node.gameId].wordlist for node in plan.nodes if node.gameId in specs}
    )
