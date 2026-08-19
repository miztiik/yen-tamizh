# Difficulty and Scoring

**Last Updated**: 2026-08-17

The tuning vocabulary: how hard a puzzle is, how a result is scored, and how the streak and stats are derived. This page fixes the terms; the concrete numbers are config-driven ([config.md](config.md)) so tuning never touches code (Holy Law #6). Difficulty as a designed experience is Palm's altitude ([../../.github/agents/palm.agent.md](../../.github/agents/palm.agent.md)).

## Difficulty is a curve, not a slider

Difficulty is a **designed curve**, not a raw dial (Palm worldview #4). Each puzzle carries a difficulty grade on a small ramp (easy -> extreme); the ramp has a colour token per step ([design-system.md](design-system.md)). Early items are nearly impossible to lose so the first 60 seconds end in a win; new wrinkles arrive a few items apart. A [Mode](modes.md) reads difficulty to shape its Session (Daily's mix, Infinite's pickable bucket, a [Journey](journeys.md)'s rising path); a [Game](games.md) reads it to size its own puzzle. What "hard" means is per-Game and lives in that Game's generator, not here.

## Difficulty has two axes: length and familiarity

A word puzzle's difficulty is **how long the answer is AND how well the player knows it**, and the second axis carries more of the weight. Every difficulty band in `config/daily-generator.json` therefore bounds both: an ezhuthu-length range, and a **frequency stratum** ceiling.

A stratum is one quarter of the SERVED wordlist, ordered by how often the word actually occurs in Tamil text - stratum 1 is the most familiar quarter. The quarters are computed over the served set and nothing wider: a quartile taken over the whole [lexicon](lexicon.md) would describe millions of surfaces a player is never offered.

The shipped bands, and why they overlap on length rather than tiling:

| Band | Ezhuthu | Familiarity |
| --- | --- | --- |
| easy | 3-4 | top quarter only |
| medium | 4-5 | top half |
| hard | 5-6 | anything above the serving floor |

**Length alone is anti-correlated at both tails.** A long Tamil headword is usually a compound that decomposes into recognisable chunks, so it is EASIER than its tile count suggests. A short rare word is brutal: there is nothing to decompose and nothing to recognise. A length-only easy band therefore forces the generator into the shortest words, and short Tamil words are disproportionately literary - which made the old `easy` band the one most likely to serve a museum piece.

**The compound half of that claim is still an assumption.** The lexicon computes a `compound` flag and does not publish it - it had no reader, and an unread provenance column is bytes on every row (see [../architecture/lexicon/pipeline.md](../architecture/lexicon/pipeline.md)) - so the share of served 5-6 ezhuthu answers that actually decompose has never been measured against the share at 3-4. If long headwords turn out not to be mostly compounds, the hard band is mis-specified and its length bounds, not its familiarity bound, are what needs re-tuning. Measuring it costs one publish run with the column restored; nothing else here depends on the answer.

A 3-ezhuthu answer also has only six arrangements against three attempts, so it is **brute-forceable by shuffling** without the player ever recognising the word. That is a hollow win rather than an unfair one, and raising the easy floor to 4 ezhuthu is what makes an easy solve mean something. Three-ezhuthu words are still served, but only in the top familiarity quarter.

A word that no band claims - a short word outside the familiar quarters - is simply never drawn. The wordlist says what is SERVABLE; the bands say what is DRAWABLE.

## A day is dealt across the bands, and drawn stratified within one

A Daily's slots are dealt round-robin across the configured bands, so a three-item day is easy, then medium, then hard - a curve rather than three rolls of the same dice. Because the easy band admits only the most familiar quarter, **a day can never be three words nobody knows**. That is a structural guarantee, not a tuning hope.

Within a band the draw is **stratified**, not a uniform shuffle: each frequency quarter is shuffled on its own and the quarters are then interleaved, so every window of four picks holds one word from each. A uniform shuffle has the right mix on average and still hands out three unfamiliar words on a bad day - and a bad day is the day a player stops. Which quarter leads is seeded by the date, so the draw stays a pure function of the day.

The tolerance this is tuned against, in the player's own terms: one unknown word in a day of three is the GOOD day - it is the one worth telling someone about. Two is annoying. Three of three, twice in a week, ends the habit.

## What a player is asked to spell: the four serving gates

The [lexicon](lexicon.md) keeps every surface any source ever showed us. What a player is asked to PRODUCE is a far smaller set, cut by four admission gates in `config/derived-wordlists.json` ([../how-to/add-a-derived-wordlist.md](../how-to/add-a-derived-wordlist.md)). PRESENT and SERVED are different populations on purpose.

| Gate | Shipping default | Why |
| --- | --- | --- |
| `wordClasses` | headword only | The anagram asks the player to PRODUCE an exact ezhuthu sequence, so a word with unsettled orthography hands out tiles encoding one dialect's spelling and punishes every other. A proper noun is a person or a party, never a puzzle answer. |
| `minAttestations` + `minTier1Attestations` | 2 and 1 | How many word-hood authorities called it a word, and how many of those were dictionaries rather than bare listings. Two bare lists agreeing is not evidence: a spellchecker wordlist co-occurs with nearly any orthographically legal string. |
| `minFrequency` | 1 | A dictionary word that appears zero times in modern Tamil is a museum piece. This gate does the most work of the four. |
| `requireMeaning` | true | A word whose Tamil meaning is unknown can carry neither the summary line nor the paid hint rung. |

Every served word therefore has SOMETHING to say about itself, which is what lets the summary show a meaning for all three of a day's words - won or lost. It does not follow that every word can SELL one: the dearest rung is dropped when every phrase available either spells the answer out or carries a Latin-script romanisation, which is 846 of the 32,241 served rows.

Selection is an **allow-list** of word classes, never a deny-list, so a word the classifier could not place cannot reach a player by omission - and the classes a Game may ever be configured to serve are narrowed in the contract itself, so admitting a proper noun is a reviewed change rather than a one-line config edit.

Categories deliberately gate nothing. Only 2,569 of the 162,361 published headwords carry one, so admitting on a category would cut the served set from tens of thousands of rows to a few hundred. A category is a selection DIMENSION for a themed round - a separate set the Daily draws from on the days a whole themed playlist can be filled - never an admission test on the ordinary one. The same holds for `pos`, which is the same mechanism over a different column. See [../how-to/add-a-derived-wordlist.md](../how-to/add-a-derived-wordlist.md).

## Scoring is derived, not stored twice

A result is **derived from the standard [telemetry](telemetry.md) events**, never persisted as a second source of truth. From `puzzle.started`, `puzzle.attempt.submitted`, `puzzle.hint.used`, and `puzzle.completed` the scorer computes the visible stats:

- **TIME** - active elapsed time (the clock pauses when the tab is hidden, so time off the puzzle never counts).
- **INSTINCT** - first-try successes (e.g. rungs solved on the first submission).
- **RETRIES** - wrong submissions.
- **STREAK** - consecutive completed days (below).

Beating a puzzle is the floor; a **three-star** grade is the ceiling (Iisalo, via Palm) - a reason to replay a puzzle already solved, which doubles content depth without doubling content cost. Star thresholds are config knobs.

## The streak

The streak ticks **once per completed [Daily](modes.md) day** and is the shared brag. It is recomputed on read (never trusted from the payload) against a fixed **UTC** day boundary, so it is device-clock-independent and share-stable. A replay of an already-won day is practice: it never re-bumps the streak or the best time. Only Daily advances the streak; a Journey, Infinite, or Time Trial result does not.

## Hints cost the brag, not money

A hint is free and unlimited in spirit but costs the **brag**: taking one excludes the day from the best-time record and stamps "hints" on the share card. This is the honest answer to the "stuck" moment (Palm worldview #7) - the game reads a stuck player and offers a free, well-timed hint or a suggestion to replay an earlier item, and it *never* sells a power-up, ships a timer as scarcity, or gates progress behind a purchase (project non-goals, [principles.md](principles.md)). Per-Game hint visibility, count, and cost are config-driven ([config.md](config.md)); the hint shape is defined in [core-loop.md](core-loop.md).

### The anagram's ladder, and what each rung is priced at

The ladder is walked in order, so its order is its pricing. The three rungs and their shipped costs:

| Rung | Returns | Cost | Reaches |
| --- | --- | --- | --- |
| `category` | a bare one-word Tamil tag | 1 | 2,111 of 32,241 served words (6.5%) |
| `first-ezhuthu` | one position | 2 | every served word |
| `meaning` | a phrase | 3 | 31,395 of 32,241 served words (97.4%) |

The prices are set by **how much of the answer each rung hands over**, and the escalation is legible in the SHAPE of what comes back - a tag, then a letter, then a phrase - which is why the `category` rung must render one bare word and never a sentence. `hints.perGame.anagram` in `config/app-config.json` is the ceiling on how many rungs a day may bake; it is 3, so all three can reach a puzzle, and it is a ceiling rather than a promise.

A fourth rung, `length`, was **deleted**. It charged a point for the tile count already on the player's screen, which reads as the game short-changing them - and it was one of only two rungs offered, so half the ladder returned nothing. The reach column above is why the ladder is variable-length rather than always three: a rung this word cannot honestly answer is skipped and the next one moves up. See [core-loop.md](core-loop.md) for the three honesty rules that drop a rung.

### In Tamil a LONGER answer is easier, which is the reverse of English

The roadmap sketched the wordle at five ezhuthu on the English game's proportions. Simulated against a player who guesses a familiar word still consistent with every mark so far, the median solve is **15 guesses at 3 ezhuthu, 10 at 4, 7 at 5 and 5 at 6**.

The cause is the alphabet. English has 26 letters and a longer word is a larger space to search; Tamil has 247 ezhuthu, of which **203 to 217 are in play at every length**, so the alphabet is effectively constant and an extra position is an extra CONSTRAINT rather than an extra degree of freedom. The same arithmetic explains why a guess buys so little at the short end: over the shipped six-ezhuthu set the best fixed opening word measured across 400 candidates averages **1.13 marks a game**, and at five ezhuthu the same measurement gives 0.92, where a good English opener averages about two.

That is why the wordle serves exactly six ezhuthu and allows **eight** attempts, and why both numbers are config. At eight guesses the simulated solve rate is 94.5 percent on the easy band, 93.5 on medium and 85.5 on hard, against 86.2 / 84.5 / 71.5 at seven - and a hard word is one slot of every three. Narrowing the hard band to drop the rarest frequency quarter was measured as the alternative and rejected: q3 alone solves 75.0 percent within seven and q4 alone 74.0, so the quarter costs a quarter of the vocabulary and buys one point. Once the length is pinned, what decides whether a board is winnable is information per guess, not how rare the answer is.

### The wordle's ladder, and the rung it refuses

Two rungs - `category` at 1 and `meaning` at 3 - because `firstEzhuthu` cannot be honest on this board. The missing-letters board refuses it because the ezhuthu is already printed; the wordle refuses it for the opposite reason. A player can buy the same fact by spending a guess, and one guess answers five other positions at the same time, so the rung is strictly worse than the move it competes with. A rung that loses to the move the player was going to make anyway charges for nothing, which is the `length` rung in a different costume.

Scoring is the anagram's rate unchanged: 10 points an ezhuthu, so a six-ezhuthu win is 60 before hints. The same word is worth the same on both boards because the score is a property of the WORD; how few rows a win took is the wordle's own brag and it is already derivable from `puzzle.attempt.submitted`, so paying for it in the score would count it twice.

## The share moment

The end-of-session summary ([ui-shell.md](ui-shell.md)) is designed to look good in a screenshot - the score, the stars, the streak, and a small game name - because players share screenshots, not links (Player worldview #8). The share card carries no spoiler and no tracking link.

## See also

- [core-loop.md](core-loop.md) - the events the scorer reads and the hint shape.
- [lexicon.md](lexicon.md) - what a `wordClass`, an attestation and a frequency are.
- [modes.md](modes.md) - the Daily streak and per-Mode framing.
- [games.md](games.md) - where per-Game "hard" is actually defined.
- [journeys.md](journeys.md) - the rising-difficulty path and its stats row.
- [telemetry.md](telemetry.md) - the event envelope every stat is derived from.
- [config.md](config.md) - the difficulty ramp, star thresholds, and hint knobs.
- [design-system.md](design-system.md) - the difficulty colour ramp tokens.
- [../how-to/add-a-derived-wordlist.md](../how-to/add-a-derived-wordlist.md) - the serving gates as knobs.
- [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) - the ledger that proves what each gate cost.
