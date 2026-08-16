# Lexicon sources (raw, not committed)

**Last Updated**: 2026-08-16

This directory holds the raw dictionaries, word lists and frequency tables the
`wordsmith` pipeline streams. The bytes are **gitignored** - roughly 450 MB of
third-party files - and only two things are committed: the byte-exact fixture
slices under [`../../fixtures/lexicon/`](../../fixtures/lexicon/) and, later, the
published lexicon artifacts.

This file is the **acquisition ledger**. It records, for every source in the plan's
inventory, what the source is, the `role` it is allowed to play, where its bytes
came from, where they land, how many bytes there are and their sha256. A test
parses the ledger table below, so the numbers in it cannot go stale silently.

## Layout

One directory per source id. The nine frequency sources and the two authorities
that the corpus layer already registered keep their existing
[`../../corpus/`](../../corpus/) paths - the wordsmith plan moves the registry,
not the files - so the ledger's `path` column is the single place that says where
a source lives:

```
datasets/lexicon/sources/<source-id>/source.<ext>     new to this plan
datasets/corpus/<source-id>/source.<ext>              already registered in config/corpus-sources.json
```

## Roles

Every source carries exactly one `role`, and the role bounds what the source is
allowed to assert:

| role | May assert | Sources |
| --- | --- | --- |
| `authority` | that a surface IS a word (a headword), plus whatever else it carries | A1-A8 |
| `formEvidence` | only that a surface is NOT a headword - an inflected form | B1, B2 |
| `category` | semantic metadata; never word-hood | C1 |
| `frequency` | counts; never word-hood | D1-D9, E1 |
| `authored` | that a `llm_enrich` pass wrote a value; no source has this role yet | - |

## Licence

There is no licence gate on this directory, and that is a deliberate ruling, not
an oversight. Tamil words, their meanings and their synonyms are public-domain
facts about a language; a particular dictionary's edited prose is not. The
pipeline extracts the FACT - headword, part of speech, synonym set, category -
into the store, and never republishes a source's definition sentence verbatim.
A source whose terms are restrictive is simply superseded by the next authority
rather than argued with.

## The ledger

`bytes`, `records` and `sha256` describe the file at `path` exactly as acquired -
on 2026-08-14 for A1-A7 and B1 through E1, on 2026-08-15 for A8, and on
2026-08-16 for A9. `records` counts physical lines for the line-based formats
(so D1's count includes its `word,frequency` header line, and A8's includes its
`page_title` one), root-array elements for the JSON formats, and MAIN-NAMESPACE
pages for the MediaWiki export - which is what its reader treats as a record,
and is 410,074 of the export's 415,705 pages.

