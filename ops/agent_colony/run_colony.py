#!/usr/bin/env python3
"""Read-only deterministic AETHEL agent-colony runner; inspected repo code is never executed."""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from toolbox_policy import ToolboxDispatcher

SEVERITY = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
REQUIRED_DENY = {"write_file", "push_branch", "merge_pr", "read_secret_values", "network_request"}
SENSITIVE_NAMES = {".env", ".env.local", ".env.production", ".env.staging", ".env.windows", ".env.test"}
IGNORED_DIRS = {".git", "node_modules", ".venv", "venv", "target", "dist", "__pycache__"}


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError(f"Expected JSON object: {path}")
    return value


def make_finding(agent, severity, title, path, recommendation, details=""):
    key = hashlib.sha256(f"{agent}|{title}|{path}".encode()).hexdigest()[:12]
    return {"id": f"AC-{key}", "agent_id": agent, "severity": severity, "title": title,
            "evidence_path": path, "recommendation": recommendation, "status": "open", "details": details}



def validate_finding_contract(findings, manifest):
    """Return schema errors for the complete deterministic finding set."""
    contract = manifest.get("report_contract", {})
    required = contract.get("required_finding_fields", [])
    allowed_severity = set(contract.get("severity_values", []))
    allowed_status = set(contract.get("status_values", []))
    known_agents = {a.get("id") for a in manifest.get("agents", []) if isinstance(a, dict)}
    errors = []
    seen_ids = set()

    if not isinstance(findings, list):
        return ["findings must be a list"]

    permitted_fields = set(required) | {"details"}
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"finding {index} must be an object")
            continue
        missing = set(required) - set(finding)
        if missing:
            errors.append(f"finding {index} missing fields: {','.join(sorted(missing))}")
        extras = set(finding) - permitted_fields
        if extras:
            errors.append(f"finding {index} has unexpected fields: {','.join(sorted(str(v) for v in extras))}")

        for field in required:
            value = finding.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"finding {index} field {field} must be a non-empty string")
        if any(not isinstance(finding.get(field), str) or not finding[field].strip() for field in required):
            continue

        finding_id = finding["id"]
        if not re.fullmatch(r"AC-[0-9a-f]{12}", finding_id):
            errors.append(f"finding {finding_id} has an invalid ID")
        if finding_id in seen_ids:
            errors.append(f"duplicate finding ID: {finding_id}")
        seen_ids.add(finding_id)

        if finding["agent_id"] not in known_agents:
            errors.append(f"finding {finding_id} references an unknown agent")
        if finding["severity"] not in allowed_severity:
            errors.append(f"finding {finding_id} has unsupported severity")
        if finding["status"] not in allowed_status:
            errors.append(f"finding {finding_id} has unsupported status")
        if len(finding["title"]) > 300 or len(finding["recommendation"]) > 2000:
            errors.append(f"finding {finding_id} text exceeds the report contract limits")

        evidence_path = finding["evidence_path"]
        path_part = evidence_path.split("#", 1)[0]
        path_parts = path_part.split("/")
        if (
            len(evidence_path) > 600
            or evidence_path.startswith(("/", "\\\\"))
            or "\\\\" in evidence_path
            or re.match(r"^[A-Za-z]:", evidence_path)
            or any(part in {"", ".."} for part in path_parts)
            or (len(path_parts) > 1 and "." in path_parts)
            or "://" in evidence_path
            or any(ord(ch) < 32 for ch in evidence_path)
        ):
            errors.append(f"finding {finding_id} has an unsafe evidence path")
        details = finding.get("details")
        if details is not None and (not isinstance(details, str) or len(details) > 2000):
            errors.append(f"finding {finding_id} has invalid details")
    return sorted(set(errors))


