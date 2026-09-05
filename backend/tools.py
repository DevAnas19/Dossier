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
