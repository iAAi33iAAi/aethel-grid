# AC-8722 — SPEC-004 Canonical Source Review

**Review date:** 2026-10-29  
**Disposition:** `HOLD` — Gate 1 remains blocked  
**Scope:** Evidence reconciliation across the user-reported CAIOS kernel/toolbox test results, the current AETHEL Grid agent-colony branch, the OpenClaw credential-guard remediation branch, and the current project master reference.

## Executive decision

The reported 95-test suite is useful as a proposed regression baseline, but it does not by itself ratify SPEC-004. The actual implementation source and test file must be tied to an immutable repository commit and independently reproduced before the 95/95 and 353/353 claims are recorded as verified.

The current repository evidence does **not** establish that `caios_kernel_module.py` is committed on `aethel-grid/main`: fetching that path from `main` returned 404, and the file is not in the changed-file set for agent-colony PR #44. The current PR #44 branch does include `ops/agent_colony/toolbox_policy.py`, but its checked-in manifest's human release-owner permissions differ from the role permissions described in the reported test summary.

The project master reference explicitly says the v0.3.1 implementation is a candidate, not the ratified source of truth; it says not to invent the missing formula and keeps promotion on HOLD pending normative review, serialization rules, independent derivation, golden vectors, cross-language conformance, adversarial tests, and a ratification record.

## 1. Evidence ledger: reported versus verified

| Claim | Evidence status | What can responsibly be concluded |
|---|---|---|
| `caios_kernel_module.py` is the canonical committed kernel source | **Not independently verified in this review** | The path was not found on `aethel-grid/main`. The exact source commit/file hash must be supplied or committed before source-based verification. |
| `test_caios_kernel_and_toolbox.py` reports 95/95 | **Reported, not reproduced** | The count is preserved as a session claim, not an independently confirmed CI result. The file is not in the current PR #44 changed-file list. |
| 72 payment tests + 85 biometric tests + 101 env-guard tests + 95 kernel/toolbox tests = 353 | **Arithmetic verified; test execution not independently verified as one suite** | The counts sum to 353, but the components come from different source/test snapshots and are not evidence of one atomic passing commit. |
| Environment guard has 101 committed tests | **Conflicts with the checked-in branch snapshot reviewed here** | The current `test_aethel_env_guard.py` contains 25 test methods; the Env Guard CI run at branch head `5589d82a57b1c8af96f5427ee1f9026358128919` passed those 25 tests. |
| The environment guard finding is closed | **Not closed operationally** | PR #23 is still a draft and unmerged. The current `.env.windows` tree removal does not erase Git history and no credential rotation was performed in this session. |
| Payment admission and scanner authentication findings are closed | **Code remediation is proposed; operational closure not established** | PR #22 and PR #21 remain separate draft/unmerged work. CI on a branch does not rotate secrets, provision production credentials, or prove production runtime behavior. |
| Gate 1 is certified by the boundary tests | **Not established** | Boundary tests check a candidate's behavior against selected expected outcomes; they cannot define or ratify the missing metric law. |

## 2. Candidate invariants reported for the kernel

The following values and comparison operators are recorded here **as claims from the supplied session summary**, not as source-verified normative law:

| Input | Reported condition | Reported consequence | Boundary case reported |
|---|---|---|---|
| Native uncertainty `u` | `u > 0.35` | `HOLD` | `u = 0.35` does not trigger this rule |
| Confidence `sigma` | `sigma < 0.40` | `HOLD` | `sigma = 0.40` does not trigger this rule |
| Drauk-Weight `DW` | `DW >= 4.90` | `BIO_VETO` | `DW = 4.90` triggers the veto |
| Soil Health Index `SH` | `SH < 0.30` | `BIO_VETO` | `SH = 0.30` does not trigger this rule |

Before these can be called canonical, the source and normative specification must define units, permitted value types, scale/normalization, measurement provenance, rounding, missing/stale sensor handling, and the physical interlock contract. Decimal values and selected boundaries alone do not establish those properties.

### Gate naming must be versioned

The reported kernel description says “Gate 2 (BIO_VETO) before Gate 3 (manifold),” while other project material describes the physical soil interlock as “Gate 1 BIO_VETO.” This could be different numbering layers, but it must be explicitly mapped in a versioned gate table. Do not silently merge the labels.

## 3. Toolbox policy: checked-in source versus reported role summary

The checked-in source reviewed on `feature/agent-colony-readonly-v0.1` is:

