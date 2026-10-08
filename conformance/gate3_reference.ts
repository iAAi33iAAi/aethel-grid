// Standalone BigInt reference for SPEC-004 Gate 3.
// No Number arithmetic is used for governed values.

export function qdiv(numerator: bigint, denominator: bigint): bigint {
  if (denominator <= 0n) throw new Error("denominator must be positive");
  const quotient = numerator < 0n ? (-numerator) / denominator : numerator / denominator;
  return numerator < 0n ? -quotient : quotient;
}

export function splitTransfer(gross: bigint): [bigint, bigint, bigint] {
  if (gross < 0n) throw new Error("gross must be non-negative");
  const arch = qdiv(gross, 100n);
  const remainder = gross - arch;
  const comm = qdiv(remainder, 2n);
  const node = remainder - comm;
  if (arch + comm + node !== gross) throw new Error("CONSERVATION_FAILURE");
  return [arch, comm, node];
}

export function canonicalPreimage(fields: string[]): Uint8Array {
  if (fields.length !== 10) throw new Error("TEN_FIELDS_REQUIRED");
  if (fields.some((field) => field.includes(":"))) {
    throw new Error("FIELD_DELIMITER_COLLISION");
  }
  return new TextEncoder().encode(fields.join(":"));
}