def validate_manifest(m):
    """Validate untrusted manifest structure before creating dispatchers or agents."""
    errors = []
    if not isinstance(m, dict):
        return ["manifest must be a JSON object"]
    if m.get("schema") != "aethel-agent-colony/v1":
        errors.append("unsupported schema")

    policy = m.get("policy")
    if not isinstance(policy, dict):
        errors.append("policy must be an object")
        policy = {}
    for key in (
        "allow_repository_writes",
        "allow_merges",
        "allow_live_payments",
        "allow_biometric_actions",
        "allow_secret_access",
        "allow_unrestricted_shell",
        "allow_external_network_from_agent_toolbox",
    ):
        if policy.get(key) is not False:
            errors.append(f"unsafe policy: {key} must be false")
    if policy.get("default_decision") != "HOLD":
        errors.append("policy default_decision must be HOLD")
    if policy.get("require_human_review_for_code_changes") is not True:
        errors.append("policy require_human_review_for_code_changes must be true")

    agents = m.get("agents")
    boxes = m.get("toolboxes")
    if not isinstance(agents, list) or not agents:
        errors.append("agents must be a non-empty list")
        agents = []
    if not isinstance(boxes, list) or not boxes:
        errors.append("toolboxes must be a non-empty list")
        boxes = []

    valid_agents = []
    for index, agent in enumerate(agents):
        if not isinstance(agent, dict):
            errors.append(f"agent entry {index} must be an object")
            continue
        aid = agent.get("id")
        if not isinstance(aid, str) or not aid.strip():
            errors.append(f"agent entry {index} must have a non-empty string id")
            continue
        valid_agents.append(agent)

    valid_boxes = []
    for index, box in enumerate(boxes):
        if not isinstance(box, dict):
            errors.append(f"toolbox entry {index} must be an object")
            continue
        bid = box.get("id")
        if not isinstance(bid, str) or not bid.strip():
            errors.append(f"toolbox entry {index} must have a non-empty string id")
            continue
        valid_boxes.append(box)

    aids = [a["id"] for a in valid_agents]
    bids = [b["id"] for b in valid_boxes]
    if len(aids) != len(set(aids)):
        errors.append("agent IDs must be unique")
    if len(bids) != len(set(bids)):
        errors.append("toolbox IDs must be unique")
    amap = {a["id"]: a for a in valid_agents}
    bmap = {b["id"]: b for b in valid_boxes}

    for box in valid_boxes:
        bid = box["id"]
        allow = box.get("allow")
        deny = box.get("deny")
        if not isinstance(allow, list) or not allow:
            errors.append(f"{bid}: allow must be a non-empty list")
            allow = []
        if not isinstance(deny, list):
            errors.append(f"{bid}: deny must be a list")
            deny = []
        if any(not isinstance(item, str) or not item.strip() for item in allow):
            errors.append(f"{bid}: allow entries must be non-empty strings")
        if any(not isinstance(item, str) or not item.strip() for item in deny):
            errors.append(f"{bid}: deny entries must be non-empty strings")
        if len(allow) != len(set(item for item in allow if isinstance(item, str))):
            errors.append(f"{bid}: duplicate allow capabilities")
        if len(deny) != len(set(item for item in deny if isinstance(item, str))):
            errors.append(f"{bid}: duplicate deny capabilities")
        overlap = set(item for item in allow if isinstance(item, str)) & set(
            item for item in deny if isinstance(item, str)
        )
        if overlap:
            errors.append(f"{bid}: allow/deny overlap: {','.join(sorted(overlap))}")

    for agent in valid_agents:
        aid = agent["id"]
        toolbox_id = agent.get("toolbox_id")
        if not isinstance(toolbox_id, str) or toolbox_id not in bmap:
            errors.append(f"{aid}: toolbox missing")
        else:
            box = bmap[toolbox_id]
            box_deny = box.get("deny", [])
            if not isinstance(box_deny, list):
                box_deny = []
            if aid != "human_release_owner" and not REQUIRED_DENY.issubset(set(
                item for item in box_deny if isinstance(item, str)
            )):
                errors.append(f"{aid}: missing mandatory deny rules")
        deps = agent.get("depends_on", [])
        if not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps):
            errors.append(f"{aid}: depends_on must be a list of agent IDs")
            continue
        for dep in deps:
            if dep not in amap:
                errors.append(f"{aid}: unknown dependency {dep}")

    visiting = set()
    visited = set()

    def visit(aid):
        if aid in visiting:
            errors.append(f"dependency cycle at {aid}")
            return
        if aid in visited or aid not in amap:
            return
        visiting.add(aid)
        deps = amap[aid].get("depends_on", [])
        if isinstance(deps, list):
            for dep in deps:
                if isinstance(dep, str):
                    visit(dep)
        visiting.remove(aid)
        visited.add(aid)

    for aid in aids:
        visit(aid)

    stages = m.get("stages")
    if not isinstance(stages, list) or not stages:
        errors.append("stages must be a non-empty list")
    else:
        stage_ids = set()
        staged_agents = []
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                errors.append(f"stage entry {index} must be an object")
                continue
            sid = stage.get("id")
            members = stage.get("agents")
            if not isinstance(sid, str) or not sid.strip():
                errors.append(f"stage entry {index} must have a non-empty string id")
            elif sid in stage_ids:
                errors.append(f"duplicate stage ID: {sid}")
            else:
                stage_ids.add(sid)
            if not isinstance(members, list) or any(not isinstance(aid, str) for aid in members):
                errors.append(f"stage entry {index} agents must be a list of IDs")
                continue
            staged_agents.extend(members)
            for aid in members:
                if aid not in amap:
                    errors.append(f"stage {sid}: unknown agent {aid}")
                elif amap[aid].get("stage") != sid:
                    errors.append(f"{aid}: stage assignment mismatch")
        if len(staged_agents) != len(set(staged_agents)):
            errors.append("each agent must appear in only one stage")
        if set(staged_agents) != set(aids):
            errors.append("stage membership must cover every agent exactly once")

    contract = m.get("report_contract")
    if not isinstance(contract, dict):
        errors.append("report_contract must be an object")
    else:
        required_fields = contract.get("required_finding_fields")
        severity_values = contract.get("severity_values")
        status_values = contract.get("status_values")
        if not isinstance(required_fields, list) or any(not isinstance(v, str) for v in required_fields):
            errors.append("report_contract required_finding_fields must be a list of strings")
        if not isinstance(severity_values, list) or not severity_values:
            errors.append("report_contract severity_values must be a non-empty list")
        elif any(
            not isinstance(v, str) or v not in {"critical", "high", "medium", "low", "info"}
            for v in severity_values
        ):
            errors.append("report_contract contains unsupported severity")
        if not isinstance(status_values, list) or not status_values:
            errors.append("report_contract status_values must be a non-empty list")
        elif any(not isinstance(v, str) or not v.strip() for v in status_values):
            errors.append("report_contract status_values must contain non-empty strings")
        if not isinstance(contract.get("secret_policy"), str) or not contract["secret_policy"].strip():
            errors.append("report_contract secret_policy is required")

    return sorted(set(errors))