A8 and A9 are the two sources whose origin is an ARCHIVE rather than the file
itself, so their rows describe the decompressed bytes and each archive's own
digest is recorded in its section below
([A8](#a8---acquired-from-a-gzip-archive),
[A9](#a9---the-wiktionary-content-itself)).

| # | id | role | origin | path | bytes | records | sha256 | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | master-dictionary | authority | yen-tamizh_OLD/src/dictionary/master_dictionary.json | datasets/corpus/master-dictionary/source.json | 19128594 | 104421 | `385347a37dc315ae78e2df714d28f9da99420bf79570f4bca28c8d3c90756cc9` | acquired |
| A2 | en-ta-dictionary | authority | yen-tamizh_OLD/src/dictionary/raw/t1.json | datasets/lexicon/sources/en-ta-dictionary/source.json | 14884252 | 56856 | `de9952d65e4c03955d70bd36cc844da14b4c48749a11b3146d011b6d5e8452c1` | acquired |
| A3 | spellcheck-wordlist | authority | yen-tamizh_OLD/src/dictionary/intermediate/ta_words_v1.json | datasets/lexicon/sources/spellcheck-wordlist/source.json | 15602428 | 355275 | `050d49af576aae6c4305fd31334b404b28ecea52d3de1ff35cd85539cce578f1` | acquired |
| A4 | huggingface-wordlist | authority | yen-tamizh_OLD/src/dictionary/intermediate/ta_words_huggingface.json | datasets/lexicon/sources/huggingface-wordlist/source.json | 1010186 | 26485 | `c5c06d47a53b98a423b557e147ba02c0cdfc433759422dae7234decbe6720d09` | acquired |
| A5 | old-wordlist | authority | yen-tamizh_OLD/src/dictionary/raw/t2.json | datasets/corpus/old-wordlist/source.json | 1712398 | 36082 | `defb1b04013299925dd0bb1086891e6ef64b1dbc672bc9208233777ed3de0fda` | acquired |
| A6 | madras-lexicon | authority | https://dsal.uchicago.edu/dictionaries/tamil-lex/ | - | - | - | - | NOT ACQUIRED |
| A7 | wiktextract-ta | authority | https://kaikki.org/dictionary/Tamil/kaikki.org-dictionary-Tamil.jsonl | datasets/lexicon/sources/wiktextract-ta/source.jsonl | 86701341 | 13773 | `56c3063941fe4fe8004efbd51e6a57173b25f5d86c68fff648e27be5a15fc723` | acquired |
| A8 | ta-wiktionary-titles | authority | https://dumps.wikimedia.org/tawiktionary/20260801/tawiktionary-20260801-all-titles-in-ns0.gz | datasets/lexicon/sources/ta-wiktionary-titles/source.txt | 7745492 | 410075 | `7b4954ccad02227771354192a88bbae82939009068067b029abd073e29321cf0` | acquired |
| A9 | ta-wiktionary-content | authority | https://dumps.wikimedia.org/tawiktionary/20260801/tawiktionary-20260801-pages-articles.xml.bz2 | datasets/lexicon/sources/ta-wiktionary-content/source.xml | 647116289 | 410074 | `a33493a73bcb3d03302b8501814d80f16344d0e3cf651f41cce7bf323cf6e4d5` | acquired |
| B1 | inflected-verbs-bulk | formEvidence | yen-tamizh_OLD/src/dictionary/raw/Simple-verbs-01022021.txt | datasets/lexicon/sources/inflected-verbs-bulk/source.txt | 69572318 | 1461494 | `3baf32b9662c248b81273be0446c4f8fbfcb812c0ea6675ee47485293a9fb3b5` | acquired |
| B2 | inflected-verbs-clean | formEvidence | yen-tamizh_OLD/src/dictionary/intermediate/verbs.txt | datasets/lexicon/sources/inflected-verbs-clean/source.txt | 727814 | 19249 | `0e1913e15f1ebc7413b50f8b738a933ab7f6ecd48c3db09e9a6f4ef107226d1e` | acquired |
| C1 | themed-vocabulary | category | yen-tamizh_OLD/src/dictionary/intermediate/ta_vocabulary_clean.json | datasets/lexicon/sources/themed-vocabulary/source.json | 144240 | 1290 | `91a78edadca357690975066c6d00815060f79e6a679f07e9a63cd8758f26ed6c` | acquired |
| D1 | tamil-words-frequency | frequency | yen-tamizh_OLD/src/dictionary/raw/tamil-words-frequency.csv | datasets/corpus/tamil-words-frequency/source.csv | 192867247 | 4591655 | `b2be87bb2c503da602e7d5656acc0efc396592d8c422f40db269ced4134b5978` | acquired |
| D2 | ta-dedup | frequency | yen-tamizh_OLD/words_and_frequency/words_and_frequency/frequency+words_in_ta_dedup.txt | datasets/corpus/ta-dedup/source.csv | 20962605 | 553988 | `dac09925388c0339d26c9e46532892a7812611d55bad9db2bc9b6ab90e12d90e` | acquired |
| D3 | wiki | frequency | yen-tamizh_OLD/words_and_frequency/words_and_frequency/frequency+words_in_wiki.txt | datasets/corpus/wiki/source.csv | 9673403 | 273953 | `98e57ad7e12917380bf31482f4230efb46ec81ea131357a209fbee1e9e16f2fb` | acquired |
| D4 | dinamalar | frequency | yen-tamizh_OLD/words_and_frequency/words_and_frequency/frequency+words_in_Dinamalar_dataset_2009_2019.csv | datasets/corpus/dinamalar/source.csv | 6247571 | 170845 | `a4ff12e33979b45aacb64f5a8be9c963e25c28cfba5dca6db0c77f3a682fcebf` | acquired |
| D5 | tamilmurasu | frequency | yen-tamizh_OLD/words_and_frequency/words_and_frequency/frequency+words_in_Tamilmurasu_dataset_06_Jan_2011_06_Jan_2020.csv | datasets/corpus/tamilmurasu/source.csv | 501112 | 15663 | `14f9c5c04c4d8b860dfe51946c32633147f66bbff7c47b62d9d1b87cd2f2a1df` | acquired |
| D6 | sirukathaigal | frequency | yen-tamizh_OLD/words_and_frequency/words_and_frequency/frequency+words_in_sirukathaigal.com.html | datasets/corpus/sirukathaigal/source.csv | 9083366 | 255533 | `f32b4c4db4f8acd58e6d97530af0c74c6e7be40c7f59feeb7c51da8533e49537` | acquired |
| D7 | solvanam | frequency | yen-tamizh_OLD/words_and_frequency/words_and_frequency/frequency+words_in_solvanam.html | datasets/corpus/solvanam/source.csv | 4345491 | 127738 | `cae466298d1740545210a22297997414c983883c38a20a64ce5ae536f04dcd23` | acquired |
| D8 | gurunithya | frequency | yen-tamizh_OLD/words_and_frequency/words_and_frequency/frequency+words_in_gurunithya.wordpress.com.html | datasets/corpus/gurunithya/source.csv | 95111 | 3062 | `9c94c91b19bf3ff6d41f31d43a884df395241fb8bc10646897381634291656b6` | acquired |
| D9 | opensubtitles-ta | frequency | https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/ta/ta_full.txt | datasets/corpus/opensubtitles-ta/source.txt | 562582 | 19371 | `62105bea7448f5243dc4bfbed5311dd607f08af21fa026c776d2a373c10a24f8` | acquired |
| E1 | azhiyasudargal | frequency | yen-tamizh_OLD/words_and_frequency/words_and_frequency/frequency+words_in_azhiyasudargal.html | datasets/corpus/azhiyasudargal/source.csv | 46839 | 2678 | `7d90827fa2671be46ab27490e5b136f0cec69a9f707ecfe36dc7842cc33b2014` | acquired (disabled) |

Eleven of these sha256 values - A1, A5 and D1-D9 - are not new. The corpus ingest
recorded them in the `provenance` block of
[`../../wordlists/master/words_ranked.json`](../../wordlists/master/words_ranked.json)
in August 2026, and every one of them matches the bytes re-acquired today,
including D9, which was re-downloaded from its URL rather than copied. A test
asserts that agreement, which is what makes the committed master wordlist
provably a function of these exact files.

The origins recorded above are the corrected ones. The nine frequency sources
live under a **doubled** directory in the predecessor repository -
`words_and_frequency/words_and_frequency/` - which the `origin` values already in
`config/corpus-sources.json` omit. When row 5 ports those entries it should carry
the corrected origins, not the ones on file.

### A6 - NOT ACQUIRED

The University of Madras Tamil Lexicon (DSAL) has no obtainable bulk artifact.
The published site is a search interface over a server-side database; it offers
an "About" PDF and front matter, and nothing else. Probed on 2026-08-14:

| URL tried | Result |
| --- | --- |
| `https://dsal.uchicago.edu/dictionaries/tamil-lex/` | 200 `text/html` - the search page. Its HTML carries 7 links, none to data |
| `https://dsal.uchicago.edu/dictionaries/tamil-lex/tamil-lex.zip` | 404 |
| `https://dsal.uchicago.edu/dictionaries/tamil-lex/tamil-lex.xml` | 404 |
| `https://dsal.uchicago.edu/dictionaries/tamil-lex/tamil-lex.txt` | 404 |
| `https://dsal.uchicago.edu/dictionaries/tamil-lex/downloads/` | 404 |
| `https://dsal.uchicago.edu/dictionaries/tamil-lex/data/` | 404 |
| `https://dsal.uchicago.edu/dictionaries/downloads.html` | 404 |
| `https://dsal.uchicago.edu/dictionaries/data/` | 404 |
| `https://dsal.uchicago.edu/dictionaries/about.html` | 200 `text/html` - no data link |
| `https://dsal.uchicago.edu/dictionaries/dictionaries.html` | 200 `text/html` - no data link |

No substitute was put in its place. A6 is the plan's only source of
`definitionEn` at scale, so its absence is a real gap and is reported as one
rather than papered over: without it, `llm_enrich` authors Tamil meanings from
A2's glosses, C1's pairs and A7's senses alone. The entry stays in the ledger so
a later reader knows it was sought, where, and what happened.

### A8 - acquired from a gzip archive

A8 exists because A7 is not what its name suggests. `wiktextract-ta` is the
ENGLISH Wiktionary's Tamil subset, which is what kaikki.org publishes: kaikki
exports roughly twenty Wiktionary editions and Tamil is not one of them, so the
Tamil Wiktionary itself had never been read. At 13,773 entries A7 is the thinner
half of Wiktionary's Tamil coverage; the Tamil edition's main namespace holds
410,074 pages.

Three things about acquiring it are worth writing down, because each one costs an
hour to rediscover.

**Wikimedia refuses the default Python User-Agent.** A plain
`urllib.request.urlopen` on any `dumps.wikimedia.org` URL returns **HTTP 403
Forbidden**. A descriptive User-Agent is required and is enough:

```
User-Agent: yen-tamizh-lexicon/1.0 (build-time corpus tooling)
```

**The URL is a DATED one, not `latest`.** `latest` is a moving target: the same
path serves different bytes every month, so a recorded sha256 goes stale without
anything in the repository changing. Wikimedia also publishes dated runs, and on
2026-08-15 ten of them resolved - `20251201` through `20260801` - which is a
retention window of roughly nine months. The `20260801` run and `latest` returned
byte-identical files (1,888,498 bytes, the same digest, both `Last-Modified: Tue,
04 Aug 2026 12:30:54 GMT`), so pinning the dated URL costs nothing and buys a
reproducible fetch. The dump run is NAMED `20260801` and was PRODUCED on
2026-08-04; the ledger's origin is the name, this paragraph is the date.

**The row describes the decompressed file.** The origin is a `.gz`; the bytes at
`path` are what `gzip` yields from it. That is not a convenience - a fixture must
be a byte-exact contiguous slice of the file the reader reads, and a truncated
gzip member is not a readable gzip file at all, so a `.gz` on disk could not have
an honest 1x fixture. Both digests are on record, so the chain from the published
archive to the file the pipeline reads is verifiable end to end:

| artifact | bytes | sha256 |
| --- | --- | --- |
| the published archive | 1888498 | `a7f97c8122461f70937753e0039aa727f0aacfca3b6157f610397c9aa361a09b` |
| decompressed, at `path` | 7745492 | `7b4954ccad02227771354192a88bbae82939009068067b029abd073e29321cf0` |

The file is LF-only (zero carriage returns), ends with a newline, holds no blank
line, and its first line is the header `page_title`, which is why the registry
entry sets `hasHeader`.

**It is a TIER-2, enumerative authority.** The role is `authority` because no
other role in the closed vocabulary is true of it - it asserts no negative, no
theme and no count - and because three sources already registered as authorities
(A3, A4, A5) are bare word lists too, two of them machine-generated, which this
one is not: a page in the main namespace exists because a person wrote a
dictionary entry. But that editorial act is not IN the bytes. The dump carries no
gloss, no definition, no part of speech, no synonym and no category, so it can
never satisfy the entry test - a `headword` fact plus a describing fact from the
SAME source - and can never make a surface a headword by itself. Provenance
describes the bytes on hand, not what is believed about how they came to exist,
so the ruling is tier 2 with the editorial provenance recorded beside it.

What it contributes, measured against the store on 2026-08-15: of the 98,100
single-token, wholly Tamil titles of 25 ezhuthu or fewer, 12,383 are surfaces the
lexicon had never seen and 2,722 are surfaces it had seen but no authority had
vouched for. 83,701 fall in the 1-7 ezhuthu band the games draw from.

### A9 - the Wiktionary CONTENT itself

A8 acquired the Tamil Wiktionary's TITLES. A9 acquires what the titles are
titles OF, and it is a different source in every way that matters: the same
410,074 main-namespace pages, but carrying the Tamil sense, the synonym set, the
part of speech and the English gloss that a title list has none of.

The two are not even the same STRINGS. A8's dump writes a page title's spaces as
underscores and A9's writes them as spaces, so 187,234 multi-word titles are
staged twice, once under each spelling. Neither is wrong - each is what its own
publisher shipped - and neither is a Tamil word, so both are classified the same
way.

The same two acquisition rules as A8 apply and are not restated: the descriptive
User-Agent, and the DATED URL rather than `latest`. On 2026-08-16 the `20260801`
run and `latest` returned byte-identical files - 39,766,454 bytes, the same
digest - so the dated URL is pinned and the moving one is not.

The archive is bzip2 rather than gzip, and the same rule sends the decompressed
file to `path`: a truncated bzip2 stream is not a readable bzip2 file, so an
archive on disk could never have an honest `1x` fixture. Both digests are on
record.

| artifact | bytes | sha256 |
| --- | --- | --- |
| the published archive | 39766454 | `6aaad55e0d3baa9448ff326561eb973b23f4e8d299b95fcf18beb8a48017b180` |
| decompressed, at `path` | 647116289 | `a33493a73bcb3d03302b8501814d80f16344d0e3cf651f41cce7bf323cf6e4d5` |

At 647 MB it is by a factor of three the largest file the pipeline reads, which
is why its reader is written against expat's handler interface rather than an
element tree: peak memory tracks the largest RECORD, not the file, and not even
the largest PAGE. The three biggest pages in the first two thousand are a
template listing and a village-pump archive at 226 KB, 346 KB and 1,035 KB,
against a largest ARTICLE of 23 KB - so declining to accumulate the text of a
page outside the declared namespace is worth a factor of 45.

**It is a TIER-1, lexicographic authority, and A8 is not.** The two rulings are
the same rule applied to different bytes. A8 is tier 2 because the editorial act
is not in the bytes it ships; A9 ships exactly that act - somebody decided the
string is a word and then said what it means. Measured over the whole dump:
92,731 of the 98,107 wholly Tamil single-token titles carry a Tamil sense,
94,929 carry a part of speech and 46,180 carry a synonym set. The claim is
enforced ROW BY ROW rather than on average: the reader emits a `headword` fact
only for a page that carries at least one of those facts, so 145,054 of the
410,074 pages - stubs, redirects and appendix listings - are observed and
attested by nobody, and none of those surfaces is lost, because A8 already
enumerates every one of them.

Wikitext has conventions rather than a grammar, so the reader COUNTS what it
could not read instead of dropping it. Over the whole dump it skipped 40,946
lines inside blocks it was harvesting, and every run prints that number and the
pages-without-facts one beside the seven-field tally.

### E1 - acquired, disabled The extraction that produced it stripped
vowel signs and pulli, so its tokens are bare consonant skeletons - valid Tamil
letters that are not Tamil words, and some of which cannot begin a Tamil word at
all. A known-bad source is kept and explained rather than deleted, so that nobody
re-adds it in a year having forgotten why it went. Flip it on only if a corrected
extraction ever replaces the bytes, which would change its sha256.

## What was deliberately NOT acquired

The predecessor repository holds a great deal more than the ledger above. Group F
of the plan's inventory enumerates it with a reason each, so that a later reader
does not have to re-litigate whether something was missed. In short:

| Not acquired | Why |
| --- | --- |
| `src/dictionary/raw/t1_bkpup.json` | A byte-identical backup of A2 |
| `src/dictionary/intermediate/tamil_dict_01..12.json` | Chunked copies of A2; A2 is the whole file |
| `src/dictionary/intermediate/tamil_words_sorted_*.json`, `tamil_word_list_*.json`, `intermediate/archive/` (410 files, 183 MB) | Intermediate output of the legacy pipeline this plan replaces. Their input is D1 |
| `src/dictionary/intermediate/processing_log.json` | A log of a legacy run, not data |
| `words_and_frequency.tar.bz2` | The same 8 files as the extracted directory, compressed. No unique data |
| `data/puzzles/index.json`, `data/puzzles/2026/*.json` | The old game's baked puzzle bank. Superseded output, not a word source |
| `data/wordlists/game_words_2..6_letter.json` | Already present as `datasets/wordlists/by-length/` |
| `src/utils/`, `scripts/` | Legacy pipeline code this plan replaces |
| `frontend/wireframe_screens/` | Design reference, not data |

### Candidates evaluated for a SECOND meaning source, 2026-08-16

The Tamil Wiktionary content dump gives most headwords a meaning, but one
source asserting a meaning is a claim rather than a confidence. Five candidates
were evaluated for corroboration; nothing below was acquired, and each verdict
is a live probe rather than a recollection.

The bar every candidate has to clear first is REPRODUCIBILITY. This registry
pins every source by `sha256` and `bytes`, and a zero-network drift check reads
those. A producer that answers differently on each call cannot sit inside a
stage whose Oracle is byte-identity - the same ruling that made the model an
input FILE rather than a stage. A live service is admissible only in the shape
that ruling allows: a human runs it once, the output is committed, and a digest
is recorded.

| Candidate | Bulk artifact | Reproducible | What it would add | Verdict |
| --- | --- | --- | --- | --- |
| IndoWordNet, English-linked | `cfiltnlp/IWN-En` `data/english-hindi-tamil-linked.tsv`, 13,711,270 B | yes, if the URL pins a COMMIT rather than a branch | Tamil SYNSETS and Tamil glosses, sense-disambiguated by a Princeton WordNet synset id | **RECOMMENDED** |
| `ta.wikipedia` titles | `tawiki-20260801-all-titles-in-ns0.gz`, 2,021,059 B | yes, dated URL resolves | proper-noun evidence, which the serving gate needs to exclude reliably | accept as a cheap follow-on |
| Wikidata lexemes | `latest-lexemes.json.bz2`, 442,289,093 B | yes | **904** Tamil lexical entries, counted live at the SPARQL endpoint | reject on value against cost |
| Google Translate | none | no | a gloss per word | reject - see below |
| agarathi.com | none; `/download` is 404 and the site is a query interface | no | unknown | reject - scrape-only |

**IndoWordNet is the recommendation, and the reason is the shape of the data
rather than its size.** Its Tamil column is a SYNSET - a set of Tamil words that
share one sense - keyed to an English WordNet synset with an English gloss
beside it. That is precisely the field the lexicon is weakest in: the synonym
column it has today comes from reading a bilingual dictionary sideways, which
groups by an ENGLISH headword and therefore mixes senses. A synset does not.
Being linked to English WordNet also makes it independently checkable against
the English glosses the store already holds, which is what makes it a
CORROBORATING source rather than a second opinion nobody can adjudicate.

Two things a follow-up row must settle before registering it. Its licence is
**CC BY-NC-SA 4.0** (both CFILT repositories state it; GitHub's own detector
reports `NOASSERTION` because the file is not a verbatim SPDX text). The
project's licence ruling for this directory - facts about a language are
extracted, a source's edited prose is never republished - covers the synset
membership and the part of speech; the Tamil gloss SENTENCE is prose and stays
store-only evidence like every other source's. And the artifact must be pinned
by commit sha, not by `master`, for the same reason A8 and A9 pin a dated dump
rather than `latest`.

**What was rejected, and why, in the candidates' own terms:**

- **Google Translate has no bulk artifact at all.** The only programmatic access
  is the Cloud Translation REST API, which needs a billing-enabled key - a
  dependency this repository will not take on - and whose terms do not permit
  redistributing its output as a dictionary. The committed-file shape would
  make the REPRODUCIBILITY problem go away; it does not make the terms problem
  go away, and the terms are the blocker. Machine translation is also the wrong
  instrument for the job: it produces a translation of a string, where what the
  lexicon needs is a lexicographer's claim that a string is a word with a sense.
  Nothing was scraped and no scraper was written.
- **The Open Multilingual Wordnet does not carry Tamil.** Its v2.0 release
  publishes forty-one per-language archives and none of them is Tamil, so the
  `wn` package route yields nothing. The AU-KBC Tamil WordNet host no longer
  resolves in DNS, and the one open-source "Tamil WordNet" repository on GitHub
  contains a licence file and a README and no data.
- **Wikidata lexemes are bulk and reproducible and nearly empty for Tamil.** 904
  lexical entries is four hundred thousand times less than the wiki dump for a
  file four hundred times larger.
- **agarathi.com publishes no bulk artifact.** Its `robots.txt` disallows only
  its asset directories, so a crawl would not be forbidden by the file, but a
  crawl is not a source: there would be no digest to record, no way to re-obtain
  the same bytes, and no way for a reviewer to check what was taken.

## Fixtures

Every acquired source has two committed fixtures under
[`../../fixtures/lexicon/`](../../fixtures/lexicon/):

```
datasets/fixtures/lexicon/<source-id>.1x.<ext>
datasets/fixtures/lexicon/<source-id>.10x.<ext>
```

42 files, 6,759,161 bytes in total. Three rules govern them:

1. **A fixture keeps its source's extension.** A byte-exact slice of a CSV is a
   CSV and a slice of a JSON array is JSON, so each reader is exercised against
   the format it will really meet.
2. **A fixture is `raw[:k] + raw[len(raw) - m:]`** - a head slice of the source,
   plus, for the framed formats, the source's own closing bytes. For the
   line-based formats `m` is zero and the fixture is a pure byte prefix. For a
   JSON array the first N elements are copied unchanged and the source's own
   `]` and `}` are appended, and for the MediaWiki export the source's own
   `</mediawiki>` is, so the fixture parses while every record byte is the
   source's. Nothing is normalized, hand-edited or cherry-picked.
3. **The 10x fixture holds exactly ten times the records of the 1x fixture**, so
   the reader memory predicate has both of its inputs. N is 2,000 records at 10x,
   reduced where 2,000 records would exceed a one-mebibyte fixture (A7, whose
   records are 6 KB each) or where the source is smaller (C1 has 1,290 rows).
   For a source with a header line the count is of physical LINES, header
   included, which is what keeps the ten-times ratio exact (A8: 200 and 2,000).
   A9 counts what its reader counts - MAIN-NAMESPACE pages, 50 and 500 - so its
   slices run to 200 and 690 physical pages. Counting raw pages instead would
   have put the export's largest page, a 1 MB village-pump archive, in the 10x
   and not the 1x, and the memory predicate would then have been measuring a
   discussion page.

Because a fixture is a head slice it is not a representative SAMPLE. Never infer
a distribution from one - the part-of-speech census in this row's pull request was
counted over the whole of every source, not over a fixture.

## Repopulating

Fetch each `origin` back to its `path`. Sources whose origin is a
`yen-tamizh_OLD/...` path come from the predecessor repository; sources whose
origin is a URL can be fetched directly. A8 and A9 need two extra steps and are
the only ones that do: their `dumps.wikimedia.org` URLs answer 403 without a
descriptive User-Agent, and their origins are archives - gzip for A8, bzip2 for
A9 - so decompress each into `path` rather than saving the archive there. Then
confirm the bytes:

```
python -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('<path>').read_bytes()).hexdigest())"
```

A sha256 that disagrees with the ledger means the upstream file changed. Record
the new value and say why in the same commit; do not overwrite a recorded hash
silently, because every downstream artifact's provenance points at the old one.

## See also

- [`../../fixtures/lexicon/`](../../fixtures/lexicon/) - the committed slices.
- [`../../corpus/README.md`](../../corpus/README.md) - the corpus layer's raw sources, which this ledger also covers.
- [`../../../TODO/20260814-wordsmith-lexicon-pipeline-plan.md`](../../../TODO/20260814-wordsmith-lexicon-pipeline-plan.md) - the plan, whose section 0 holds the full source inventory.
- [`../../README.md`](../../README.md) - what `datasets/` is for.
