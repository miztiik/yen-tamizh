# Games

**Last Updated**: 2026-08-21

The catalog of Game mechanics and the contract every Game honours. A **Game** (`gameId`) is the verb - the puzzle mechanic. It is one of the two orthogonal axes of a play session (the other is the [Mode](modes.md)); the content it draws from is a [Pack](#pack). The verb itself is defined once in [core-loop.md](core-loop.md); this page catalogs its six concrete forms.

## The Game contract

Every Game is a **pure mechanic**. It:

- receives a `payload` (its puzzle data) plus a `GameContext` (the bus, logger, and config it needs), and nothing more;
- renders into the `stage` slot only (never the chrome - see [ui-shell.md](ui-shell.md));
- emits the standard [telemetry](telemetry.md) events (`puzzle.started`, `puzzle.attempt.submitted`, `puzzle.hint.used`, `puzzle.completed`, `puzzle.abandoned`) - which is what "wires it up"; there is no central switch statement;
- never reads global config beyond its payload and context, and never writes storage directly (the shell owns persistence);
- round-trips its state (`getState` / `restoreState`) so a mid-puzzle reload is recoverable ([core-loop.md](core-loop.md));
- may carry an optional ordered `hints` array (`{ kind, text, cost }`).

Each Game's puzzle `payload` is a persisted surface with its own schema (`<gameId>-puzzle`) - contracts before logic, see [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md). Each Game lands with its own code row; this doc fixes the vocabulary those rows build to.

## The catalog

The `gameId` values are the locked identifiers used in code, schemas, config, and UI copy. The Tamil column holds **working names** - display titles that need a native-speaker pass before they land in `config/copy.json` (they are copy, never identifiers; see [config.md](config.md)). Tamil script here is content, not punctuation.

| `gameId` | Tamil (working name) | Mechanic | Tamil-specific note |
| --- | --- | --- | --- |
| `word-ladder` | சொல் ஏணி (add one ezhuthu) | Add exactly one ezhuthu and rearrange to reach the next valid word. | Rungs are counted in ezhuthu, not codepoints. The reachability graph is proven at build time so the browser only plays a valid ladder. |
| `anagram` | சொல் கலைப்பு | Unscramble ezhuthu tiles into the target word. | The proven starter mechanic, ported from the prior generation. |
| `missing-letters` | இடைவெளி நிரப்பு | Fill the blanked ezhuthu of a partially shown word. | A blank is a whole ezhuthu, never half a cluster. The blanks are POSITIONS in the answer's segmentation, so the payload ships no ezhuthu array of its own. |
| `wordle` | சொல் யூகி | Guess an N-ezhuthu word in N tries; per-tile present / correct / absent feedback. | "Letter" = ezhuthu; the keyboard is an ezhuthu picker (uyir + mei + uyirmei). |
| `word-search` | சொல் தேடல் | Trace hidden words in an ezhuthu grid, 8 directions. | Grid cells are ezhuthu; tracing is drag or keyboard. |
| `crossword` | சொற்கட்டம் | Fill a mini crossword from clues; entries interlock on shared ezhuthu. | Interlock is on ezhuthu identity. A build-time solver in `backend/` places the words. |

## missing-letters

A word is printed with one or more whole ezhuthu punched out of it, and a bank of ezhuthu sits below. Tap one and it drops into the next hole; tap a filled hole to take it back. The board auto-submits the moment the last hole fills, so there is no check button and nothing to read before the first move.

Three things are true of it that are not true of the anagram, and each one shapes the contract:

- **There is no Tamil keyboard, so the bank is the input method.** Its size is therefore a balance number rather than a layout preference - it is the odds a player who knows nothing still guesses right inside the allowed attempts - and it lives in `config/daily-generator.json` as `choiceCount` (Holy Law #6).
- **The generator CHOOSES the mask.** An anagram is handed the tiles it must work with; this Game gets to pick which ezhuthu to hide, so it scores every candidate mask against the served set and takes one no other served word answers. See [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) for the measured trade-off and what happens on the words where no such mask exists.
- **The first ezhuthu can never be a hint.** The board has already printed every ezhuthu it is not hiding, so that rung is either a fact on the screen or the answer itself. Its ladder is two rungs - a category, then a meaning - where the anagram's is three.

Scoring counts HOLES, not the word's length: this Game hands the player most of the answer, so a one-blank win is worth 20 against the anagram's 40 to 60 ([difficulty-and-scoring.md](difficulty-and-scoring.md)).

## wordle

A board six ezhuthu wide and eight rows tall. Compose a row, submit it, and every cell comes back marked: the right ezhuthu in the right place, the right ezhuthu somewhere else, or not in the word at all. The marks accumulate on the keyboard as well as on the board, and the answer is shown when the last row is spent.

Four things about it are Tamil-specific, and each one is a decision rather than a port of the English game:

- **A "letter" is an ezhuthu, and so is a mark.** `கா` is one cell, not two, so a guess playing `கா` where the answer holds `கோ` is ABSENT - they are different letters that happen to share a base. A marker walking code points would find the `க` in both and say "present", which is a lie the player would build three more guesses on.
- **Duplicates are marked in two passes.** Exact positions are taken first and only what is left can be marked present, so an answer holding one `க` never lights up two of them. See [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) for the worked table.
- **The keyboard is a COMPOSER, not 247 keys.** Thirty-one keys commit one ezhuthu each - twelve uyir, the aytham, and each consonant in its bare form - and a thirteen-key form row RE-SPELLS the cell just placed into any of that consonant's shapes, mei first and then the twelve uyirmei. That row IS the Tamil letter chart, which is why it needs no tutorial. Every key is coloured by the exact ezhuthu it would commit right now, so the form row is a live per-letter readout; rolling twelve forms up into one verdict on the base key has no honest answer, because `கா` being absent says nothing about `கு`.
- **Every complete row is accepted; there is no accept list.** A word check can only ever REJECT, and the best list this repo could build - the published headword class - withholds 1,395,218 classified `inflected` surfaces, which is exactly what a speaker of an agglutinative language types. Rejecting is also a favour, since it hands the row back, so accepting everything is the strictly harsher setting and the only one that can never tell a player their real word is not a word.

The answer is six ezhuthu because that was measured, not assumed - in Tamil a LONGER answer is easier, the reverse of English ([difficulty-and-scoring.md](difficulty-and-scoring.md)). Its ladder is two rungs: `firstEzhuthu` is refused because a guess buys the same fact and answers five other positions at the same time.

## word-search

An eight-by-eight grid of ezhuthu with four to six words hidden in it, and the list of those words printed beside the grid. Draw a straight line through a word - in any of the eight directions, forwards or backwards - and it is struck off the list with its meaning beside it. Every word found ends the board; nothing else does.

Four things are true of it that are not true of the other three Games:

- **A grid cell is a WHOLE ezhuthu.** This is the mechanic's central correctness property, not a nicety: a cell holding half a cluster is a cell no Tamil reader can name, and no straight line through it spells anything. The payload's contract checks every cell twice - that it is one cluster, and that the cluster is one of the 247 - because a lone vowel sign, which is what splitting a cluster leaves behind, survives segmentation as a single unit and would pass the first check alone.
- **Length is not the difficulty axis.** A longer word covers more cells and is more distinctive, so it is EASIER to spot - the inverse of what length does to a scramble or a wordle board. What makes a search harder is how many words are outstanding and how well the player knows them, so all three bands span the same 4 to 6 ezhuthu and separate on the word count (4 / 5 / 6) and the frequency quarter.
- **A wrong trace costs nothing.** Tracing is how a player LOOKS, and charging for looking would turn the one exploratory mechanic in the game into a guessing game. There is no attempt budget and no way to lose - so the payload carries no `attempts` field for nobody to read.
- **There is no hint ladder at all.** This board prints the words it is asking for, so a category, a first ezhuthu and a meaning are all facts already on the screen. The only thing a player lacks is a LOCATION, and a baked location rung would have to name one particular word - making it worthless if that word were already found, which is the same test that deleted the `length` rung and refused `firstEzhuthu` twice. The help this Game gives instead is a REVEAL priced in the word it hands over: the player forfeits that word's points and keeps every other one, so a player stuck on the last word is never trapped and never loses what they earned.

Both input methods are one mechanic. A pointer press and the keyboard's first Enter drop the same anchor; dragging and the arrow keys move the same cursor; releasing and the second Enter submit the same line. A trace is judged by what it SPELLS, so a word placed backwards is found by reading it either way, and a word the filler happened to spell a second time is found where the player traced it. A mechanic only playable by drag would fail this repo's keyboard bar (CLAUDE.md section 0a), so the two paths resolve through one definition of what is selected and cannot disagree.

## crossword

A small board of numbered squares beside a numbered list of meanings. Write a word into a square and it goes into the answer running across AND the answer running down at once; write every answer and the board is solved. There is no attempt budget - writing is how a player thinks on a crossword - and the only price is a REVEAL, which hands over one answer and forfeits exactly its points.

Four things are true of it that are not true of the four Games before it:

- **The answers are not independent of each other, and a build-time solver is what makes that safe.** Every other Game's payload is a function of one word; here each answer is constrained by every answer crossing it. The search that satisfies all of them at once runs in `backend/` at bake time, so the browser is handed a finished board and never searches for anything (Holy Law #1, Holy Law #2). The payload's contract then rebuilds the grid from the entries and reads every answer back out of it, so a placement bug fails the bake rather than shipping a board whose across and down answers contradict each other.
- **A Tamil grid can be interlocked but not fully CHECKED, and that was measured.** Pinning one position of an answer leaves a median of 103 to 556 candidate words, two positions leave 3 to 11, and three leave a median of ONE. So an American-style board where every square belongs to two answers is impossible past three by three: a 3x3 word square fills every time, a 4x4 twice in twelve, and a 5x5 never. The shipped masks are therefore British-style lattices with unchecked squares, where each answer crosses two or three others rather than all of them.
- **The clue is the lexicon's own Tamil sense, never an invention and never a translation.** This is the first Game that prints the meaning and asks for the WORD, which is the reverse of every Game before it - and that turns two harmless properties of a gloss into disqualifications. A sense containing its own headword hands the answer over; a sense carrying Latin script clues a Tamil grid in English. Both are cut from the derived set rather than clued badly here, and the payload's contract refuses a clue that spells its answer as an independent second check.
- **There is no hint ladder, for the opposite reason to the search board's.** This board already SELLS meanings - that is what a clue is - and prints one per answer, free, before the player has written anything. Every rung the shared ladder can render is therefore a fact on the screen or a fact about one of six to eight answers, whose worth depends on whether that answer is still outstanding when it is bought. The help is a per-entry reveal instead, priced in the answer it hands over.

The keyboard and the pointer are one mechanic here too. Tapping a square and arrowing to it move the same caret; tapping the square you are on and pressing Enter both turn the corner; a composer key and the arrow keys drive the same state. Landing on a square adopts the direction that square really runs, so the highlighted answer is always the answer being written. The composer is the wordle's letter chart re-used as a mechanic rather than as code - one tap on a base writes its a-form and steps along, one tap on a form re-spells the square just written - because a Game reaching into another Game is what one-schema-per-Game exists to prevent, and the two keyboards answer different questions.

Filling the cells the words do not use makes UNINTENDED words - measured at 50.4 percent of boards, mean 0.70, maximum 5 - and those are recorded rather than designed out, on the anagram's `alsoValid` precedent. A player who traces a real Tamil word and is told "wrong" concludes the game cheated; "that is a word, but not on today's list" teaches them one.

## word-ladder

A short Tamil word sits at the bottom of a column, with a bank of ezhuthu beside it. Take one letter from the bank, drop it into the word, and arrange the tiles into another real word - then do it again on the word you just made. Three to five rungs and the climb is done. The first rung is GIVEN: it is the ledge you start on, not a word you are asked for.

Five things are true of it that are not true of the five Games above, and each one is a decision this Game's build-time half already made:

- **The ladder is PROVEN before it is dealt, which is why its schema ships a row ahead of its board.** Whether a word can be climbed from is a fact about the whole served set rather than about the word, and a browser may never search for one (Holy Law #1). So the reachability graph is built in `backend/` at bake time and the player is handed a climb somebody already walked. A ladder that stopped short would not be a harder puzzle, it would be an unanswerable one.
- **A rung adds exactly one ezhuthu and rearranging is free.** Formally the multiset of the next word's ezhuthu minus the multiset of this one's is a single letter, and nothing goes the other way - so `கம்` climbs to `அகம்` and to `கரம்`, and the letters may land anywhere. Over EZHUTHU, never over code points: `கா` is one letter, and a code-point walk that read it as `க` plus a floating vowel sign would let a "climb" from `கம்` to `காம்` claim to have added nothing at all.
- **The bank is the input method, and there is one for the whole climb.** There is no Tamil keyboard here either, so a letter has to be picked from something; pooling one bank across the ladder makes choosing WHICH letter to spend now part of the puzzle rather than a fresh eight-way guess at every rung. It always holds what the climb needs and always more.
- **Tamil's short-word graph is thin, and the measurement is what shaped the Game.** 35,991 ezhuthu multisets carry 16,983 add-one edges - under half an edge a node - but the edges concentrate at the bottom: three quarters of two-ezhuthu multisets can be climbed from, two fifths of three-ezhuthu ones, and none of the seven-ezhuthu ones. That still leaves 6,218 distinct four-rung climbs, which is seventeen years of Dailies, so the curated seed list the plan allowed for was not needed. See [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) for the numbers and for how the builder picks between them.
- **The climb is chosen to protect its WEAKEST rung.** One word nobody knows ends the ladder however good the rest is, so each step is taken to leave the rarest rung of the finished climb as familiar as it can be - which more than doubles the ladders whose every rung is a word a player actually meets, and costs no ladders at all.

There is no attempt budget: this is the one board whose progress is a chain, so ending it mid-way would take away the rungs already earned. There is no hint ladder either, for the crossword's reason turned inside out - every rung the shared ladder could sell is a fact about the next word, which on a three-letter answer is most of it. The help is a per-rung reveal, priced in the rung it hands over.

### The board, and the one thing it does that no other board does (Row 16)

The ladder is drawn top rung first, so the target sits ABOVE the word the player is standing on and the given rung anchors the bottom. Every rung above the player is blank - the climb is the guess, and printing the answer one rung early would hand over the puzzle.

- **Every resolved rung carries a +ezhuthu badge: the one letter that carried it.** It is the whole verb made legible. A climber can read their own route back down the ladder and see that each step cost exactly one letter, which is a rule the board states by looking the way it does rather than by explaining itself. The badge is read off the SPENT TILE rather than off the two words, so a rung that was bought shows the letter it cost exactly like a rung that was climbed - and is bordered differently, because what it cost is a different thing from what it took.
- **The completion moment is a locally rendered result card, and it GATES the session.** It shows the four stats [journeys.md](journeys.md) named - TIME, INSTINCT, RETRIES, STREAK - a mark per rung, and a copy-to-clipboard share. The runner clears the stage the instant it is told a puzzle is complete, so the other five Games can report after a short celebration beat and this one cannot: a result on a timer is a result nobody can share. So the card waits for a tap. That is the one place this Game diverges from the other five, and the divergence IS the feature.
- **The four stats are derived from the emitted event stream and from nothing else.** Every one of them could have been a counter the Game kept and the save persisted; that is the design that was refused, because a stat stored beside the events that produced it is a second copy of a fact, free to drift, and the `save` contract would have grown a field per brag. `puzzle.started` carries the streak the player arrived with, each `puzzle.attempt.submitted` carries the `attemptIndex` that makes INSTINCT countable, and `puzzle.completed` closes the clock. STREAK is not counted here at all - the Mode reads the run StorageService already keeps and hands it down in the config slice, because a Game may not touch storage and a run named twice reads as two runs.
- **Sharing makes no network call of any kind.** The card is text and DOM built on the device. A share endpoint or a server-rendered card image was rejected: a static bundle has nothing to call, and a brag that needs a server is a brag that stops working the day the server does (Holy Law #1). It is pinned structurally in `games/word-ladder/boundary.test.ts` and again in the browser by `tests/word-ladder.spec.ts`, which asserts no request leaves the page while the card is on screen.
- **A resumed climb REPLAYS its events rather than restoring its stats.** The snapshot records which tiles were spent, which rungs were bought, and how many picks missed - but not which rung each miss fell under. So the replay spends one miss against each climbed rung, earliest first: RETRIES comes back exact and INSTINCT comes back as the floor the snapshot can prove, which is the honest direction for a brag to be wrong in. Elapsed time is the one thing a reload cannot restate, because it starts a new clock.

## Pack

A **Pack** (`packId`) is the content and language pack a Game draws from. It is a data dimension, orthogonal to the Game and the Mode. Today there is one Pack, `ta-core` (Tamil); other Packs may follow. A play session is **one Mode x one-or-more Games x a Pack**.

## Why these six

The set spans the casual word-game space with one shared atom (the ezhuthu) and one shared contract, so a second Game costs a mechanic and a schema, not a new engine. The first Game to ship is `anagram` under [Daily](modes.md) - a proven mechanic that exercises the whole shell (payload load, verb, submit, save, share) end to end. Word Ladder is the headline [Journey](journeys.md); its reachability graph, its payload schema and its board all ship, and it is the sixth and last of the set to reach a player. Authority: Palm ([../../.github/agents/palm.agent.md](../../.github/agents/palm.agent.md)) on the verb-per-Game; Fowler on the pure-mechanic contract.

## See also

- [core-loop.md](core-loop.md) - the shared verb and the ezhuthu unit.
- [modes.md](modes.md) - how a Mode frames one or more Games into a session.
- [journeys.md](journeys.md) - the curated path the Word Ladder headlines.
- [difficulty-and-scoring.md](difficulty-and-scoring.md) - per-Game difficulty and the scorer.
- [ui-shell.md](ui-shell.md) - the `stage` slot a Game renders into.
- [telemetry.md](telemetry.md) - the standard events a Game emits.
- [config.md](config.md) - per-Game tunables and display copy.
- [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) - the per-Game puzzle payload schemas.