def head_sha(path):
    if not (path/".git").exists(): return None
    try:
        r=subprocess.run(["git","-C",str(path),"rev-parse","HEAD"],check=True,capture_output=True,text=True,timeout=5)
        return r.stdout.strip() if len(r.stdout.strip())==40 else None
    except (OSError, subprocess.SubprocessError): return None


def inventory(root, d):
    rel=str(d.get("path", "")); path=(root/rel).resolve() if rel not in ("", ".") else root
    exists=path.is_dir(); workflows=[]; tests=[]; source_count=0
    if exists:
        for current, dirs, files in os.walk(path):
            dirs[:]=[x for x in dirs if x not in IGNORED_DIRS and not (rel in ("", ".") and x=="federated")]
            for name in files:
                sub=(Path(current)/name).relative_to(path).as_posix()
                if name.endswith((".py", ".rs", ".ts", ".tsx", ".js", ".sol", ".yml", ".yaml", ".json")): source_count+=1
                if sub.startswith(".github/workflows/") and sub.endswith((".yml", ".yaml")): workflows.append(sub)
                if name.startswith("test_") or name.endswith(("_test.py", ".test.ts", ".spec.ts")) or sub.startswith("tests/"): tests.append(sub)
    return {"id":d.get("id"),"role":d.get("role"),"path":rel,"present":exists,"commit_sha":head_sha(path) if exists else None,
            "source_like_file_count":source_count,"workflow_files":sorted(workflows),"test_path_samples":sorted(set(tests))[:25],
            "verification":d.get("verification",[]),"verification_scope":d.get("verification_scope","not declared"),"integration_mode":d.get("integration_mode","not declared")}


def read_text(path):
    try:
        if path.is_file() and path.stat().st_size<1_000_000: return path.read_text(encoding="utf-8",errors="replace")
    except OSError: pass
    return ""


