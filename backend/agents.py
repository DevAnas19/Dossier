from langchain.agents import create_agent
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from tools import web_search, scrape_url
import os

from dotenv import load_dotenv

load_dotenv()

# gpt-oss-120b is Groq's recommended replacement for the deprecated
# llama-3.3-70b-versatile model. Swap this string if you want a different
# free-tier Groq model.
llm = ChatGroq(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))


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
