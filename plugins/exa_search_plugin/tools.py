import logging
import os
import requests
from typing import Dict, Any, List, Optional

from agent_network.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)

EXA_API_BASE = "https://api.exa.ai"


class ExaSearchTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="exa_search",
            description=(
                "Search the web using Exa.ai's AI-powered search engine. "
                "Supports semantic/neural search, finding similar pages, and retrieving page contents. "
                "Actions: 'search' (search the web with a query), "
                "'find_similar' (find pages similar to a given URL), "
                "'get_contents' (get the text content of specific URLs). "
                "Requires 'action' dict with 'type' and relevant parameters. "
                "Example: {\"action\": {\"type\": \"search\", \"query\": \"latest AI news\"}}"
            )
        )
        self.api_key = os.environ.get("EXA_API_KEY", "")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }

    def _search(self, query: str, num_results: int = 5, category: str = None,
                include_text: bool = True, search_type: str = "auto") -> Dict[str, Any]:
        """Search the web using Exa."""
        payload = {
            "query": query,
            "type": search_type,
            "numResults": min(num_results, 10),
            "contents": {
                "text": {"maxCharacters": 1000} if include_text else False,
                "highlights": True
            }
        }
        if category:
            payload["category"] = category

        try:
            resp = requests.post(f"{EXA_API_BASE}/search", json=payload,
                                 headers=self._get_headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for r in data.get("results", []):
                result = {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "published": r.get("publishedDate", ""),
                }
                if r.get("text"):
                    result["text"] = r["text"][:500]
                if r.get("highlights"):
                    result["highlights"] = r["highlights"][:3]
                if r.get("summary"):
                    result["summary"] = r["summary"]
                results.append(result)

            return {
                "status": "success",
                "output": f"Found {len(results)} results for '{query}'.",
                "results": results
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Exa search error: {e}")
            return {"status": "error", "output": f"Search failed: {e}"}

    def _find_similar(self, url: str, num_results: int = 5) -> Dict[str, Any]:
        """Find pages similar to a given URL."""
        payload = {
            "url": url,
            "numResults": min(num_results, 10),
            "contents": {
                "text": {"maxCharacters": 500},
                "highlights": True
            }
        }

        try:
            resp = requests.post(f"{EXA_API_BASE}/findSimilar", json=payload,
                                 headers=self._get_headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for r in data.get("results", []):
                result = {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                }
                if r.get("text"):
                    result["text"] = r["text"][:300]
                if r.get("highlights"):
                    result["highlights"] = r["highlights"][:2]
                results.append(result)

            return {
                "status": "success",
                "output": f"Found {len(results)} similar pages to '{url}'.",
                "results": results
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Exa find_similar error: {e}")
            return {"status": "error", "output": f"Find similar failed: {e}"}

    def _get_contents(self, urls: List[str]) -> Dict[str, Any]:
        """Get the text content of specific URLs."""
        payload = {
            "ids": urls[:5],
            "text": {"maxCharacters": 2000},
            "highlights": True
        }

        try:
            resp = requests.post(f"{EXA_API_BASE}/contents", json=payload,
                                 headers=self._get_headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for r in data.get("results", []):
                result = {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                }
                if r.get("text"):
                    result["text"] = r["text"][:1000]
                results.append(result)

            return {
                "status": "success",
                "output": f"Retrieved content from {len(results)} page(s).",
                "results": results
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Exa get_contents error: {e}")
            return {"status": "error", "output": f"Get contents failed: {e}"}

    def run(self, **kwargs):
        """Execute an Exa search action."""
        if not self.api_key:
            return {"status": "error", "output": "EXA_API_KEY is not configured. Set it in Admin Settings."}

        action = kwargs.get("action", {})
        action_type = action.get("type") or kwargs.get("action_type")

        if action_type == "search":
            query = action.get("query") or kwargs.get("query")
            if not query:
                return {"status": "error", "output": "Query is required for search."}
            return self._search(
                query=query,
                num_results=action.get("num_results", 5),
                category=action.get("category"),
                include_text=action.get("include_text", True),
                search_type=action.get("search_type", "auto")
            )

        elif action_type == "find_similar":
            url = action.get("url") or kwargs.get("url")
            if not url:
                return {"status": "error", "output": "URL is required for find_similar."}
            return self._find_similar(
                url=url,
                num_results=action.get("num_results", 5)
            )

        elif action_type == "get_contents":
            urls = action.get("urls") or kwargs.get("urls")
            if not urls or not isinstance(urls, list):
                return {"status": "error", "output": "A list of URLs is required for get_contents."}
            return self._get_contents(urls)

        else:
            return {
                "status": "error",
                "output": f"Unknown action type: {action_type}. "
                          f"Available types: search, find_similar, get_contents."
            }


def get_tools():
    """Entry point for plugin discovery."""
    logger.info("Initializing Exa Search Plugin tools.")
    try:
        tool = ExaSearchTool()
        logger.info(f"ExaSearchTool created: {tool}")
        return [tool]
    except Exception as e:
        logger.error(f"Error creating ExaSearchTool: {e}", exc_info=True)
        return []