def inspect_existing_agent_stack(root: Path) -> dict:
    specs = [
        ("agent_router_and_quorum", "autonomy/agent_router.py", "Existing registry-based capability ranking and independent-family quorum planner"),
        ("parallel_proposal_transport", "autonomy/multi_agent_provider.py", "Existing concurrent proposal transport with registered identity normalization"),
        ("proposal_only_patch_planner", "autonomy/patch_proposal.py", "Existing bounded, proposal-only patch planner"),
        ("isolated_patch_validator", "autonomy/validate_patch_proposal.py", "Existing secret-free, disposable, network-none patch validation"),
        ("existing_autonomous_workflow", ".github/workflows/caios-autonomous-pr.yml", "Existing proposal, validation and pull-request workflow"),
        ("role_task_context_builder", "ops/agent_colony/collaboration.py", "Role-specific task packets that bind each review role to its declared toolbox"),
    ]
    components=[]
    for component_id, rel, description in specs:
        path=root/rel
        components.append({"id":component_id,"path":rel,"present":path.is_file(),"description":description})
    registry_path=root/"autonomy"/"provider_endpoint_registry.json"
    endpoint_count=None
    registry_valid=False
    if registry_path.is_file():
        try:
            data=json.loads(registry_path.read_text(encoding="utf-8"))
            if isinstance(data,dict) and data.get("schema")=="caios-provider-endpoints/v1" and isinstance(data.get("endpoints"),list):
                registry_valid=True
                endpoint_count=len(data["endpoints"])
        except (OSError,UnicodeDecodeError,json.JSONDecodeError):
            pass
    agent_config=root/"autonomy"/"agent_endpoints.json"
    ready=bool(registry_valid and endpoint_count and agent_config.is_file())
    provider_source=read_text(root/"autonomy"/"multi_agent_provider.py")
    collaboration_test=read_text(root/"autonomy"/"test_multi_agent_provider.py")
    return {
        "strategy":"extend-existing-CAIOS-agent-stack; do-not-create-a-parallel-provider-runtime",
        "components":components,
        "collaboration_contract":{
            "provider_accepts_role_specific_contexts":"task_contexts" in provider_source,
            "fake_provider_concurrency_test_present":"test_provider_fans_out_role_specific_toolboxes_concurrently" in collaboration_test,
            "role_task_contexts_are_tool_authority":False,
            "test_mode":"fake provider; no network calls",
        },
        "provider_configuration":{
            "registry_path":"autonomy/provider_endpoint_registry.json",
            "registry_schema_valid":registry_valid,
            "registered_endpoint_count":endpoint_count,
            "agent_endpoint_config_present":agent_config.is_file(),
            "model_backed_agents_ready":ready,
            "api_key_values_reported":False
        },
        "recommended_next_step":"Use AgentRegistry for capability/family/quorum planning and MultiAgentProposalProvider for parallel role-specific proposals; add a toolbox contract adapter; exercise collaboration with fake providers first. Activate real endpoints only after explicit model/source/protocol/approval pins, egress controls and secret-manager/GitHub-secret configuration."
    }


def scan_env_names(repo, prefix):
    out=[]
    if not repo.is_dir(): return out
    for current, dirs, files in os.walk(repo):
        dirs[:]=[d for d in dirs if d not in IGNORED_DIRS and not (prefix in ("", ".") and d=="federated")]
        for name in files:
            low=name.lower()
            if low in SENSITIVE_NAMES or (low.startswith(".env.") and not low.endswith((".example", ".sample", ".template"))):
                rel=(Path(current)/name).relative_to(repo).as_posix()
                out.append(make_finding("security_analyst","high","Workspace contains a non-example environment file (contents not inspected)",f"{prefix.rstrip('/')}/{rel}".lstrip("/"),"Verify whether values were ever valid; rotate/revoke real or uncertain credentials, remove the file and assess Git-history cleanup. Never copy contents into reports."))
    return out


