from agents import build_search_agent, build_reader_agent, writer_chain, critic_chain


def run_research_pipeline(topic: str, on_update=None) -> dict:
    """
    Runs the 4-stage research pipeline.

    on_update, if provided, is called as on_update(step_index, step_name, status, detail)
    after each stage starts/finishes, so a caller (e.g. the FastAPI layer) can
    report live progress to a client instead of just printing to a console.
    status is one of: "running", "done", "error"
    """

    def notify(step_index, step_name, status, detail=""):
        if on_update:
            on_update(step_index, step_name, status, detail)

    state = {}

    # step 1 - search agent
    notify(1, "search", "running")
    search_agent = build_search_agent()
    search_result = search_agent.invoke({
        "messages": [("user", f"find recent, reliable and detailed information about : {topic}")]
    })
    state["search_results"] = search_result["messages"][-1].content
    notify(1, "search", "done", state["search_results"][:400])

    # step 2 - reader agent
    notify(2, "scrape", "running")
    reader_agent = build_reader_agent()
    reader_result = reader_agent.invoke({
        "messages": [("user",
            f"Based on the following Search result about '{topic}' pick the most relevant URL and scrape it for deeper content.\n\n"
            f"Search Results: \n{state['search_results'][:800]}"
        )]
    })
    state["scraped_content"] = reader_result["messages"][-1].content
    notify(2, "scrape", "done", state["scraped_content"][:400])

    # step 3 - writer chain
    notify(3, "write", "running")
    research_combined = (
        f"SEARCH RESULT : \n {state['search_results']} \n\n"
        f"DETAILED SCRAPE CONTENT : \n {state['scraped_content']}"
    )
    state["report"] = writer_chain.invoke({
        "topic": topic,
        "research": research_combined
    })
    notify(3, "write", "done", state["report"][:400])

    # step 4 - critic chain
    notify(4, "review", "running")
    state["feedback"] = critic_chain.invoke({
        "report": state["report"]
    })
    notify(4, "review", "done", state["feedback"][:400])

    return state


if __name__ == "__main__":
    topic = input("\n Enter a Research topic : ")
    result = run_research_pipeline(topic, on_update=lambda i, n, s, d: print(f"[{i}] {n} -> {s}"))
    print("\n FINAL REPORT \n", result["report"])
    print("\n CRITIC REPORT \n", result["feedback"])
