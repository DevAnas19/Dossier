from langchain.tools import tool
import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient
import os

from dotenv import load_dotenv
load_dotenv()

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


@tool
def web_search(query: str) -> str:
    """Search the web for a given query and it should be recent and reliable information on a topic, Returns Titles, URLs and snippets """
    response = tavily.search(query=query, max_results=5)
    results = response["results"]  # tavily.search returns a dict; the list lives under "results"

    out = []

    for r in results:
        out.append(
            f"Title: {r['title']}\nURL: {r['url']}\nSnippet: {r['content'][:300]}\n"
        )
    return "\n------\n".join(out)


@tool
def academic_search(query: str) -> str:
    """Search academic literature (Semantic Scholar) for a given query.
    Returns Titles, URLs (to the paper page), and abstract snippets.
    Use this for claims that need scholarly / peer-reviewed backing."""
    try:
        response = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "limit": 5,
                "fields": "title,abstract,url,year,authors",
            },
            timeout=10,
        )
        response.raise_for_status()
        papers = response.json().get("data", [])
    except requests.exceptions.RequestException as e:
        return f"Error searching academic sources: {str(e)}"

    if not papers:
        return "No academic results found."

    out = []
    for p in papers:
        authors = ", ".join(a["name"] for a in (p.get("authors") or [])[:3])
        abstract = (p.get("abstract") or "No abstract available.")[:300]
        out.append(
            f"Title: {p.get('title')}\n"
            f"Year: {p.get('year')}\n"
            f"Authors: {authors}\n"
            f"URL: {p.get('url')}\n"
            f"Abstract: {abstract}\n"
        )
    return "\n------\n".join(out)


@tool
def scrape_url(url: str) -> str:
    """
    Scrape a webpage from a given URL and return its clean text content.
    Use this tool when detailed information from a specific webpage is needed.
    """

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        return text[:3000]

    except requests.exceptions.RequestException as e:
        return f"Error scraping URL: {str(e)}"

    except Exception as e:
        return f"Unexpected error: {str(e)}"