/**
 * Tamil ezhuthu (grapheme-cluster) segmentation + classification.
 *
 * An ezhuthu is the atomic written unit of Tamil: an independent vowel (uyir), a
 * pure consonant (mei = consonant + pulli), a consonant+vowel (uyirmei), or the
 * aytham. `segment` groups a string's Unicode code points into ezhuthu without
 * altering them, so `segment(w).join("") === w` for every input (non-Tamil
 * characters pass through as their own units).
 *
 * The walk is a deterministic code-point scan, not `Intl.Segmenter`, so this TS
 * twin and the Python twin in `backend/yen_tamizh_backend/ezhuthu/` are provably
 * identical regardless of the host ICU version. The shared golden corpus
 * `datasets/fixtures/ezhuthu_golden.jsonl` proves the parity (Row 6).
 */

export type EzhuthuKind = "uyir" | "mei" | "uyirmei" | "aytham" | "other";

const AYTHAM = 0x0b83;
const PULLI = 0x0bcd;

/**
 * Tamil combining marks that attach to the preceding base character: U+0B82
 * anusvara; U+0BBE..U+0BCD vowel signs (matras) and the pulli/virama; U+0BD7 au
 * length mark (the second half of the decomposed au matra and au vowel).
 */
function isCombining(cp: number): boolean {
  return cp === 0x0b82 || (cp >= 0x0bbe && cp <= 0x0bcd) || cp === 0x0bd7;
}

function isUyir(cp: number): boolean {
  return cp >= 0x0b85 && cp <= 0x0b94; // independent vowels a .. au
}

function isConsonant(cp: number): boolean {
  return cp >= 0x0b95 && cp <= 0x0bb9; // mei letters ka .. ha (incl. Grantha)
}

function isVowelSign(cp: number): boolean {
  return (cp >= 0x0bbe && cp <= 0x0bcc) || cp === 0x0bd7;
}

/** Split `word` into ezhuthu (grapheme clusters), code-point preserving. */
export function segment(word: string): string[] {
  const clusters: string[] = [];
  let current = "";
  for (const ch of word) {
    const cp = ch.codePointAt(0) ?? 0;
    if (current !== "" && isCombining(cp)) {
      current += ch;
    } else {
      if (current !== "") clusters.push(current);
      current = ch;
    }
  }
  if (current !== "") clusters.push(current);
  return clusters;
}

/** Classify one ezhuthu (as produced by `segment`). */
export function classify(ezhuthu: string): EzhuthuKind {
  if (ezhuthu === "") return "other";
  const base = ezhuthu.codePointAt(0) ?? 0;
  if (base === AYTHAM) return "aytham";
  if (isUyir(base)) return "uyir";
  if (isConsonant(base)) {
    let hasVowelSign = false;
    let hasPulli = false;
    for (const ch of ezhuthu) {
      const cp = ch.codePointAt(0) ?? 0;
      if (isVowelSign(cp)) hasVowelSign = true;
      if (cp === PULLI) hasPulli = true;
    }
    if (hasPulli && !hasVowelSign) return "mei";
    return "uyirmei";
  }
  return "other";
}