- [`ops/agent_colony/toolbox_policy.py`](https://github.com/iAAi33iAAi/aethel-grid/blob/feature/agent-colony-readonly-v0.1/ops/agent_colony/toolbox_policy.py) — blob SHA `ed41d4c8384cdf41d291888f8388ca3ca00b9390`.
- [`ops/agent_colony/manifest.json`](https://github.com/iAAi33iAAi/aethel-grid/blob/feature/agent-colony-readonly-v0.1/ops/agent_colony/manifest.json) — blob SHA `8f7c4c53c27931fee1e573665a3e771f8fe97807`.

The dispatcher checks a role's manifest allowlist/denylist, logs ALLOW/DENY records in an in-process list, and raises on denied calls. Its own module documentation expressly says this is an **in-process application policy boundary, not an OS sandbox**. The in-memory audit list is not a durable, tamper-evident audit ledger.

The manifest currently gives `human_release_owner` the capabilities `record_human_approval`, `record_rejection`, and `require_remediation`. It denies `delegate_approval_to_model`, `auto_merge`, `auto_deploy`, `invoke_live_payment`, `read_secret_values`, `network_request`, `write_file`, `push_branch`, and `merge_pr`. It does **not** list `execute_release_gate` or `override_hold_state` as allowed capabilities. Therefore, the reported claim that those two permissions are exclusive to the human role does not describe this checked-in manifest snapshot. Either identify the separate canonical PDF/source version that defines them, or update the implementation and tests after an approved policy decision; do not claim both designs are the same.

The current manifest denies many unsafe capabilities per toolbox. Do not treat the presence of a string in a role's deny list as an OS/process security boundary. For real secrets, network access, code writes, release promotion, payment, or biometric control, enforce the boundary at the process/service/credential layer too.

## 4. Chronicle/WAL handling: distinguish state mutation from denial audit

The reported rule “blocked commands are not logged to Chronicle WAL” needs a precise definition.

- **Required:** a blocked command must not mutate business state, call an execution primitive, or create a success/commit record.
- **Also required:** the attempted action and its denial should be retained in a separate, durable, append-only security/audit record (or a clearly distinguished denial event) with actor, policy version, request/correlation ID, timestamp policy, denial reason, and redacted resource metadata.

If “not logged” means no record of the denied attempt exists anywhere, it weakens incident response and accountability. Tests should assert both properties independently: no state transition/commit on denial, and one redacted denial-audit event. Do not solve the audit gap by writing a blocked command as if it were an executed state transition.

## 5. Gate 1 acceptance criteria — do not invent the missing metric law

The current master reference says the canonical meaning of `u_metric`, its admitted transformations, its decision partitions, and exact value representation must be ratified. Use this ordered acceptance checklist:

1. **Normative definition:** state what `u_metric` measures; identify raw inputs, units/ranges, preprocessing, transformations, missing-data behavior, and measurement provenance.
2. **Decision partition:** specify exact `PROCEED`, `REVIEW`, `BLOCK`, and `HOLD` boundaries, their operator semantics, priority, and any independent veto precedence. Give examples on either side of every boundary.
3. **Canonical arithmetic:** select the normative fixed-width integer/fixed-point model (the project references `i128/qdiv` as a candidate direction); define scale, rounding, overflow, signed division, negative values, and type rules.
4. **Invalid-value behavior:** reject booleans when a true integer is required, floats/NaN/infinities where excluded, malformed or out-of-range inputs, duplicate JSON keys, unexpected fields, and ambiguous coercions.
5. **Canonical record/bytes:** specify exact field set and order, UTF-8, escaping, timestamp grammar/time zone, number representation, hash preimage, signature domain, and version tags.
6. **Independent implementations:** have at least two implementations derive the metric and decision directly from raw inputs rather than copying each other's output or fixture decisions.
7. **Golden corpus:** publish input, expected intermediate metric, exact serialized bytes/hash, and expected decision for normative and adversarial vectors. Include equality boundaries, adjacent values, overflow, negative values, missing data, invalid types, and contradictory evidence.
8. **Cross-language parity:** run the same corpus through the reference Python implementation and the intended Rust/other runtime; verify exact decisions and byte/hash equality.
9. **Independent challenge:** red-team the specification and test harness for circular fixtures, boundary gaps/overlaps, hidden floats, coercions, stale sensor data, and fail-open exceptions.
10. **Ratification:** record the normative specification version, source commits, toolchains, dependency locks, corpus hashes, independent reviewer approvals, and explicit release decision.

A test can prove that code follows a stated formula; it cannot prove that the formula is the approved one. A fixed lookup table of known vector outcomes is not an independent derivation of the metric law.

## 6. What test success does and does not mean

A passing test suite establishes that tested assertions passed against a particular source snapshot under a particular test environment. It does not by itself establish:

- the source file is present in the designated canonical repository or at a ratified commit;
- the tests cover the entire module or independently derive expected outputs;
- the threshold values are correct as a normative specification;
- the local behavior survives concurrency, process crashes, filesystem tampering, distributed replay, or sensor spoofing;
- a physical SCADA relay has been installed, calibrated, field-tested, or proven fail-safe;
- a historical credential has been rotated/revoked;
- production payment or biometric integrations are safe or enabled.

The reported total of 353 is therefore a session scorecard, not yet a single reproducible certification result.

## 7. Operational status and next action

- [Agent-colony PR #44](https://github.com/iAAi33iAAi/aethel-grid/pull/44): draft; code and policy tests are bounded and read-only.
- [Scanner-auth PR #21](https://github.com/iAAi33iAAi/openclaw-colony/pull/21): draft; runtime key provisioning/TLS and operational checks remain distinct.
- [Signed-payment-admission PR #22](https://github.com/iAAi33iAAi/openclaw-colony/pull/22): draft; no production transfer is authorized by this review.
- [Environment-remediation PR #23](https://github.com/iAAi33iAAi/openclaw-colony/pull/23): draft; current-tree deletion, history review, and credential rotation are separate required steps.

**Next engineering task:** obtain the exact canonical `caios_kernel_module.py`, `toolbox_policy.py`, and `test_caios_kernel_and_toolbox.py` bytes at immutable source references; record their SHA-256/blob hashes; reproduce the relevant tests against those exact files; then implement and ratify Gate 1 from a normative formula rather than inferring it from boundary examples. Until those gates are passed and evidence is recorded, the release disposition stays `HOLD`.
