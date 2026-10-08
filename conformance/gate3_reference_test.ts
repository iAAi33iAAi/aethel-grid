import { canonicalPreimage, qdiv, splitTransfer } from "./gate3_reference.ts";
import { createHash } from "node:crypto";

function assert(condition: boolean, message: string): void {
  if (!condition) throw new Error(message);
}

assert(qdiv(199n, 100n) === 1n, "positive qdiv");
assert(qdiv(-199n, 100n) === -1n, "negative qdiv");

const split = splitTransfer(199n);
assert(split[0] === 1n && split[1] === 99n && split[2] === 99n, "splitTransfer");
assert(split[0] + split[1] + split[2] === 199n, "conservation");

const fields = [
  "7", "alice", "node-001", "199", "1", "99", "99",
  "a".repeat(64), "2026-10-07T120000Z", "b".repeat(64),
];
const preimage = canonicalPreimage(fields);
assert(new TextDecoder().decode(preimage).split(":").length === 10, "ten fields");

const digest = createHash("sha256").update(preimage).digest("hex");
assert(
  digest === "3f8a79aeef1649686b85015a54c78b5b5c1796bef5fbed78fa41df1878d61f35",
  "digest"
);

let rejected = false;
try {
  canonicalPreimage([...fields.slice(0, 8), "2026-10-07T12:00:00Z", fields[9]]);
} catch (error) {
  rejected = error instanceof Error && error.message === "FIELD_DELIMITER_COLLISION";
}
assert(rejected, "timestamp delimiter collision");

console.log("Gate-3 TypeScript reference: PASS");