def run(root: Path, manifest_path: Path, portfolio_path: Path):
    m=load_json(manifest_path); errors=validate_manifest(m)
    if errors: raise ValueError("Colony manifest rejected: "+"; ".join(errors))
    portfolio=load_json(portfolio_path).get("repositories")
    if not isinstance(portfolio,list) or not portfolio: raise ValueError("Portfolio manifest has no repository list")
    toolbox = ToolboxDispatcher(m)
    toolbox.authorize("portfolio_cartographer", "read_declared_manifests", "federation/system_manifest.json")
    inv=[]
    for d in portfolio:
        if not isinstance(d, dict):
            continue
        toolbox.authorize("portfolio_cartographer", "list_repository_paths", str(d.get("path", ".")))
        toolbox.authorize("portfolio_cartographer", "record_commit_sha", str(d.get("path", ".")))
        inv.append(inventory(root,d))
    gates=load_json(root/"conformance/GATE_STATUS.json") if (root/"conformance/GATE_STATUS.json").is_file() else {}
    paths=[(".",root)]+[(r["path"],(root/r["path"]).resolve()) for r in inv if r["present"] and r["path"] not in ("", ".")]

    def protocol_agent():
        toolbox.authorize("protocol_analyst", "read_gate_status", "conformance/GATE_STATUS.json")
        toolbox.authorize("protocol_analyst", "read_specs", "specs/")
        toolbox.authorize("protocol_analyst", "record_evidence_path", "conformance/GATE_STATUS.json")
        out=[]
        rules=[("gate_1","high","Canonical SPEC-004 math remains blocked","Ratify metric law and decision partitions before promotion."),("gate_3","medium","Canonical ledger byte profile remains partially closed","Ratify timestamp/escaping and preimage rules; then run cross-language golden vectors."),("gate_4","medium","Canonical checkpoint/Merkle gate has not started","Specify and test checkpoint semantics before claiming full protocol certification."),("gate_6","high","Level-4 certification remains blocked","Keep promotion on HOLD until prerequisite gates have explicit evidence.")]
        for gid,sev,title,action in rules:
            status=str(gates.get(gid,{}).get("status","UNKNOWN")).upper()
            if status in {"BLOCKED","PARTIALLY_CLOSED","NOT_STARTED","UNKNOWN"}:
                out.append(make_finding("protocol_analyst",sev,title,"conformance/GATE_STATUS.json",action,f"Recorded status: {status}"))
        return out

    def security_agent():
        toolbox.authorize("security_analyst", "detect_sensitive_file_paths_without_printing_contents", "portfolio")
        toolbox.authorize("security_analyst", "inspect_auth_code", "biometric attestation")
        toolbox.authorize("security_analyst", "inspect_payment_gates", "live transfer path")
        out=[]
        for rel,repo in paths:
            out.extend(scan_env_names(repo,rel))
            bp=repo/"backend/biometric_routes.py"
            if bp.is_file():
                src=read_text(bp); marker='@router.post("/attest")'; seg=src.split(marker,1)[1].split("@router.",1)[0] if marker in src else ""
                scanner_headers=all(x in seg for x in ("X-Scanner-Timestamp","X-Scanner-Nonce","X-Scanner-Signature"))
                scanner_verifier=("verify_scanner_request(" in seg and "scanner_auth" in src)
                if not scanner_headers or not scanner_verifier:
                    out.append(make_finding("security_analyst","critical","Biometric attestation lacks visible request-signature admission",f"{rel.rstrip('/')}/backend/biometric_routes.py".lstrip("/"),"Require per-scanner authentication, signed body/liveness, freshness, persistent single-use nonces and replay tests."))
            sp=repo/"backend/stripe_bridge.py"
            if sp.is_file():
                src=read_text(sp)
                transfer_body=src.split("def _live_transfer(",1)[1].split("# ── Main entry point",1)[0] if "def _live_transfer(" in src else ""
                payment_body=src.split("def process_manna_payment(",1)[1].split("# ── Webhook verification",1)[0] if "def process_manna_payment(" in src else ""
                live_flag="COLONY_LIVE_PAYMENTS_ENABLED" in payment_body
                receipt_check="verify_transfer_admission(" in payment_body
                receipt_check_precedes_transfer=(
                    "verify_transfer_admission(" in payment_body
                    and "_live_transfer(" in payment_body
                    and payment_body.index("verify_transfer_admission(") < payment_body.index("_live_transfer(")
                )
                primitive_guard="if _permit is not _TRANSFER_CALL_PERMIT:" in transfer_body
                all_three_calls_guarded=payment_body.count("_permit=_TRANSFER_CALL_PERMIT") >= 3
                admission_tests=read_text(repo/"tests/test_payment_admission.py")
                direct_bypass_test="test_raw_transfer_primitive_denies_direct_invocation" in admission_tests
                if "stripe.Transfer.create(" in transfer_body and not all((
                    live_flag, receipt_check, receipt_check_precedes_transfer,
                    primitive_guard, all_three_calls_guarded, direct_bypass_test,
                )):
                    out.append(make_finding("security_analyst","critical","Live Stripe transfer lacks complete signed-admission boundary",f"{rel.rstrip('/')}/backend/stripe_bridge.py".lstrip("/"),"Keep live transfer disabled until the payment entrypoint verifies a task/lineage/amount-bound receipt before any transfer, the raw Stripe primitive rejects direct invocation, all transfer calls carry the verified permit, and bypass tests pass."))
        return out

    def devops_agent():
        toolbox.authorize("devops_qa", "read_workflows", "portfolio workflows")
        toolbox.authorize("devops_qa", "read_test_definitions", "portfolio test paths")
        out=[]
        for r in inv:
            if not r["present"]: out.append(make_finding("devops_qa","high","Manifest repository checkout is missing",r["path"] or ".","Fix checkout path and record the exact repository revision."))
            if r["present"] and not r["workflow_files"]: out.append(make_finding("devops_qa","low","No GitHub Actions workflow files found",r["path"] or ".","Confirm CI is managed elsewhere or add a minimal read-only test workflow."))
            if not r["verification"]: out.append(make_finding("devops_qa","medium","No verification command declared",r["path"] or ".","Declare a test command and state the limits of its coverage."))
        return out

    def toolbox_agent():
        toolbox.authorize("toolbox_architect", "read_agent_manifest", "ops/agent_colony/manifest.json")
        toolbox.authorize("toolbox_architect", "validate_toolbox_allowlists", "ops/agent_colony/manifest.json")
        toolbox.authorize("toolbox_architect", "inspect_existing_agent_stack", "autonomy/agent_router.py; autonomy/multi_agent_provider.py; provider registry")
        out=[]; byid={b["id"]:b for b in m["toolboxes"]}
        stack = inspect_existing_agent_stack(root)
        if not stack["provider_configuration"]["model_backed_agents_ready"]:
            out.append(make_finding("toolbox_architect","medium","Model-backed collaboration is not configured in CAIOS","autonomy/provider_endpoint_registry.json","Reuse autonomy/agent_router.py, autonomy/multi_agent_provider.py, autonomy/patch_proposal.py and autonomy/validate_patch_proposal.py; first prove the role/task/toolbox contract with fake providers. Do not add live endpoints or keys until an operator approves exact model/source/protocol pins and egress controls.",f"registered_endpoint_count={stack['provider_configuration']['registered_endpoint_count']}; agent_endpoints_config_present={stack['provider_configuration']['agent_endpoint_config_present']}"))
        for a in m["agents"]:
            box=byid.get(a["toolbox_id"])
            if not box or not box.get("allow"): out.append(make_finding("toolbox_architect","high","Agent has no toolbox allowlist",a["id"],"Give the agent a reviewed, minimal allowlist."))
            elif a["id"]!="human_release_owner" and not REQUIRED_DENY.issubset(set(box.get("deny",[]))): out.append(make_finding("toolbox_architect","critical","Automated toolbox lacks mandatory deny rules",f"ops/agent_colony/manifest.json#{a['toolbox_id']}","Deny writes, push, merge, secret reads and network requests by default."))
        return out

    # Domain agents run concurrently on the same immutable checkout snapshot.
    stage1=[]
    with ThreadPoolExecutor(max_workers=4,thread_name_prefix="aethel-agent") as pool:
        futures=[pool.submit(fn) for fn in (protocol_agent,security_agent,devops_agent,toolbox_agent)]
        for future in as_completed(futures): stage1.extend(future.result())
    # Integrator and independent evidence challenger collaborate concurrently.
    required=set(m["report_contract"]["required_finding_fields"])
    def synthesize():
        toolbox.authorize("integration_synthesizer", "read_agent_reports", "current cycle findings")
        toolbox.authorize("integration_synthesizer", "deduplicate_findings", "current cycle findings")
        toolbox.authorize("integration_synthesizer", "order_dependencies", "current cycle findings")
        return list({f["id"]:f for f in stage1}.values())
    def redteam():
        toolbox.authorize("independent_redteam", "challenge_claims", "current cycle findings")
        toolbox.authorize("independent_redteam", "check_evidence_presence", "current cycle findings")
        toolbox.authorize("independent_redteam", "check_permission_boundaries", "manifest and report")
        return [make_finding("independent_redteam","critical","Agent output missing evidence fields",f.get("evidence_path","unknown"),"Reject output until all evidence fields exist.",f"Missing: {', '.join(sorted(required-set(f)))}") for f in stage1 if required-set(f)]
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix="aethel-review") as pool:
        synth_future=pool.submit(synthesize); redteam_future=pool.submit(redteam); integrated=synth_future.result(); redteam_findings=redteam_future.result()
    findings=list({f["id"]:f for f in integrated+redteam_findings}.values())
    findings.sort(key=lambda f:(SEVERITY[f["severity"]],f["agent_id"],f["id"]))
    contract_errors=validate_finding_contract(findings,m)
    if contract_errors: raise ValueError("Generated finding fails report contract: "+"; ".join(contract_errors))
    counts={s:sum(1 for f in findings if f["severity"]==s) for s in SEVERITY}
    hold=counts["critical"]>0 or counts["high"]>0 or str(gates.get("gate_6",{}).get("status","UNKNOWN")).upper()=="BLOCKED"
    agent_runs=[{"id":"portfolio_cartographer","status":"completed","execution_mode":"inventory"}]
    for aid in ("protocol_analyst","security_analyst","devops_qa","toolbox_architect"):
        agent_runs.append({"id":aid,"status":"completed","execution_mode":"parallel-deterministic-probe","findings_generated":sum(1 for f in stage1 if f["agent_id"]==aid)})
    agent_runs += [{"id":"integration_synthesizer","status":"completed","execution_mode":"parallel-evidence-join","findings_integrated":len(integrated)},{"id":"independent_redteam","status":"completed","execution_mode":"parallel-evidence-contract-challenge","findings_generated":len(redteam_findings)},{"id":"human_release_owner","status":"awaiting-human-review","execution_mode":"human-only-gate"}]
    return {"schema":"aethel-agent-colony-report/v1","generated_at_utc":datetime.now(timezone.utc).isoformat(),"colony_version":m.get("version"),"operating_mode":m.get("operating_mode"),"source_revision":head_sha(root),"source_head_sha":os.getenv("AETHEL_COLONY_HEAD_SHA") or head_sha(root),"source_base_sha":os.getenv("AETHEL_COLONY_BASE_SHA"),
            "portfolio":{"manifest":str(portfolio_path),"repositories_total":len(inv),"repositories_present":sum(r["present"] for r in inv),"repositories":inv},
            "architecture_review":inspect_existing_agent_stack(root),
            "agents":m["agents"],"agent_runs":agent_runs,"tool_execution_audit":toolbox.audit_log(),"findings_summary":{"total":len(findings),**counts},"release_decision":"HOLD" if hold else "REVIEW","findings":findings,
            "limits":["Deterministic probes, not model-backed LLM agents.","Inspected repository code is not executed.","Environment-file path findings do not prove a credential is valid; values are never reported.","This report is not production-security or protocol certification."]}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--repo-root",type=Path,default=Path.cwd()); p.add_argument("--manifest",type=Path,default=Path("ops/agent_colony/manifest.json")); p.add_argument("--system-manifest",type=Path,default=Path("federation/system_manifest.json")); p.add_argument("--output",type=Path,default=Path("agent-colony-report.json")); a=p.parse_args(argv)
    root=a.repo_root.resolve(); mp=a.manifest if a.manifest.is_absolute() else root/a.manifest; pp=a.system_manifest if a.system_manifest.is_absolute() else root/a.system_manifest; op=a.output if a.output.is_absolute() else root/a.output
    try:
        report=run(root,mp,pp); op.parent.mkdir(parents=True,exist_ok=True); op.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(json.dumps({"status":"PASS","output":str(op),"repositories":report["portfolio"]["repositories_total"],"present":report["portfolio"]["repositories_present"],"findings":report["findings_summary"],"release_decision":report["release_decision"]},indent=2)); return 0
    except (OSError,ValueError,json.JSONDecodeError) as exc:
        print(f"COLONY_BLOCKED: {exc}",file=sys.stderr); return 2

if __name__=="__main__": raise SystemExit(main())
