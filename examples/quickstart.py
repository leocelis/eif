"""EIF quickstart - minimal end-to-end example.

Run:
    cd /path/to/eif
    pip install -e ".[mcp]"
    python examples/quickstart.py
"""

from __future__ import annotations

import asyncio

# ─────────────────────────────────────────────────────────────────────────────
# Simulated agent response (replace with your actual agent call)
# ─────────────────────────────────────────────────────────────────────────────

AGENT_RESPONSE = """
To handle 10x traffic growth, I recommend migrating your Rails monolith to microservices.
Your current system handles 1000 RPS at 50ms P99 latency.
Microservices will reduce that latency to ~20ms and allow you to scale each service
independently. The migration will take 6-9 months with a team of 4 engineers.
Cloud infrastructure cost will be approximately $8,000/month after migration.
"""

CLAIMS = [
    {
        "text": "Current system handles 1000 RPS at 50ms P99 latency",
        "claim_type": "ASSUMED",
        "consequence_of_wrong": "HIGH",
        "falsification_condition": "Measure actual peak RPS in production monitoring; if < 500, claim is wrong",
    },
    {
        "text": "Microservices will reduce P99 latency to ~20ms",
        "claim_type": "GUESSED",
        "consequence_of_wrong": "HIGH",
        "falsification_condition": "Benchmark P99 latency in staging with microservice architecture; if > 30ms, claim fails",
    },
    {
        "text": "Migration will take 6-9 months with 4 engineers",
        "claim_type": "ASSUMED",
        "consequence_of_wrong": "MEDIUM",
        "falsification_condition": "Track milestone completion; if milestone 1 takes > 3 months, original estimate is wrong",
    },
    {
        "text": "Cloud infrastructure cost will be ~$8,000/month",
        "claim_type": "GUESSED",
        "consequence_of_wrong": "MEDIUM",
        "falsification_condition": "Run AWS Cost Calculator with actual service specs; if estimate differs by > 30%, claim fails",
    },
]


async def run_eif(claims: list[dict], decision: str) -> None:
    """Run the EIF loop on a set of claims."""
    from eif import session as session_store
    from eif.calibrate.bayesian import compute_posterior
    from eif.mcp_server.server import eif_declare

    # ── Create session ───────────────────────────────────────────────────────
    sess = await session_store.new_session()
    sid = sess.session_id
    print(f"\n{'='*60}")
    print(f"EIF session: {sid}")
    print(f"Decision: {decision}")
    print(f"{'='*60}\n")

    # ── DECLARE ──────────────────────────────────────────────────────────────
    print("Phase 1: DECLARE - classifying assumptions...")
    declare_result = await eif_declare(
        session_id=sid,
        decision=decision,
        claims=claims,
    )

    reg = declare_result.get("registry", {})
    n_k = len(reg.get("known", []))
    n_a = len(reg.get("assumed", []))
    n_g = len(reg.get("guessed", []))
    print(f"  KNOWN: {n_k}  ASSUMED: {n_a}  GUESSED: {n_g}")

    high_risk = declare_result.get("high_risk_claims", [])
    if high_risk:
        print(f"  HIGH-risk claims ({len(high_risk)}):")
        for c in high_risk[:3]:
            print(f"    ⚠  {c.get('text', '')[:70]}")

    # ── CALIBRATE (simplified - no external evidence in this demo) ───────────
    print("\nPhase 3: CALIBRATE - computing posteriors...")
    routes = []
    for claim in claims:
        ct = claim.get("claim_type", "ASSUMED")
        cq = claim.get("consequence_of_wrong", "MEDIUM")
        prior = {"KNOWN": 0.80, "ASSUMED": 0.50, "GUESSED": 0.30}.get(ct, 0.50)
        # Without external evidence, use neutral likelihood (0.52)
        posterior, _ = compute_posterior(prior, True, 0.52)
        act_thresh  = 0.80 if cq == "HIGH" else 0.70
        halt_thresh = 0.40 if cq == "HIGH" else 0.35
        route = "ACT" if posterior >= act_thresh else ("HALT" if posterior <= halt_thresh else "REVISE")
        routes.append(route)
        sym = {"ACT": "✓", "REVISE": "⚠", "HALT": "⛔"}.get(route, "?")
        print(f"  {sym} [{route}] prior={prior:.2f} → posterior={posterior:.2f}  «{claim['text'][:50]}»")

    overall = "HALT" if "HALT" in routes else ("REVISE" if "REVISE" in routes else "ACT")
    print(f"\n  Overall routing: {'⛔ HALT' if overall=='HALT' else '⚠ REVISE' if overall=='REVISE' else '✓ ACT'}")

    # ── EXPLAIN ──────────────────────────────────────────────────────────────
    print("\nPhase 5: EXPLAIN - checking if response is hard-to-vary...")
    from eif.explain.hard_to_vary import ExplanationDetail, check_hard_to_vary

    # Simulate extracted details
    details = [
        ExplanationDetail(
            detail_text="Current system handles 1000 RPS at 50ms P99",
            prediction_impact="If wrong, migration scope and cost estimates collapse",
        ),
        ExplanationDetail(
            detail_text="Microservices reduce P99 latency to ~20ms",
            prediction_impact="If wrong, the latency benefit argument disappears",
        ),
    ]
    htv = check_hard_to_vary(details)
    print(f"  Hard-to-vary verdict: {'✓ PASS' if htv == 'PASS' else '✗ FAIL'}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("EIF SUMMARY")
    print(f"{'='*60}")
    print(f"Claims declared : {len(claims)} ({n_a + n_g} assumptions, {n_k} known)")
    print(f"High-risk       : {len(high_risk)}")
    print(f"Overall routing : {overall}")
    print(f"HTV verdict     : {htv}")
    print()

    if overall == "HALT":
        print("⛔ EIF recommends HALT - do not proceed with this decision.")
        print("   At least one HIGH-consequence claim has insufficient evidence.")
    elif overall == "REVISE":
        print("⚠  EIF recommends REVISE - gather more evidence before acting.")
        print("   Multiple ASSUMED claims need independent validation.")
    else:
        print("✓  EIF recommends ACT - evidence supports proceeding.")

    print()
    print("Next steps:")
    print("  1. Add P1 code execution to verify the 1000 RPS claim against production metrics")
    print("  2. Add P3 web search to validate the latency improvement benchmark")
    print("  3. Run eif_falsify() with evidence to update posteriors")


if __name__ == "__main__":
    asyncio.run(run_eif(CLAIMS, "Migrate Rails monolith to microservices for 10x traffic"))
