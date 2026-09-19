from langchain.agents import create_agent
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from tools import web_search, scrape_url, academic_search
import json
import os
import time

from dotenv import load_dotenv

load_dotenv()

# llama-3.1-8b-instant has a much higher free-tier TPM than gpt-oss-120b.
# You can override via GROQ_MODEL in your .env if you want a bigger model.
llm = ChatGroq(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-safeguard-20b"))


def _invoke_with_retry(chain, inputs: dict, max_retries: int = 4, base_wait: float = 8.0) -> str:
    """Invoke a LangChain chain and retry on 429 / 503 errors with
    exponential back-off. Raises the last exception if all retries fail."""
    for attempt in range(max_retries):
        try:
            return chain.invoke(inputs)
        except Exception as e:
            err = str(e)
            if any(code in err for code in ("429", "503", "rate_limit_exceeded", "UNAVAILABLE")):
                wait = base_wait * (2 ** attempt)
                print(f"[retry] API error ({err[:60]}), waiting {wait:.1f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"All {max_retries} retries failed (rate limit / service unavailable.")


def build_search_agent():
    return create_agent(
        model=llm,
        tools=[web_search]
    )


def build_reader_agent():
    return create_agent(
        model=llm,
        tools=[scrape_url]
    )


def build_academic_agent():
    return create_agent(
        model=llm,
        tools=[academic_search]
    )


writer_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert research writer. Write clear, structured and insightful reports."),
    ("human", """Write a detailed research report on a topic below.
    Topic :
    {topic}

    research gather :
    {research}

    Structure the report using this exact markdown format:

    ## Introduction
    2-4 sentences framing the topic and why it matters.

    ## Key Findings
    Present at least three findings as a markdown table with these exact columns:

    | # | Finding | Evidence & Explanation |
    |---|---------|-------------------------|
    | 1 | One-sentence finding, stated as fact | 2-3 sentences of supporting evidence and explanation, citing specific numbers, sources, or study names from the research where available |

    Each "Evidence & Explanation" cell should be a real paragraph of explanation, not a single fragment.

    ## Conclusion
    2-4 sentences synthesizing what the findings mean.

    ## Sources
    A markdown bullet list of every URL found in the research (one per line, plain URLs, no invented links).

    - Be detailed, factual, and professional. Use plain markdown only (no HTML tags, no footnote brackets like 【】).
    """)
])

writer_chain = writer_prompt | llm | StrOutputParser()

critic_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a rigorous academic reviewer and critical editor.
    Your goal is to evaluate research reports for accuracy, structure, depth, and strict adherence to requirements, providing clear and actionable feedback for improvement.
    Use plain markdown only: no HTML tags (no <br>, no <table>). For multi-part comments, use a markdown bullet list (lines starting with "-"), never HTML line breaks."""),
    ("human", """Review the research report provided below against the original prompt and research materials.

report :
{report}

Evaluate the report on the following criteria:
1. Structure & Completeness: Does it contain all four required sections (Introduction, Key Findings with at least 3 detailed points, Conclusion, Sources)?
2. Source Accuracy: Are all URLs from the gathered research accurately listed in the Sources section without invention?
3. Quality & Insight: Is the analysis factual, professional, detailed, and directly supported by the research?

Respond in this exact markdown structure:

## Overall score
State your own score for this report as a single line: `Score: X/10` (replace X with a real number you assign — do not leave it as a placeholder).

## Assessment
A markdown table with columns: | Criterion | Rating (out of 10) | Comments |
One row per criterion above. Inside the Comments cell, if you need multiple points, separate them with "; " on one line — do not use <br> or line breaks inside a cell.

## Revision instructions
A numbered markdown list of clear, direct directives on what the writer needs to fix to produce a final, polished version.
    """)
])

critic_chain = critic_prompt | llm | StrOutputParser()


# ---------------------------------------------------------------------------
# v2 additions: planner, claim extraction, claim verification
# ---------------------------------------------------------------------------

def _parse_json_list(raw: str) -> list:
    """Best-effort JSON list parse. LLMs sometimes wrap output in ```json
    fences despite instructions not to — strip those before parsing."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        parsed = json.loads(cleaned.strip())
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


planner_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a research planner. Break a topic into a small set of "
               "concrete, non-overlapping sub-questions that together cover it well."),
    ("human", """Topic: {topic}

Return EXACTLY 2 sub-queries that would find the key facts needed to write a
thorough report on this topic. Respond with ONLY a JSON array of 2 strings,
no preamble, no markdown fences. Example: ["sub-query one", "sub-query two"]
""")
])
planner_chain = planner_prompt | llm | StrOutputParser()


def plan_sub_queries(topic: str) -> list[str]:
    sub_queries = _parse_json_list(_invoke_with_retry(planner_chain, {"topic": topic}))
    if not sub_queries:
        return [topic]
    return sub_queries[:2]  # hard cap — never send more than 2 to the research stage


claim_extraction_prompt = ChatPromptTemplate.from_messages([
    ("system", "You extract discrete, checkable factual claims from research notes. "
               "Each claim should be a single self-contained statement that could be "
               "individually verified as true or false against evidence."),
    ("human", """Research notes on "{topic}":

{evidence}

Extract 4-8 distinct factual claims made or implied by these notes.
Respond with ONLY a JSON array of strings (the claims), no preamble, no markdown fences.
""")
])
claim_extraction_chain = claim_extraction_prompt | llm | StrOutputParser()


def extract_claims(topic: str, evidence: str) -> list[str]:
    # Truncate to ~3000 chars — enough signal, stays well under the 7K ITPM limit
    trimmed = evidence[:3000]
    return _parse_json_list(_invoke_with_retry(claim_extraction_chain, {"topic": topic, "evidence": trimmed}))


verification_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a strict fact-checker. Judge whether a claim is backed by "
               "given evidence. Do not use outside knowledge — judge only against "
               "the evidence provided."),
    ("human", """Claim: {claim}

Evidence:
{evidence}

Does the evidence support this claim? Respond with ONLY one word:
"supported" if the evidence clearly backs the claim,
"contradicted" if the evidence clearly contradicts it,
"missing" if the evidence says nothing relevant to judge it either way.
""")
])
verification_chain = verification_prompt | llm | StrOutputParser()


def verify_claim(claim: str, evidence: str) -> str:
    # Truncate to ~2000 chars per verification call — claim + evidence must stay under 7K ITPM
    trimmed = evidence[:2000]
    result = _invoke_with_retry(verification_chain, {"claim": claim, "evidence": trimmed}).strip().lower()
    for status in ("supported", "contradicted", "missing"):
        if status in result:
            return status
    return "missing"