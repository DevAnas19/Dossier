from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
import time

from agents import (
    build_search_agent,
    build_reader_agent,
    build_academic_agent,
    writer_chain,
    critic_chain,
    plan_sub_queries,
    extract_claims,
    verify_claim,
    _invoke_with_retry,
)

MAX_VERIFICATION_ROUNDS = 1   # dropped from 2 — saves 4-8 API calls per run
AGENT_TIMEOUT = 45            # seconds before we give up on one agent call


def _run_agent(agent, message: str) -> str:
    result = agent.invoke({"messages": [("user", message)]})
    return result["messages"][-1].content


def _safe_run_agent(agent, message: str, fallback: str = "") -> str:
    """Run an agent with a timeout. Returns fallback string on timeout or error
    so one failing source doesn't crash the whole pipeline."""
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_agent, agent, message)
            return future.result(timeout=AGENT_TIMEOUT)
    except FuturesTimeout:
        print(f"[timeout] agent timed out after {AGENT_TIMEOUT}s, skipping")
        return fallback
    except Exception as e:
        print(f"[error] agent failed: {str(e)[:120]}, skipping")
        return fallback


def _research_sub_query(sub_query: str) -> str:
    """Run web search then academic search SEQUENTIALLY with a gap between
    them. Parallel calls doubled the burst rate and caused most 429/503s."""
    web_result = _safe_run_agent(
        build_search_agent(),
        f"find recent, reliable information about: {sub_query}. "
        f"Return a brief summary of the top 3 findings only.",
        fallback="[web search unavailable for this sub-query]"
    )
    time.sleep(4)  # breathing room between the two agent calls

    academic_result = _safe_run_agent(
        build_academic_agent(),
        f"find 2-3 academic or peer-reviewed sources about: {sub_query}. "
        f"Return titles, authors, and a one-sentence summary per paper.",
        fallback="[academic search unavailable for this sub-query]"
    )

    return (
        f"--- Sub-query: {sub_query} ---\n"
        f"WEB:\n{web_result}\n\n"
        f"ACADEMIC:\n{academic_result}\n"
    )


def run_research_pipeline(topic: str, on_update=None) -> dict:
    def notify(step_index, step_name, status, detail=""):
        if on_update:
            on_update(step_index, step_name, status, detail)

    state = {}

    # step 1 - planner (max 2 sub-queries)
    notify(1, "plan", "running")
    sub_queries = plan_sub_queries(topic)
    state["sub_queries"] = sub_queries
    notify(1, "plan", "done", ", ".join(sub_queries))

    # step 2 - research: run sub-queries sequentially, not in parallel
    notify(2, "research", "running")
    evidence_blocks = []
    for i, q in enumerate(sub_queries):
        notify(2, "research", "running", f"researching: {q}")
        evidence_blocks.append(_research_sub_query(q))
        if i < len(sub_queries) - 1:
            time.sleep(3)  # gap between sub-queries
    state["evidence"] = "\n\n".join(evidence_blocks)
    notify(2, "research", "done", state["evidence"][:300])

    # step 3 - claim extraction
    notify(3, "extract", "running")
    claims = extract_claims(topic, state["evidence"])
    # cap at 5 claims — more than that multiplies verification calls too much
    claims = claims[:5]
    state["claims"] = {c: "unverified" for c in claims}
    notify(3, "extract", "done", f"{len(claims)} claims extracted")

    # step 4 - single verification pass (no retry loop — saves 4-8 calls)
    notify(4, "verify", "running")
    for claim in state["claims"]:
        state["claims"][claim] = verify_claim(claim, state["evidence"])
        time.sleep(2)  # gap between each verification call

    supported   = sum(1 for s in state["claims"].values() if s == "supported")
    contradicted = sum(1 for s in state["claims"].values() if s == "contradicted")
    unresolved  = sum(1 for s in state["claims"].values() if s == "missing")
    state["claim_summary"] = {
        "supported": supported,
        "contradicted": contradicted,
        "unresolved": unresolved,
    }
    notify(4, "verify", "done", f"{supported} supported, {contradicted} contradicted, {unresolved} unresolved")

    # step 5 - writer
    notify(5, "write", "running")
    claims_report = "\n".join(
        f"- [{status.upper()}] {claim}"
        for claim, status in state["claims"].items()
    )
    research_combined = (
        f"VERIFIED CLAIMS:\n{claims_report}\n\n"
        f"SUPPORTING EVIDENCE:\n{state['evidence'][:2500]}"
    )
    state["report"] = _invoke_with_retry(writer_chain, {
        "topic": topic,
        "research": research_combined,
    })
    notify(5, "write", "done", state["report"][:300])

    # step 6 - critic
    notify(6, "review", "running")
    state["feedback"] = _invoke_with_retry(critic_chain, {
        "report": state["report"],
    })
    notify(6, "review", "done", state["feedback"][:300])

    return state


if __name__ == "__main__":
    topic = input("\n Enter a Research topic : ")
    result = run_research_pipeline(topic, on_update=lambda i, n, s, d: print(f"[{i}] {n} -> {s}  {d[:80]}"))
    print("\n CLAIM SUMMARY \n", result["claim_summary"])
    print("\n FINAL REPORT \n", result["report"])
    print("\n CRITIC REPORT \n", result["feedback"])