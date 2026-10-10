# SPEC-004 Gate 3 — Canonical Byte Profile Proposal v0.1

**Status: PROPOSAL ONLY — NOT RATIFIED — NOT A NORMATIVE SPECIFICATION**

This proposal is intended to make the outstanding Gate 3 decision reviewable. It does not change the current reference implementations, golden vectors, gate ledger, or promotion state. The project authority must explicitly accept or replace the proposed decisions before implementation is treated as canonical.

Related tracking: [AETHEL Evolution Gate 1 issue #4](https://github.com/iAAi33iAAi/aethel-grid/issues/4).

## 1. Problem being resolved

The current reference law defines the ledger preimage field order as:

\`SEQ:FROM:TO_NODE:GROSS:ARCH:COMM:NODE:STATE_HASH:TIMESTAMP:PREV_HASH\`

The current implementations join ten strings with ASCII colon (\`:\`) and reject a colon occurring inside any field. The shared example uses \`2026-10-07T120000Z\`; a conventional timestamp containing time colons (\`2026-10-07T12:00:00Z\`) is rejected. The existing code does not yet fully specify empty fields, identifier grammar, hash grammar, timestamp validity, Unicode, control characters, or common numeric bounds.

A canonical byte profile must resolve each of these deliberately. The metric formula and Gate 3's economic split arithmetic are separate matters.

## 2. Candidate profiles for the authority to choose

### Option A — Strict colon-free ASCII fields (recommended candidate)

Keep the ten-field order and colon separator. Reject unsupported field values; do not escape or rewrite them. Define one valid representation per field.

Advantages:
- Preserves the existing valid golden preimage and SHA-256 digest.
- Keeps implementations small and auditable.
- Makes field boundaries unambiguous by failing closed.
- Requires no Unicode normalization or escaping library.

Cost:
- Machine identifiers and ledger metadata in the preimage must be ASCII-safe.
- If future fields need arbitrary user text, that text must live outside this fixed-width canonical preimage or a new protocol version must be ratified.

### Option B — Escaped fields

Define an exact escaping algorithm and escape all characters that can alter parsing (including the escape marker itself), in a fixed order, before joining.

Advantages:
- Permits a wider input alphabet.

Costs:
- Existing hashes may change.
- Each language needs identical encoding, decoding, malformed-escape handling, and canonical round-trip rules.
- A vNext version and a separately generated corpus would be safer than retroactively reinterpreting old hashes.

### Option C — Length-prefixed binary/text encoding

Encode each field with an explicit byte length, a version/domain prefix, and exact UTF-8 bytes.

Advantages:
- Removes delimiter ambiguity even for arbitrary text.

Costs:
- Changes the current preimage format and hashes.
- Requires a versioned migration and a new normative binary grammar.

**Recommendation for review:** Option A is the least disruptive candidate for the current Gate 3 profile because it preserves the existing known-good vector and makes rejection behavior explicit. This is a recommendation, not an approval or a claim that Option A has been ratified.

## 3. Proposed Option A field profile

The following proposed rules deliberately preserve the existing valid example. The project authority may amend any of them before ratification.

| Position | Field | Candidate grammar |
|---:|---|---|
| 1 | \`SEQ\` | Canonical unsigned decimal integer: \`0\` or a nonzero digit followed by digits; no sign or leading zero |
| 2 | \`FROM\` | Non-empty ASCII identifier, 1–128 chars: first char alphanumeric; remaining chars alphanumeric, dot, underscore, or hyphen |
| 3 | \`TO_NODE\` | Same identifier grammar as \`FROM\` |
| 4 | \`GROSS\` | Canonical unsigned decimal integer, common numeric domain defined below |
| 5 | \`ARCH\` | Canonical unsigned decimal integer; must equal the normative split derived from \`GROSS\` |
| 6 | \`COMM\` | Canonical unsigned decimal integer; must equal the normative split derived from \`GROSS\` |
| 7 | \`NODE\` | Canonical unsigned decimal integer; must equal the normative split derived from \`GROSS\` |
| 8 | \`STATE_HASH\` | Exactly 64 lowercase hexadecimal characters |
| 9 | \`TIMESTAMP\` | Strict UTC form \`YYYY-MM-DDTHHMMSSZ\`; valid Gregorian date; hour 00–23, minute 00–59, second 00–59; no leap second, offset, fractional second, whitespace, or colon |
| 10 | \`PREV_HASH\` | Exactly 64 lowercase hexadecimal characters |

Additional candidate rules:

1. Exactly ten fields are required, in the listed order.
2. No field may be empty.
3. No field may contain colon, NUL, CR, LF, or any other ASCII control character.
4. The preimage is the ten validated ASCII fields joined with exactly nine ASCII colons, with no leading/trailing bytes, whitespace, BOM, or final newline.
5. Hash the exact preimage bytes as SHA-256; encode the digest as 64 lowercase hexadecimal characters.
6. No trimming, case folding, Unicode normalization, timestamp conversion, or other implicit repair is permitted. Reject unsupported characters rather than silently altering them.
7. Validate \`ARCH\`, \`COMM\`, and \`NODE\` against the exact normative split law before serialization, not merely their sum.
8. The common numeric domain for \`GROSS\` and the split arithmetic should be explicitly adopted as signed nonnegative i128, i.e. \`0 <= gross <= 2^127 - 1\`. Python and TypeScript/JavaScript implementations must reject values outside that domain to match Rust, even though their integer types can represent larger values.

### Compatibility check

The existing test example:

\`7:alice:node-001:199:1:99:99:<64 lowercase hex>:2026-10-07T120000Z:<64 lowercase hex>\`

satisfies the candidate field profile, and its current expected digest should remain unchanged. The colon-bearing timestamp \`2026-10-07T12:00:00Z\` must remain rejected under Option A.

## 4. Required conformance tests before canonical promotion

Every implementation (Python, Rust, TypeScript/JavaScript BigInt) must share one vector corpus and agree on both acceptance/rejection and exact bytes/digests.

### Positive cases
- Existing preimage and digest remain byte-for-byte unchanged.
- Minimum sequence \`0\` and gross \`0\`.
- Gross values around split boundaries: 0, 1, 99, 100, 101, 199, 200.
- Maximum agreed numeric input and cases near that bound.
- Valid timestamps including leap-day and year boundaries.
- Identifier characters at every allowed edge.

### Negative cases
- Field count 9 or 11.
- Empty fields, extra separators, colon in every individual field position.
- Leading/trailing whitespace, CR, LF, NUL, other control bytes, and UTF-8 BOM.
- Uppercase, short, long, non-hex, or Unicode characters inside hash fields.
- Invalid dates, invalid clock values, conventional colon-bearing ISO time, offsets, fractions, leap seconds, and trailing characters.
- Empty identifiers, identifiers over 128 characters, slash, backslash, spaces, colon, and non-ASCII.
- Numeric plus signs, negative values, leading zeros, decimal points, exponent notation, and values above the agreed i128 domain.
- Split fields that do not match \`split_transfer(gross)\`, even if their sum equals \`gross\`.
- Identical logical input represented with any alternate byte spelling.

For rejected inputs, languages must return the same stable error category or documented language-specific equivalent. They must not generate a digest for an invalid record.

## 5. Promotion constraints

This document does not close Gate 3. Before promotion:

1. Project authority explicitly approves Option A, B, or C and the numeric domain.
2. The exact candidate grammar is implemented in all three languages.
3. Positive and negative vector expectations are generated from the agreed executable reference rules.
4. Cross-language bytes and SHA-256 digests match on the same corpus.
5. Clean-checkout CI passes on one exact commit and the gate ledger cites that evidence.
6. The maintainer records the normative profile/version and migration story for any future format change.

Until those conditions are met, the Gate 3 preimage contract remains **PARTIALLY CLOSED** and \`PROMOTION = HOLD\`.
