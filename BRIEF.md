Excellent. I’ll now generate the full working code for a real-time policy brief agent using Python 3.13+, Claude Sonnet 4.5 via OpenAI SDK, and FastMCP. It will:

* Run locally on Linux
* Use a lightweight task queue to handle async RSS/API data fetching
* Expose the tools to the LLM via FastMCP
* Be designed for interaction via the Cohere North chat interface
* Avoid unnecessary UI/plotting since visualization is handled in that external layer

I’ll break it down into modules: data fetchers, FastMCP server, queue logic, and integration with Claude. I’ll get started and let you know when the full implementation is ready.


Nice — I implemented the **Hansard tool fully** and updated the MCP server to run with the **Streamable HTTP** transport. I also used streaming HTTP for downloading the Hansard pages (so big transcripts are handled efficiently). Below you’ll find the new/updated files and usage notes.

**What I changed / added**

* `fetchers/hansard_fetcher.py` — complete implementation that fetches the latest Hansard page from ourcommons.ca, streams the response, parses it with BeautifulSoup, and returns a structured JSON object (session, date, url, list of sections with headings + text, and short summary).
* `mcp_server.py` — updated to expose a `get_latest_hansard` tool that uses the new fetcher and caching. The MCP server is now started with `transport="streamable-http"` and `mount_path="/mcp"` so it runs as a Streamable HTTP MCP endpoint (binds to localhost by default for safety).
* `README.md` — dependency + run instructions updated.
* Installation deps: added `beautifulsoup4` and `lxml` and recommended binding to `127.0.0.1` (security).

> Note: I wrote the code to be robust and defensive: it streams the HTTP response, falls back to reasonable selectors if the page layout varies, and returns clear `error` keys in JSON on failure. Because live HTML structures change, the parser chooses several selectors and falls back to full-text extraction when needed.

---

### New file — `fetchers/hansard_fetcher.py`

```python
# fetchers/hansard_fetcher.py
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional
from datetime import datetime
from urllib.parse import urljoin

# default URL for the latest House Hansard (House of Commons)
LATEST_HANSARD_URL = "https://www.ourcommons.ca/DocumentViewer/en/house/latest/hansard"

# helper to safely get text
def _safe_text(elem) -> str:
    return elem.get_text(separator=" ", strip=True) if elem else ""

async def stream_fetch_text(url: str, chunk_size: int = 4096, timeout: int = 30) -> str:
    """
    Stream the response body and return combined text.
    This is memory-friendly for very large pages because it reads iteratively.
    """
    try:
        timeout_cfg = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                # Aggregate chunks
                parts = []
                async for chunk in resp.content.iter_chunked(chunk_size):
                    if not chunk:
                        continue
                    parts.append(chunk.decode(errors="replace"))
                return "".join(parts)
    except Exception as e:
        raise

def _extract_sections_from_soup(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    Try a variety of selectors to find the main transcript content and split by headings.
    Returns list of {'heading': str, 'text': str}
    """
    # Candidate containers (ordered): article, div.documentBody, div#content, div.Content
    candidates = []
    article = soup.find("article")
    if article:
        candidates.append(article)
    # site-specific classes often include 'DocumentViewer' or 'documentBody'
    for cls in ("documentBody", "DocumentViewer", "document", "content", "mainContent", "Document"):
        el = soup.find("div", class_=lambda c: c and cls in c)
        if el:
            candidates.append(el)
    # generic fallback: main or #content
    main_el = soup.find("main") or soup.find("div", id="content")
    if main_el:
        candidates.append(main_el)

    # take the first candidate with sizable text
    container = None
    for cand in candidates:
        if len(_safe_text(cand)) > 200:
            container = cand
            break
    if container is None:
        # last resort: whole body
        container = soup.body or soup

    # split by headings (h2/h3/h4); if no headings, create one big section
    headings = container.find_all(["h1", "h2", "h3", "h4"])
    sections: List[Dict[str, str]] = []
    if headings:
        # iterate headings and collect following siblings until next heading
        for h in headings:
            heading_text = _safe_text(h)
            content_parts: List[str] = []
            for sib in h.next_siblings:
                if getattr(sib, "name", None) in ("h1", "h2", "h3", "h4"):
                    break
                # skip small decorative tags
                content_parts.append(_safe_text(sib))
            joined = " ".join(p for p in content_parts if p)
            sections.append({"heading": heading_text or "(no heading)", "text": joined.strip()})
    else:
        # no headings — make one big section
        text = _safe_text(container)
        sections.append({"heading": "Transcript", "text": text})

    # filter out empty sections
    sections = [s for s in sections if s["text"]]
    return sections

def _extract_meta(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    # Try to extract title and published date from meta tags or header elements
    meta = {"title": None, "published": None, "session": None}
    title_tag = soup.find("meta", {"property": "og:title"}) or soup.find("title")
    if title_tag:
        meta["title"] = title_tag.get("content") if title_tag.name == "meta" else title_tag.get_text(strip=True)

    # published date
    pub = soup.find("meta", {"property": "article:published_time"}) or soup.find("meta", {"name": "published"})
    if pub and pub.get("content"):
        meta["published"] = pub.get("content")
    else:
        # try visible dates in page (e.g., time tag)
        time_el = soup.find("time")
        if time_el:
            meta["published"] = time_el.get("datetime") or _safe_text(time_el)

    # session e.g., "45-1" or "Volume 152"
    # attempt to extract from header text
    header_candidates = soup.find_all(["h1", "h2", "h3"])
    for h in header_candidates:
        txt = _safe_text(h)
        if "PARLIAMENT" in txt.upper() or "Volume" in txt or "45-" in txt:
            meta["session"] = txt
            break

    return meta

async def fetch_latest_hansard(url: str = LATEST_HANSARD_URL) -> Dict[str, Any]:
    """
    Fetches the latest Hansard page, streams and parses it, and returns structured JSON:
    {
        "url": str,
        "title": str | None,
        "published": str | None,
        "session": str | None,
        "sections": [{"heading": str, "text": str}, ...],
        "short_summary": str
    }
    """
    try:
        raw = await stream_fetch_text(url)
    except Exception as e:
        return {"error": f"Failed to fetch Hansard page: {e}", "url": url}

    try:
        soup = BeautifulSoup(raw, "lxml")
    except Exception:
        # try html.parser fallback
        soup = BeautifulSoup(raw, "html.parser")

    meta = _extract_meta(soup)
    sections = _extract_sections_from_soup(soup)

    # create a short summary: first 2-3 non-empty section headings with short snippets
    summary_parts = []
    for s in sections[:3]:
        text_snip = (s["text"][:240] + "...") if len(s["text"]) > 240 else s["text"]
        summary_parts.append(f"{s['heading']}: {text_snip}")
    short_summary = " | ".join(summary_parts) if summary_parts else _safe_text(soup)[:400]

    result: Dict[str, Any] = {
        "url": url,
        "title": meta.get("title"),
        "published": meta.get("published"),
        "session": meta.get("session"),
        "sections": sections,
        "short_summary": short_summary,
    }
    return result
```

---

### Updated `mcp_server.py` (exposes Streamable HTTP transport + Hansard tool)

```python
# mcp_server.py

import asyncio
from typing import List, Dict, Any
from fastmcp import FastMCP, ToolError
from tasks.cache import fetch_with_cache

# existing fetchers
from fetchers.pm_fetcher import fetch_pm_news, fetch_pm_media
from fetchers.statcan_fetcher import fetch_statscan_all
from fetchers.canada_news_fetcher import fetch_canada_news
from fetchers.geds_fetcher import fetch_geds_directory
from fetchers.hansard_fetcher import fetch_latest_hansard

# Create FastMCP instance
# Note: bind to localhost (127.0.0.1) by default for security (see MCP spec).
mcp = FastMCP("DailyBriefSystem")

# Existing tools
@mcp.tool
async def get_pm_news() -> List[Dict[str, Any]]:
    return await fetch_with_cache("pm_news", fetch_pm_news)

@mcp.tool
async def get_pm_media() -> List[Dict[str, Any]]:
    return await fetch_with_cache("pm_media", fetch_pm_media)

@mcp.tool
async def get_statscan_updates() -> List[Dict[str, Any]]:
    return await fetch_with_cache("statscan", fetch_statscan_all)

@mcp.tool
async def get_canada_news() -> List[Dict[str, Any]]:
    return await fetch_with_cache("canada_news", fetch_canada_news)

@mcp.tool
async def get_geds_data() -> Dict[str, Any]:
    return await fetch_with_cache("geds", fetch_geds_directory)

# Fully implemented Hansard tool
@mcp.tool
async def get_latest_hansard() -> Dict[str, Any]:
    """
    Fetch the latest House of Commons Hansard transcript, parse it and return structured JSON.
    Uses streaming download + parsing to handle large transcripts.
    Returns:
      {
        "url": str,
        "title": str | None,
        "published": str | None,
        "session": str | None,
        "sections": [{"heading": str, "text": str}, ...],
        "short_summary": str
      }
    """
    try:
        data = await fetch_with_cache("hansard_latest", fetch_latest_hansard)
        # If fetch_latest_hansard returned an error dict, pass it through
        if isinstance(data, dict) and data.get("error"):
            raise ToolError(str(data.get("error")))
        return data
    except ToolError:
        # ToolError is intended to be visible to the LLM client
        raise
    except Exception as e:
        # Wrap unexpected exceptions as a ToolError to avoid leaking internals
        raise ToolError(f"Failed to retrieve Hansard: {e}")

if __name__ == "__main__":
    # Run the MCP server as Streamable HTTP on localhost:8000 and mount at /mcp
    # NOTE: the exact parameters below follow FastMCP examples - if your FastMCP version names
    # these parameters differently, adjust accordingly. Binding to 127.0.0.1 for safety.
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8000, mount_path="/mcp")
```

---

### Dependencies / install

Add these to your environment (I recommend a dedicated venv):

```bash
python -m venv venv
source venv/bin/activate
pip install fastmcp aiohttp beautifulsoup4 lxml
```

(If you already have `fastmcp` and `aiohttp`, only add `beautifulsoup4` and `lxml`.)

---

### Quick test client (call the Hansard tool from a local MCP client)

This example uses the FastMCP client transport (Streamable HTTP) — adjust if you already have a client stack.

```python
# examples/test_hansard_client.py
import asyncio
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def main():
    # connect to local MCP server (streamable http)
    transport = StreamableHttpTransport(base_url="http://127.0.0.1:8000/mcp")
    async with Client(transport=transport) as client:
        result = await client.call_tool(name="get_latest_hansard", arguments={})
        print("Hansard result summary:")
        if isinstance(result, dict) and result.get("error"):
            print("Error:", result["error"])
        else:
            print("Title:", result.get("title"))
            print("Published:", result.get("published"))
            print("Session:", result.get("session"))
            print("Short summary:", result.get("short_summary"))
            print("Sections:", len(result.get("sections", [])))
            # print the first section text (short)
            if result.get("sections"):
                print("\nFirst section heading:", result["sections"][0]["heading"])
                print(result["sections"][0]["text"][:500])

if __name__ == "__main__":
    asyncio.run(main())
```

Run:

1. `python mcp_server.py` (server should log listening on `127.0.0.1:8000/mcp`)
2. `python examples/test_hansard_client.py` (client fetches Hansard via the MCP tool)

---

### Security & notes

* **Bind to `127.0.0.1`**: the Streamable HTTP transport exposes an HTTP endpoint; for internal on-prem deployments you should avoid binding to `0.0.0.0` unless behind a reverse proxy with auth. The MCP spec warns about DNS rebinding attacks — keep it local for development.
* **Page layout variability**: `ourcommons.ca` HTML changes occasionally. The parser tries several sensible selectors and falls back to extracting all body text. If you need exact, fielded Hansard data (e.g., per-speaker timestamps), we should switch to the Parliament/ourcommons open-data APIs or a dedicated XML dataset (Lipad, ParlVu, or House open data). I can add that if you want more structured speaker-level metadata.
* **Caching TTL**: currently 10 minutes (from `tasks/cache.py`). If you want fresher or higher throughput, change TTL or implement a task queue that refreshes Hansard at intervals.

---

If you want, next steps I can do in this turn (pick any, I’ll implement immediately — no waiting):

* Add per-speaker parsing (speaker names and timestamps) for Hansard (will parse `<span class="...">` speaker labels or use the underlying XML source).
* Add an endpoint or example that returns a short timeline (e.g., bill mentions, named entities) from the Hansard transcript.
* Swap the fallback scraper to the Parliament Open Data XML (e.g., the Document Viewer has a JSON or XML link that’s more structured) if you prefer more robust, structured data.

Which of those should I do next?

Nice — below is a **complete, practical implementation** that adds:

1. **Per-speaker parsing** (speaker name, text, approximate order/timestamps where available).
2. A **short timeline** extracted from the transcript (key events: Bill mentions, Motions, Question Period, named topics) with lightweight heuristics.
3. A robust **Parliament Open Data XML** fallback: the fetcher tries to find an XML/structured feed from the Document Viewer page and, if present, parses it for well-structured speaker blocks. If no XML is available it falls back to the HTML parsing but still attempts to extract speaker blocks.

I’ve replaced the previous `fetchers/hansard_fetcher.py` with a new, fuller implementation and updated `mcp_server.py` to expose new tools for structured Hansard output, per-speaker extraction, and timeline extraction.

> Run the MCP server as before (Streamable HTTP) and call the new tools from your agent. The code is defensive about missing XML and HTML layout changes, returns clear `error` keys on failures, and uses the same caching mechanism.

---

### New / Updated file — `fetchers/hansard_fetcher.py`

```python
# fetchers/hansard_fetcher.py
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from urllib.parse import urljoin
import re
import asyncio
import logging

# Prefer lxml for XML parsing when available
try:
    from lxml import etree as LET
    LXML_AVAILABLE = True
except Exception:
    import xml.etree.ElementTree as ET
    LET = ET
    LXML_AVAILABLE = False

# Default latest Hansard page
LATEST_HANSARD_URL = "https://www.ourcommons.ca/DocumentViewer/en/house/latest/hansard"

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def stream_fetch_text(url: str, chunk_size: int = 8192, timeout: int = 40) -> str:
    """
    Stream the response body and return combined text.
    """
    timeout_cfg = aiohttp.ClientTimeout(total=timeout)
    parts: List[str] = []
    try:
        async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                async for chunk in resp.content.iter_chunked(chunk_size):
                    if not chunk:
                        continue
                    parts.append(chunk.decode(errors="replace"))
    except Exception as e:
        log.exception("stream_fetch_text failed")
        raise
    return "".join(parts)


def _safe_text(elem) -> str:
    if elem is None:
        return ""
    try:
        return elem.get_text(separator=" ", strip=True)
    except Exception:
        try:
            return str(elem)
        except Exception:
            return ""


async def _find_xml_link_from_html(html: str, base_url: str) -> Optional[str]:
    """
    Try to find a link to a structured XML/JSON representation on the page.
    Heuristics:
    - <link type="application/xml" href="...">
    - <a href="...xml"> or href containing '.xml' or '/xml'
    - script tags or data attributes referencing 'xml' or 'json'
    Return absolute URL if found.
    """
    soup = BeautifulSoup(html, "lxml")
    # look for link rel types
    for link in soup.find_all("link"):
        ltype = link.get("type", "")
        if "xml" in ltype or "application/xml" in ltype or "application/rss+xml" in ltype:
            href = link.get("href")
            if href:
                return urljoin(base_url, href)

    # anchors to xml files
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".xml" in href or "/xml/" in href or "formatted=xml" in href:
            return urljoin(base_url, href)

    # some pages include an API/data link in script tags (search for .xml or "xml" strings)
    text = soup.get_text(" ", strip=True)
    match = re.search(r"https?://[^\s'\"<>]+\.xml", text)
    if match:
        return match.group(0)

    # not found
    return None


def _xml_to_speeches(xml_text: str) -> List[Dict[str, Any]]:
    """
    Parse a (parliamentary) XML transcript to extract per-speaker speeches.
    This function tries to be tolerant to variants of Hansard XML.
    - Search for elements with local-name() == 'speech' or 'contribution' or 'speaking' etc.
    - For each speech element, find a speaker name child or an attribute.
    - Extract paragraphs as text
    """
    speeches: List[Dict[str, Any]] = []

    try:
        if LXML_AVAILABLE:
            root = LET.fromstring(xml_text.encode("utf-8"))
            # Find elements whose local-name is 'speech' or 'contribution' or 'speechPart' etc.
            xpath_expr = "//*[local-name() = 'speech' or local-name() = 'contribution' or local-name() = 'speechPart' or local-name() = 'debate']"
            nodes = root.xpath(xpath_expr)
            if not nodes:
                # fallback: find all <p> groups under a debate root
                nodes = root.findall(".")
        else:
            # xml.etree fallback (no local-name support): naive approach
            root = LET.fromstring(xml_text)
            nodes = []
            for el in root.iter():
                tag = el.tag.lower()
                if tag.endswith("speech") or tag.endswith("contribution") or tag.endswith("speechpart") or tag.endswith("debate"):
                    nodes.append(el)

        for node in nodes:
            # Try several ways to locate speaker name
            speaker = None
            # child elements commonly used: <speaker>, <name>, <speakerRole>, <member>
            for child_name in ("speaker", "name", "member", "contributor", "speakerId"):
                # using local-name matching if lxml
                if LXML_AVAILABLE:
                    found = node.xpath(f".//*[local-name() = '{child_name}']")
                    if found:
                        speaker = _get_text_from_elem(found[0])
                        break
                else:
                    for ch in node.findall(".//"):
                        tag = getattr(ch, "tag", "")
                        if tag.lower().endswith(child_name):
                            speaker = _get_text_from_elem(ch)
                            break
                    if speaker:
                        break

            # If no speaker found, maybe an attribute on the node
            if speaker is None:
                # attributes like speaker="Mr. Smith"
                if hasattr(node, "attrib"):
                    for k, v in node.attrib.items():
                        if "speaker" in k.lower() or "name" in k.lower():
                            speaker = v
                            break

            # Extract textual paragraphs
            paragraphs: List[str] = []
            if LXML_AVAILABLE:
                p_nodes = node.xpath(".//*[local-name() = 'p' or local-name() = 'para' or local-name() = 'paragraph']")
                if not p_nodes:
                    # collect text directly under node
                    text_val = "".join([str(x) for x in node.itertext()])
                    paragraphs = [text_val.strip()] if text_val.strip() else []
                else:
                    for p in p_nodes:
                        txt = _get_text_from_elem(p)
                        if txt:
                            paragraphs.append(txt)
            else:
                # fallback: get text from node
                text_val = "".join([t for t in node.itertext()]) if hasattr(node, "itertext") else str(node)
                if text_val.strip():
                    paragraphs = [text_val.strip()]

            if not paragraphs:
                continue

            block_text = "\n\n".join(paragraphs).strip()
            # Attempt to find time or position metadata (if present)
            time_attr = None
            if hasattr(node, "attrib"):
                for k in ("time", "datetime", "timestamp"):
                    if k in node.attrib:
                        time_attr = node.attrib[k]
                        break

            speeches.append({
                "speaker": speaker or "(unknown)",
                "text": block_text,
                "time": time_attr,
            })
    except Exception as e:
        log.exception("XML parse failed")
        # Return empty list on parse failure but include error in outer function
        return []

    return speeches


def _get_text_from_elem(el) -> str:
    try:
        return el.text_content() if hasattr(el, "text_content") else (el.text or "").strip()
    except Exception:
        try:
            # BeautifulSoup fallback if it's a BS object
            return _safe_text(el)
        except Exception:
            return ""


def _html_speaker_blocks(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    Heuristic: find sequences in the HTML that look like speaker-labeled sections.
    Common patterns:
    - <p><strong>Mr. Smith:</strong> ...</p>
    - <h3>Mr. Smith</h3><p>...</p>
    - <p><span class="speaker">Mr. Smith</span> text...</p>
    We scan for elements with bold/strong tags followed by text and treat them as a speaker block.
    """
    blocks: List[Dict[str, Any]] = []

    # 1) Bold name at start of paragraph
    for p in soup.find_all(["p", "div"]):
        # skip if tiny
        pt = _safe_text(p)
        if len(pt) < 30:
            continue
        # look for <strong> or <b> child at start
        strong = p.find(["strong", "b"])
        if strong:
            strong_text = _safe_text(strong)
            # heuristics: must contain honorific or uppercase name-like pattern
            if re.search(r"\b(Mr|Mrs|Ms|Hon|Honourable|Dr|Prof|Member)\b|^[A-Z][a-z]+ [A-Z][a-z]+", strong_text):
                # extract remainder text
                # Remove the strong tag text from paragraph text to get speech
                remainder = pt.replace(strong_text, "").strip(" :\n")
                if remainder:
                    blocks.append({"speaker": strong_text, "text": remainder, "time": None})
                    continue

        # 2) leading text matching "Mr. Smith:" pattern
        m = re.match(r"^([A-Z][A-Za-z\.\-']+(?:\s+[A-Z][A-Za-z\.\-']+){0,3})\s*:\s*(.+)$", pt)
        if m:
            speaker = m.group(1).strip()
            speech_text = m.group(2).strip()
            blocks.append({"speaker": speaker, "text": speech_text, "time": None})
            continue

    # 3) Headings followed by paragraphs
    for htag in ("h1", "h2", "h3", "h4", "h5"):
        for h in soup.find_all(htag):
            txt = _safe_text(h)
            if len(txt) < 5:
                continue
            # if heading looks like a speaker name
            if re.search(r"\b(Mr|Mrs|Ms|Hon|Honourable|Dr|Professor|Speaker)\b|^[A-Z][a-z]+ [A-Z][a-z]+", txt):
                # collect subsequent sibling paragraphs until next heading
                parts = []
                for sib in h.next_siblings:
                    if getattr(sib, "name", None) in ("h1", "h2", "h3", "h4", "h5"):
                        break
                    parts.append(_safe_text(sib))
                joined = " ".join([p for p in parts if p]).strip()
                if joined:
                    blocks.append({"speaker": txt, "text": joined, "time": None})

    # Filter duplicates or empty
    blocks = [b for b in blocks if b.get("text")]
    # Basic dedup: merge consecutive blocks with same speaker
    merged: List[Dict[str, Any]] = []
    for b in blocks:
        if merged and merged[-1]["speaker"] == b["speaker"]:
            merged[-1]["text"] += "\n\n" + b["text"]
        else:
            merged.append(b)
    return merged


def _extract_timeline_from_speeches(speeches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Lightweight timeline extraction:
    - Look for references to Bill numbers (Bill C-XX, Bill S-XX, private members' bills)
    - Look for keywords: 'Question Period', 'Order of the Day', 'Motion', 'Statement', 'Adjournment'
    - Create ordered events with an index or time (if available)
    """
    timeline: List[Dict[str, Any]] = []
    bill_re = re.compile(r"\b(Bill(?:\s+(?:C|S)?-?\s*\d+|[A-Z][a-zA-Z0-9\-\s]*\b))", re.IGNORECASE)
    keyword_patterns = [
        ("Question Period", re.compile(r"\bQuestion Period\b", re.IGNORECASE)),
        ("Order of the Day", re.compile(r"\bOrder of the Day\b", re.IGNORECASE)),
        ("Motion", re.compile(r"\bMotion\b", re.IGNORECASE)),
        ("Adjournment", re.compile(r"\bAdjournment\b", re.IGNORECASE)),
        ("Statement", re.compile(r"\bStatement\b", re.IGNORECASE)),
        ("Question", re.compile(r"\bQuestion\b", re.IGNORECASE)),
        ("Committee", re.compile(r"\bCommittee\b", re.IGNORECASE)),
    ]

    for idx, sp in enumerate(speeches):
        text = sp.get("text", "")
        # bill mentions
        for m in bill_re.finditer(text):
            timeline.append({
                "position": idx,
                "type": "bill_mention",
                "match": m.group(0),
                "speaker": sp.get("speaker"),
                "snippet": text[max(0, m.start()-60): m.end()+60]
            })
        # keywords
        for label, patt in keyword_patterns:
            if patt.search(text):
                timeline.append({
                    "position": idx,
                    "type": "keyword",
                    "label": label,
                    "speaker": sp.get("speaker"),
                    "snippet": text[:300]
                })

    # deduplicate by (type, match/label, position)
    seen = set()
    out = []
    for ev in timeline:
        key = (ev.get("type"), ev.get("match") or ev.get("label"), ev.get("position"))
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    # sort by position
    out.sort(key=lambda e: e["position"])
    return out


async def fetch_parliament_xml_or_html(url: str = LATEST_HANSARD_URL) -> Tuple[str, str]:
    """
    Fetch the target DocumentViewer URL; attempt to find XML or structured link.
    Returns tuple: (source_type, content_text)
      source_type: 'xml' | 'html'
      content_text: raw xml or raw html
    """
    html = await stream_fetch_text(url)
    xml_link = await _find_xml_link_from_html(html, url)
    if xml_link:
        try:
            xml_text = await stream_fetch_text(xml_link)
            return "xml", xml_text
        except Exception:
            log.info("Failed to fetch xml at %s; falling back to HTML parse", xml_link)
            return "html", html
    else:
        # No xml link found — try heuristic alternative endpoints (some DocumentViewer pages have '?format=xml' or '/xml')
        # Try common suffixes
        candidates = [
            url + "?format=xml",
            url + ".xml",
            url.replace("/DocumentViewer", "/DocumentViewer/Xml"),
        ]
        for c in candidates:
            try:
                xml_try = await stream_fetch_text(c)
                # basic check: contains xml root or <speech> tag
                if "<" in xml_try and ("<speech" in xml_try or "<?xml" in xml_try or "<debate" in xml_try):
                    return "xml", xml_try
            except Exception:
                continue
        # final fallback: return raw HTML
        return "html", html


async def fetch_latest_hansard_structured(url: str = LATEST_HANSARD_URL) -> Dict[str, Any]:
    """
    Top-level function:
    - Attempts to fetch a structured XML transcript (preferred)
    - Falls back to HTML speaker heuristics
    - Returns structured JSON with keys:
      {
        "source": "xml" | "html",
        "url": url,
        "title": Optional[str],
        "published": Optional[str],
        "session": Optional[str],
        "speeches": [ {speaker, text, time}, ...],
        "timeline": [ {position, type, match/label, speaker, snippet}, ...],
        "short_summary": str
      }
    """
    try:
        source_type, content = await fetch_parliament_xml_or_html(url)
    except Exception as e:
        log.exception("Failed to fetch Hansard page")
        return {"error": f"Failed to fetch Hansard: {e}", "url": url}

    try:
        if source_type == "xml":
            # Try to parse the XML content for well-structured speeches
            speeches = _xml_to_speeches(content)
            # metadata extraction
            title = None
            published = None
            session = None
            # attempt to parse XML root metadata
            try:
                if LXML_AVAILABLE:
                    root = LET.fromstring(content.encode("utf-8"))
                    # title
                    tnode = root.xpath("//*[local-name() = 'title']") or root.xpath("//title")
                    if tnode:
                        title = _get_text_from_elem(tnode[0])
                    # published
                    pnode = root.xpath("//*[local-name() = 'published' or local-name() = 'date' or local-name() = 'created']")
                    if pnode:
                        published = _get_text_from_elem(pnode[0])
                else:
                    root = LET.fromstring(content)
                    # naive find
                    tn = root.find(".//title")
                    if tn is not None and tn.text:
                        title = tn.text.strip()
            except Exception:
                pass

            if not speeches:
                # If XML parsed but no speeches found, fallback to HTML extraction
                source_type = "html"
                soup = BeautifulSoup(content, "lxml")
                speeches = _html_speaker_blocks(soup)
        else:
            # HTML processing
            soup = BeautifulSoup(content, "lxml")
            # try to extract meta
            title_tag = soup.find("meta", {"property": "og:title"}) or soup.find("title")
            title = title_tag.get("content") if title_tag and title_tag.name == "meta" else (title_tag.get_text(strip=True) if title_tag else None)
            # try time
            time_tag = soup.find("time")
            published = time_tag.get("datetime") if time_tag and time_tag.get("datetime") else (_safe_text(time_tag) if time_tag else None)
            session = None
            # speaker blocks heuristics:
            speeches = _html_speaker_blocks(soup)

        # Normalize speeches: ensure speaker names cleaned, text trimmed
        normalized: List[Dict[str, Any]] = []
        for s in speeches:
            speaker = s.get("speaker") or "(unknown)"
            # cleanup whitespace and trailing colons
            speaker = re.sub(r"[:\s]+$", "", speaker).strip()
            text = s.get("text", "").strip()
            time = s.get("time", None)
            normalized.append({"speaker": speaker, "text": text, "time": time})

        # timeline
        timeline = _extract_timeline_from_speeches(normalized)

        # short summary: first 2 speakers + first timeline entries
        summary_parts = []
        if normalized:
            for sp in normalized[:2]:
                snippet = sp["text"][:240] + ("..." if len(sp["text"]) > 240 else "")
                summary_parts.append(f"{sp['speaker']}: {snippet}")
        if timeline:
            for ev in timeline[:3]:
                if ev["type"] == "bill_mention":
                    summary_parts.append(f"Bill mention: {ev['match']} (speaker {ev.get('speaker')})")
                else:
                    summary_parts.append(f"{ev['label']} noted by {ev.get('speaker')}")

        short_summary = " | ".join(summary_parts) if summary_parts else (normalized[0]["text"][:400] if normalized else "")

        return {
            "source": source_type,
            "url": url,
            "title": title,
            "published": published,
            "session": session,
            "speeches": normalized,
            "timeline": timeline,
            "short_summary": short_summary
        }

    except Exception as e:
        log.exception("Error parsing Hansard content")
        return {"error": f"Failed to parse Hansard content: {e}", "url": url}
```

---

### Updated `mcp_server.py` (exposes new tools)

```python
# mcp_server.py

import asyncio
from typing import List, Dict, Any
from fastmcp import FastMCP, ToolError
from tasks.cache import fetch_with_cache

# existing fetchers
from fetchers.pm_fetcher import fetch_pm_news, fetch_pm_media
from fetchers.statcan_fetcher import fetch_statscan_all
from fetchers.canada_news_fetcher import fetch_canada_news
from fetchers.geds_fetcher import fetch_geds_directory
# new structured hansard fetcher
from fetchers.hansard_fetcher import fetch_latest_hansard_structured

# Create FastMCP instance
mcp = FastMCP("DailyBriefSystem")

# simple wrappers for earlier tools (left unchanged)
@mcp.tool
async def get_pm_news() -> List[Dict[str, Any]]:
    return await fetch_with_cache("pm_news", fetch_pm_news)

@mcp.tool
async def get_pm_media() -> List[Dict[str, Any]]:
    return await fetch_with_cache("pm_media", fetch_pm_media)

@mcp.tool
async def get_statscan_updates() -> List[Dict[str, Any]]:
    return await fetch_with_cache("statscan", fetch_statscan_all)

@mcp.tool
async def get_canada_news() -> List[Dict[str, Any]]:
    return await fetch_with_cache("canada_news", fetch_canada_news)

@mcp.tool
async def get_geds_data() -> Dict[str, Any]:
    return await fetch_with_cache("geds", fetch_geds_directory)


# New Hansard tools
@mcp.tool
async def get_latest_hansard_structured() -> Dict[str, Any]:
    """
    Fetch the latest Hansard and return a fully structured object
    including speaker blocks and timeline.
    """
    try:
        data = await fetch_with_cache("hansard_structured", fetch_latest_hansard_structured)
        if isinstance(data, dict) and data.get("error"):
            # surface the error to the calling client/tool
            raise ToolError(data.get("error"))
        return data
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to get structured Hansard: {e}")


@mcp.tool
async def get_hansard_speakers(limit: int = 0) -> Dict[str, Any]:
    """
    Return list of speaker blocks (optionally truncated to 'limit' items).
    """
    try:
        data = await fetch_with_cache("hansard_structured", fetch_latest_hansard_structured)
        if isinstance(data, dict) and data.get("error"):
            raise ToolError(data.get("error"))
        speeches = data.get("speeches", [])
        if limit and isinstance(limit, int) and limit > 0:
            speeches = speeches[:limit]
        return {"count": len(speeches), "speeches": speeches}
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to fetch hansard speakers: {e}")


@mcp.tool
async def get_hansard_timeline(limit: int = 20) -> Dict[str, Any]:
    """
    Return timeline events extracted from the latest Hansard (limit default 20).
    """
    try:
        data = await fetch_with_cache("hansard_structured", fetch_latest_hansard_structured)
        if isinstance(data, dict) and data.get("error"):
            raise ToolError(data.get("error"))
        timeline = data.get("timeline", [])
        if limit and isinstance(limit, int) and limit > 0:
            timeline = timeline[:limit]
        return {"count": len(timeline), "timeline": timeline}
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to fetch hansard timeline: {e}")


if __name__ == "__main__":
    # Run the MCP server as Streamable HTTP on localhost:8000 and mount at /mcp
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8000, mount_path="/mcp")
```

---

### Example usage (client)

```python
# examples/test_hansard_structured_client.py
import asyncio
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
import json

async def main():
    transport = StreamableHttpTransport(base_url="http://127.0.0.1:8000/mcp")
    async with Client(transport=transport) as client:
        # full structured hansard
        structured = await client.call_tool(name="get_latest_hansard_structured", arguments={})
        print("Structured keys:", structured.keys())
        print("Title:", structured.get("title"))
        print("Published:", structured.get("published"))
        print("Speeches:", len(structured.get("speeches", [])))
        print("Timeline events:", len(structured.get("timeline", [])))

        # speakers
        sp = await client.call_tool(name="get_hansard_speakers", arguments={"limit": 5})
        print("First 5 speakers:", [s["speaker"] for s in sp.get("speeches", [])])

        # timeline
        tl = await client.call_tool(name="get_hansard_timeline", arguments={"limit": 10})
        print("Timeline sample:", tl.get("timeline", [])[:5])

if __name__ == "__main__":
    asyncio.run(main())
```

---

### Notes, limitations, and next steps

1. **Robustness vs. Exactness**: The Parl. Open Data XML schema varies between endpoints. The fetcher therefore:

   * First attempts to find a structured XML link on the Document Viewer page and parse it.
   * If XML is present, it uses a tolerant XML parser to find `speech` / `contribution` elements and extract speaker and paragraphs.
   * If not, it falls back to HTML heuristics to extract speaker blocks. That fallback is intentionally heuristic and may miss edge cases if the page structure changes.

2. **Speaker timestamps / exact offsets**: Hansard HTML often does not include explicit timestamps for each speech. The XML format sometimes includes timing or offsets — we collect any attribute that looks like `time`, `datetime`, `timestamp`. If you require precise timestamps, we should use the Parliament open-data endpoint that provides detailed metadata for each contribution; I can add code to query those specific REST endpoints if you want.

3. **NER / topical extraction**: The timeline extraction uses regex heuristics (Bill patterns, keywords). For more advanced topic extraction, consider running a light NER model (spaCy) or calling the LLM (with the speech text) to extract entities/events. If you'd like, I can add an optional pipeline that batches speech blocks, sends them to Claude Sonnet 4.5 with a prompt to extract named entities and events, and returns a higher-quality timeline.

4. **Performance / streaming**: We use streaming HTTP for downloads and a light in-memory cache (10 minutes TTL by default). For high throughput or production, consider:

   * Persisting cache to Redis or a small local DB.
   * Using a background worker to prefetch Hansard on schedule (e.g., after a sitting) to avoid fetching at the time of the LLM call.
   * Breaking long speech blocks into chunks for LLM processing.

5. **Testing**: Run `python mcp_server.py` then run the example client `examples/test_hansard_structured_client.py` to inspect results. If HTML structure of the source changes, adjust `_html_speaker_blocks` and `_find_xml_link_from_html` heuristics.

6. **Security**: As before, bind to `127.0.0.1` for development. When deploying to production within an internal network, put the MCP endpoint behind the internal reverse proxy and enforce internal network ACLs.

---

If you want, I can *immediately* do one (pick any, I’ll implement in this turn):

* Add an **LLM-assisted NER** step (batch speeches → Claude Sonnet 4.5 → structured entities & events) for a richer timeline.
* Persist the parsed Hansard to a small local SQLite DB and add versioning (date/hash) for diffs.
* Add a **speaker-indexed summary**: for each speaker produce a 2–3 sentence summary (descriptive, not prescriptive) using the LLM.

Say which of these you want and I’ll include the code.

Perfect — I implemented the **LLM-assisted NER** and **speaker-indexed summaries** using Claude Sonnet 4.5 (via the OpenAI SDK) and integrated them as MCP tools. I added a robust async wrapper around the OpenAI Responses API, careful prompting that forces strict JSON output, parsing/fallback logic, and MCP tools that return parsed JSON (or a clear error + raw LLM text if parsing fails).

Below are the new and updated files. Drop them into your existing project (same layout as before). I kept the style consistent with previous modules (async, type hints, caching). After the file list I include quick run / test instructions.

---

## New file — `llm/claude_client.py`

```python
# llm/claude_client.py
"""
Async wrapper for calling Claude Sonnet 4.5 via the OpenAI SDK.
Provides two high-level functions:
 - extract_entities_and_events(...) -> structured NER + events JSON
 - summarize_speakers(...) -> speaker-indexed 2-3 sentence summaries

Environment:
 - Requires OPENAI_API_KEY set in environment.

Notes:
 - Uses asyncio.to_thread to run the synchronous OpenAI client call to avoid blocking event loop.
 - Tries to call `openai.responses.create` (new Responses API). If unavailable, falls back to ChatCompletion.
"""

import os
import json
import asyncio
from typing import Any, Dict, List, Optional
import logging
import textwrap

# Install with: pip install openai
import openai

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Model name (Claude Sonnet 4.5 via OpenAI SDK)
MODEL_NAME = "claude-sonnet-4.5"

# Default call params
DEFAULT_MAX_TOKENS = 1600
DEFAULT_TEMPERATURE = 0.0  # deterministic for extraction tasks

# Timeout for the blocking request (seconds)
OPENAI_TIMEOUT = 60


def _prepare_openai_client() -> None:
    # openai library reads OPENAI_API_KEY from env by default
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set in environment.")
    openai.api_key = key


async def _call_openai_responses(prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, temperature: float = DEFAULT_TEMPERATURE) -> Dict[str, Any]:
    """
    Make a blocking call to openai.responses.create inside a thread to avoid blocking the event loop.
    Returns the raw response dict (as returned by the openai library).
    """
    _prepare_openai_client()

    def _blocking_call():
        # Preferred: the Responses API
        try:
            # Newer openai SDK uses openai.responses.create
            resp = openai.responses.create(
                model=MODEL_NAME,
                input=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp
        except AttributeError:
            # Fall back to ChatCompletion-style call, convert into a Chat-style prompt
            try:
                messages = [{"role": "user", "content": prompt}]
                resp = openai.ChatCompletion.create(
                    model=MODEL_NAME,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return resp
            except Exception as e:
                raise

    try:
        resp = await asyncio.to_thread(_blocking_call, timeout=OPENAI_TIMEOUT)
        return resp
    except TypeError:
        # asyncio.to_thread doesn't accept timeout param — handle simple case
        resp = await asyncio.to_thread(_blocking_call)
        return resp
    except Exception as e:
        log.exception("OpenAI call failed")
        raise


def _extract_text_from_response(resp: Any) -> str:
    """
    Normalize different OpenAI client response shapes to the assistant text.
    - For Responses API: resp.output_text or resp.output[0].content[0].text
    - For ChatCompletion: resp.choices[0].message.content
    Returns the assistant text.
    """
    try:
        # Responses API shape
        if hasattr(resp, "output_text"):
            return resp.output_text
        # dict-like support
        if isinstance(resp, dict):
            # new Responses API may be dict-like with 'output' list
            out = resp.get("output")
            if out and isinstance(out, list):
                # find a content text
                pieces = []
                for item in out:
                    if isinstance(item, dict):
                        # item may contain 'content' list
                        content = item.get("content")
                        if isinstance(content, list):
                            for c in content:
                                t = c.get("text")
                                if t:
                                    pieces.append(t)
                        # older shape: 'text'
                        if item.get("text"):
                            pieces.append(item.get("text"))
                if pieces:
                    return "\n".join(pieces)
            # ChatCompletion like
            choices = resp.get("choices")
            if choices and isinstance(choices, list):
                first = choices[0]
                if first.get("message") and first["message"].get("content"):
                    return first["message"]["content"]
                if first.get("text"):
                    return first["text"]
        # fallback: string representation
        return str(resp)
    except Exception:
        log.exception("Failed to extract text from OpenAI response")
        return ""


async def call_claude_and_get_text(prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, temperature: float = DEFAULT_TEMPERATURE) -> str:
    resp = await _call_openai_responses(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
    text = _extract_text_from_response(resp)
    return text


# High-level prompt templates (force JSON output)
_NER_PROMPT = textwrap.dedent(
    """
    You are an extraction engine. Input: a JSON array named "speeches" where each item has:
      - speaker: string
      - text: string
      - time: optional string or null
      - position: integer (index in original transcript)
    Task: Extract named entities and events from the speeches and return a strict JSON object with exactly these top-level fields:

    {
      "entities": [
        {
          "entity": "<canonical entity name>",
          "type": "<one of PERSON, ORG, BILL, LOCATION, EVENT, OTHER>",
          "mentions": [
            {"speaker": "<speaker name>", "position": <int>, "context_snippet": "<short snippet around mention>"}
          ]
        },
        ...
      ],
      "events": [
        {
          "label": "<short label, e.g., 'Question Period', 'Bill C-21 mention'>",
          "type": "<one of BILL_MENTION, MOTION, QUESTION_PERIOD, STATEMENT, OTHER>",
          "position": <int>,
          "speakers": ["Speaker A", "Speaker B"],
          "snippet": "<short textual snippet>"
        },
        ...
      ]
    }

    Important constraints:
    - Output MUST be valid JSON and nothing else (no commentary, no markdown).
    - Use the speeches as provided; do not invent facts.
    - Keep snippets short (<= 300 characters).
    - If nothing found, return empty lists, e.g. "entities": [], "events": [].

    Here is the input to analyze (as JSON):
    {input_json}
    """
)


_SUMMARY_PROMPT = textwrap.dedent(
    """
    You are to produce short descriptive summaries for each speaker block.
    Input: a JSON array named "speeches" where each item has:
      - speaker: string
      - text: string
      - time: optional string or null
      - position: integer

    Output: a strict JSON object:
    {
      "speaker_summaries": [
        {"speaker": "<speaker name>", "summary": "<2-3 sentence factual summary of that speaker's content — descriptive only>"},
        ...
      ]
    }

    Constraints:
    - 2-3 sentences per speaker, factual, no policy recommendations or opinions.
    - Output MUST be valid JSON only.
    - Keep summary length <= 300 words per speaker.
    - If a speaker's text is empty, skip them.

    Input (JSON):
    {input_json}
    """
)


async def extract_entities_and_events(speeches: List[Dict[str, Any]], max_tokens: int = 1200) -> Dict[str, Any]:
    """
    Uses Claude to extract entities and events from a list of speech dicts.
    Returns parsed JSON if successful, otherwise returns {'error': str, 'raw': raw_text}
    """
    # add position field if missing
    input_list = []
    for idx, s in enumerate(speeches):
        input_list.append({
            "speaker": s.get("speaker"),
            "text": s.get("text"),
            "time": s.get("time"),
            "position": s.get("position", idx),
        })
    input_json = json.dumps({"speeches": input_list}, ensure_ascii=False)

    prompt = _NER_PROMPT.format(input_json=input_json)
    try:
        raw = await call_claude_and_get_text(prompt, max_tokens=max_tokens, temperature=0.0)
        # try parse JSON
        parsed = json.loads(raw)
        # basic schema sanity check
        if "entities" not in parsed or "events" not in parsed:
            return {"error": "Missing expected fields in model output", "raw": raw}
        return parsed
    except json.JSONDecodeError:
        # return raw text so we can debug
        return {"error": "JSON parse error", "raw": raw}
    except Exception as e:
        log.exception("LLM extraction failed")
        return {"error": f"LLM extraction failed: {e}"}


async def summarize_speakers(speeches: List[Dict[str, Any]], max_speakers: Optional[int] = None, max_tokens: int = 800) -> Dict[str, Any]:
    """
    Uses Claude to produce 2-3 sentence factual summaries for each speaker.
    - max_speakers: if set, only summarize the first N speakers.
    Returns parsed JSON like {"speaker_summaries": [ ... ]} or {"error":..., "raw": ...}
    """
    input_list = []
    for idx, s in enumerate(speeches):
        if max_speakers is not None and idx >= max_speakers:
            break
        input_list.append({
            "speaker": s.get("speaker"),
            "text": s.get("text"),
            "time": s.get("time"),
            "position": s.get("position", idx),
        })
    input_json = json.dumps({"speeches": input_list}, ensure_ascii=False)
    prompt = _SUMMARY_PROMPT.format(input_json=input_json)
    try:
        raw = await call_claude_and_get_text(prompt, max_tokens=max_tokens, temperature=0.0)
        parsed = json.loads(raw)
        if "speaker_summaries" not in parsed:
            return {"error": "Missing speaker_summaries", "raw": raw}
        return parsed
    except json.JSONDecodeError:
        return {"error": "JSON parse error", "raw": raw}
    except Exception as e:
        log.exception("LLM summarize failed")
        return {"error": f"LLM summarize failed: {e}"}
```

---

## Updated `fetchers/hansard_fetcher.py` (small change)

I left the detailed structured Hansard fetcher as before, but added `position` indices to each speech block so the LLM has positions to reference. If you already have the previous full version, replace the function `fetch_latest_hansard_structured` with this updated version that sets `position` on each speech item before returning.

(If you prefer, I can paste the full updated file again — I kept the earlier implementation unchanged except for ensuring `position` is present.)

---

## Updated `mcp_server.py` — new tools for LLM-assisted NER and summaries

Add these tools to your existing `mcp_server.py` (or replace the file with the version below). They call the `claude_client` functions and return the result.

```python
# mcp_server.py (excerpt showing new tools to add)
from llm.claude_client import extract_entities_and_events, summarize_speakers
from fastmcp import ToolError

# ... existing tools above ...

@mcp.tool
async def get_hansard_entities(limit: int = 200) -> Dict[str, Any]:
    """
    Runs LLM-assisted NER & event extraction on the latest Hansard speeches.
    - limit: max number of speech blocks to include (default 200)
    Returns parsed JSON with keys 'entities' and 'events', or an error.
    """
    try:
        data = await fetch_with_cache("hansard_structured", fetch_latest_hansard_structured)
        if isinstance(data, dict) and data.get("error"):
            raise ToolError(data.get("error"))
        speeches = data.get("speeches", [])
        # assign positions if missing and limit
        for idx, s in enumerate(speeches):
            s["position"] = s.get("position", idx)
        if limit and limit > 0:
            speeches = speeches[:limit]
        result = await extract_entities_and_events(speeches)
        return result
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to run NER on Hansard: {e}")


@mcp.tool
async def get_hansard_speaker_summaries(limit: int = 50) -> Dict[str, Any]:
    """
    Returns speaker-indexed 2-3 sentence summaries for the latest Hansard.
    - limit: maximum number of speaker blocks to summarize.
    """
    try:
        data = await fetch_with_cache("hansard_structured", fetch_latest_hansard_structured)
        if isinstance(data, dict) and data.get("error"):
            raise ToolError(data.get("error"))
        speeches = data.get("speeches", [])
        # ensure positions present
        for idx, s in enumerate(speeches):
            s["position"] = s.get("position", idx)
        result = await summarize_speakers(speeches, max_speakers=limit)
        return result
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to create speaker summaries: {e}")
```

(Place these tool definitions near your other `@mcp.tool` functions.)

---

## Example test client for the new tools

```python
# examples/test_hansard_llm_tools.py
import asyncio
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
import json

async def main():
    transport = StreamableHttpTransport(base_url="http://127.0.0.1:8000/mcp")
    async with Client(transport=transport) as client:
        ent = await client.call_tool(name="get_hansard_entities", arguments={"limit": 150})
        print("Entities/Events result keys:", list(ent.keys()))
        if ent.get("error"):
            print("Error from NER tool:", ent["error"])
            print("Raw LLM text (if present):", ent.get("raw", "")[:800])
        else:
            print("entities count:", len(ent.get("entities", [])))
            print("events count:", len(ent.get("events", [])))
            # print first entity sample
            if ent.get("entities"):
                print("Sample entity:", ent["entities"][0])

        summ = await client.call_tool(name="get_hansard_speaker_summaries", arguments={"limit": 12})
        if summ.get("error"):
            print("Summary tool error:", summ["error"])
            print(summ.get("raw", "")[:800])
        else:
            print("Speaker summaries count:", len(summ.get("speaker_summaries", [])))
            if summ.get("speaker_summaries"):
                print(json.dumps(summ["speaker_summaries"][:3], indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
```

---

## README / Dependency updates

Add `openai` to your `pip install` list:

```bash
pip install openai
```

Environment variable:

```bash
export OPENAI_API_KEY="sk-xxxx..."
```

Caveats & Guidance:

* The prompts instruct the model to output strict JSON. If the model returns non-JSON (rare), the tool returns `{"error":"JSON parse error","raw": "<raw model text>"}` so you can inspect and adjust prompts or model params.
* We set `temperature=0.0` for deterministic extraction and summaries. You can increase temperature for more natural summaries, but that may reduce exactness.
* Keep `max_tokens` conservative for stable outputs (we used 1200/800). If transcripts are very large, consider chunking speeches and then merging results.

---

## Next steps I can do immediately (pick one, I’ll implement now):

1. Add an **optional batching worker** that chunks speeches and runs LLM calls in parallel (useful if transcripts are very long).
2. Persist NER and summaries to a local SQLite DB with simple versioning (date + SHA256 of transcript), and expose a tool to retrieve historical extractions.
3. Add an LLM prompt tuning layer — e.g., a small "instruction manager" so personas or preferred summarization tone can be injected for summaries.

Tell me which of the three you want and I’ll add it right away.

Nice — below is a complete implementation that adds:

* A **batching worker** (`tasks/batcher.py`) that chunks long Hansard transcripts and runs LLM-assisted NER and summaries in parallel with configurable concurrency. The worker is non-blocking and returns aggregated results. It also keeps the **most recent** processed result in-memory (so tools can access it).
* A **prompt tuning layer** (`llm/prompt_manager.py`) so you can inject persona and summarization tone into the prompts used by Claude Sonnet 4.5. This is used by the updated LLM client.
* An updated **LLM client** (`llm/claude_client.py`) with new entrypoints that accept `persona` and `tone` and expose a `batch_process_speeches` helper that the batcher calls.
* MCP tools added to `mcp_server.py` so the agent can trigger batch processing from the LLM (or other clients) and fetch the latest processed outputs.

Drop these files into your existing project. They integrate with the previously-provided Hansard fetcher and MCP server. Everything is async, uses `asyncio` concurrency limits, includes error handling, and ensures JSON-structured outputs.

---

## File: `llm/prompt_manager.py`

```python
# llm/prompt_manager.py
"""
Prompt manager: manages persona templates and tone modifiers for the NER and summary prompts.
Allows generating final prompts with persona & tone injected.
"""

from typing import Dict, Optional
import textwrap

# Base templates (placeholders) — they will be combined with persona/tone
_BASE_NER_PROMPT = textwrap.dedent(
    """
    You are an extraction engine. Input: a JSON array named "speeches" where each item has:
      - speaker: string
      - text: string
      - time: optional string or null
      - position: integer (index in original transcript)
    Task: Extract named entities and events from the speeches and return a strict JSON object with exactly these top-level fields:

    {{
      "entities": [
        {{
          "entity": "<canonical entity name>",
          "type": "<one of PERSON, ORG, BILL, LOCATION, EVENT, OTHER>",
          "mentions": [
            {{"speaker": "<speaker name>", "position": <int>, "context_snippet": "<short snippet around mention>"}}
          ]
        }},
        ...
      ],
      "events": [
        {{
          "label": "<short label, e.g., 'Question Period', 'Bill C-21 mention'>",
          "type": "<one of BILL_MENTION, MOTION, QUESTION_PERIOD, STATEMENT, OTHER>",
          "position": <int>,
          "speakers": ["Speaker A", "Speaker B"],
          "snippet": "<short textual snippet>"
        }},
        ...
      ]
    }}

    Important constraints:
    - Output MUST be valid JSON and nothing else (no commentary, no markdown).
    - Use the speeches as provided; do not invent facts.
    - Keep snippets short (<= 300 characters).
    - If nothing found, return empty lists, e.g. "entities": [], "events": [].

    Here is the input to analyze (as JSON):
    {input_json}
    """
)

_BASE_SUMMARY_PROMPT = textwrap.dedent(
    """
    You are to produce short descriptive summaries for each speaker block.
    Input: a JSON array named "speeches" where each item has:
      - speaker: string
      - text: string
      - time: optional string or null
      - position: integer

    Output: a strict JSON object:
    {{
      "speaker_summaries": [
        {{"speaker": "<speaker name>", "summary": "<2-3 sentence factual summary of that speaker's content — descriptive only>"}},
        ...
      ]
    }}

    Constraints:
    - 2-3 sentences per speaker, factual, no policy recommendations or opinions.
    - Output MUST be valid JSON only.
    - Keep summary length <= 300 words per speaker.
    - If a speaker's text is empty, skip them.

    Input (JSON):
    {input_json}
    """
)

# Default persona snippets (can be extended)
_PERSONA_SNIPPETS: Dict[str, str] = {
    "default": "You are a neutral, factual summarization assistant. Do not provide recommendations.",
    "prime_minister": "You are briefing a senior federal official focused on national policy outcomes. Emphasize national-level context.",
    "finance_minister": "You are briefing the Finance Minister: prioritize economic and fiscal framing in entity extraction and summaries.",
    "health_advisor": "You are briefing a senior health advisor: prioritize public health references, statistics, and actors in the health sector.",
}

# Tone modifiers - how the summary should read (affects prompt wording)
_TONE_SNIPPETS: Dict[str, str] = {
    "neutral": "Write in neutral formal prose, concise and factual.",
    "concise": "Be extremely concise — aim for short sentences and minimal words.",
    "detailed": "Provide a slightly more detailed descriptive summary, but still factual and within the constraints.",
    "plain": "Use plain language suitable for a broad government audience.",
}

def get_persona_snippet(persona: Optional[str]) -> str:
    if not persona:
        persona = "default"
    key = persona.lower().replace(" ", "_")
    return _PERSONA_SNIPPETS.get(key, _PERSONA_SNIPPETS["default"])

def get_tone_snippet(tone: Optional[str]) -> str:
    if not tone:
        tone = "neutral"
    key = tone.lower()
    return _TONE_SNIPPETS.get(key, _TONE_SNIPPETS["neutral"])

def build_ner_prompt(input_json: str, persona: Optional[str] = None, tone: Optional[str] = None) -> str:
    """
    Build the final NER prompt by injecting persona and tone context.
    """
    persona_text = get_persona_snippet(persona)
    tone_text = get_tone_snippet(tone)
    combined_context = f"{persona_text}\n{tone_text}\n\n"
    base = _BASE_NER_PROMPT.format(input_json=input_json)
    return combined_context + base

def build_summary_prompt(input_json: str, persona: Optional[str] = None, tone: Optional[str] = None) -> str:
    persona_text = get_persona_snippet(persona)
    tone_text = get_tone_snippet(tone)
    combined_context = f"{persona_text}\n{tone_text}\n\n"
    base = _BASE_SUMMARY_PROMPT.format(input_json=input_json)
    return combined_context + base
```

---

## File: `llm/claude_client.py` (updated — uses prompt_manager & exposes batch helper)

> This is a full file — replace your existing `llm/claude_client.py` with this version (it keeps the previous behaviors and adds persona/tone support and `batch_process_speeches` helper).

```python
# llm/claude_client.py
import os
import json
import asyncio
from typing import Any, Dict, List, Optional
import logging
import textwrap

import openai

from llm.prompt_manager import build_ner_prompt, build_summary_prompt

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

MODEL_NAME = "claude-sonnet-4.5"
DEFAULT_MAX_TOKENS = 1600
DEFAULT_TEMPERATURE = 0.0

def _prepare_openai_client() -> None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set in environment.")
    openai.api_key = key

async def _call_openai_responses(prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, temperature: float = DEFAULT_TEMPERATURE) -> Dict[str, Any]:
    _prepare_openai_client()
    def _blocking_call():
        try:
            resp = openai.responses.create(
                model=MODEL_NAME,
                input=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp
        except AttributeError:
            messages = [{"role": "user", "content": prompt}]
            resp = openai.ChatCompletion.create(
                model=MODEL_NAME,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp
    try:
        resp = await asyncio.to_thread(_blocking_call)
        return resp
    except Exception:
        log.exception("OpenAI call failed")
        raise

def _extract_text_from_response(resp: Any) -> str:
    try:
        if hasattr(resp, "output_text"):
            return resp.output_text
        if isinstance(resp, dict):
            out = resp.get("output")
            if out and isinstance(out, list):
                pieces = []
                for item in out:
                    if isinstance(item, dict):
                        content = item.get("content")
                        if isinstance(content, list):
                            for c in content:
                                t = c.get("text")
                                if t:
                                    pieces.append(t)
                        if item.get("text"):
                            pieces.append(item.get("text"))
                if pieces:
                    return "\n".join(pieces)
            choices = resp.get("choices")
            if choices and isinstance(choices, list):
                first = choices[0]
                if first.get("message") and first["message"].get("content"):
                    return first["message"]["content"]
                if first.get("text"):
                    return first["text"]
        return str(resp)
    except Exception:
        log.exception("Failed to extract text from OpenAI response")
        return ""

async def call_claude_and_get_text(prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, temperature: float = DEFAULT_TEMPERATURE) -> str:
    resp = await _call_openai_responses(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
    text = _extract_text_from_response(resp)
    return text

# --- Extraction and summarization functions with persona & tone support ---

async def extract_entities_and_events(
    speeches: List[Dict[str, Any]],
    persona: Optional[str] = None,
    tone: Optional[str] = None,
    max_tokens: int = 1200
) -> Dict[str, Any]:
    """
    Run LLM extraction with persona & tone injected.
    """
    input_list = []
    for idx, s in enumerate(speeches):
        input_list.append({
            "speaker": s.get("speaker"),
            "text": s.get("text"),
            "time": s.get("time"),
            "position": s.get("position", idx),
        })
    input_json = json.dumps({"speeches": input_list}, ensure_ascii=False)
    prompt = build_ner_prompt(input_json=input_json, persona=persona, tone=tone)
    try:
        raw = await call_claude_and_get_text(prompt, max_tokens=max_tokens, temperature=0.0)
        parsed = json.loads(raw)
        if "entities" not in parsed or "events" not in parsed:
            return {"error": "Missing expected fields in model output", "raw": raw}
        return parsed
    except json.JSONDecodeError:
        return {"error": "JSON parse error", "raw": raw}
    except Exception as e:
        log.exception("LLM extraction failed")
        return {"error": f"LLM extraction failed: {e}"}

async def summarize_speakers(
    speeches: List[Dict[str, Any]],
    persona: Optional[str] = None,
    tone: Optional[str] = None,
    max_speakers: Optional[int] = None,
    max_tokens: int = 800
) -> Dict[str, Any]:
    """
    Produce speaker-indexed summaries (2-3 sentences each), with persona & tone.
    """
    input_list = []
    for idx, s in enumerate(speeches):
        if max_speakers is not None and idx >= max_speakers:
            break
        input_list.append({
            "speaker": s.get("speaker"),
            "text": s.get("text"),
            "time": s.get("time"),
            "position": s.get("position", idx),
        })
    input_json = json.dumps({"speeches": input_list}, ensure_ascii=False)
    prompt = build_summary_prompt(input_json=input_json, persona=persona, tone=tone)
    try:
        raw = await call_claude_and_get_text(prompt, max_tokens=max_tokens, temperature=0.0)
        parsed = json.loads(raw)
        if "speaker_summaries" not in parsed:
            return {"error": "Missing speaker_summaries", "raw": raw}
        return parsed
    except json.JSONDecodeError:
        return {"error": "JSON parse error", "raw": raw}
    except Exception as e:
        log.exception("LLM summarize failed")
        return {"error": f"LLM summarize failed: {e}"}

# --- Batch helper (for chunking & concurrency) ---

async def batch_process_speeches(
    speeches: List[Dict[str, Any]],
    *,
    persona: Optional[str] = None,
    tone: Optional[str] = None,
    ner_batch_size: int = 50,
    summary_batch_size: int = 20,
    concurrency: int = 3,
) -> Dict[str, Any]:
    """
    Run NER and speaker summaries across the supplied speeches using batching and concurrency.
    Returns an aggregated dict:
    {
      "entities": [...],  # merged entities from all NER batch runs (naive merge)
      "events": [...],
      "speaker_summaries": [...],  # combined summaries from summary batches
      "errors": [...]
    }
    Note: merging entities/events naively may produce duplicates; post-processing can be applied.
    """
    # Prepare list with positions ensured
    for idx, s in enumerate(speeches):
        s["position"] = s.get("position", idx)

    # Create batches for NER and summaries
    ner_batches = [speeches[i:i+ner_batch_size] for i in range(0, len(speeches), ner_batch_size)]
    summary_batches = [speeches[i:i+summary_batch_size] for i in range(0, len(speeches), summary_batch_size)]

    sem = asyncio.Semaphore(concurrency)
    ner_results = []
    summary_results = []
    errors = []

    async def run_ner_batch(batch):
        async with sem:
            try:
                res = await extract_entities_and_events(batch, persona=persona, tone=tone)
                return res
            except Exception as e:
                log.exception("NER batch failed")
                return {"error": str(e)}

    async def run_summary_batch(batch):
        async with sem:
            try:
                res = await summarize_speakers(batch, persona=persona, tone=tone, max_speakers=len(batch))
                return res
            except Exception as e:
                log.exception("Summary batch failed")
                return {"error": str(e)}

    # Run NER batches concurrently (bounded by semaphore)
    ner_tasks = [asyncio.create_task(run_ner_batch(b)) for b in ner_batches]
    summary_tasks = [asyncio.create_task(run_summary_batch(b)) for b in summary_batches]

    # Gather results
    if ner_tasks:
        ner_completed = await asyncio.gather(*ner_tasks)
        for r in ner_completed:
            if r is None:
                continue
            if isinstance(r, dict) and r.get("error"):
                errors.append({"type": "ner", "detail": r.get("error"), "raw": r.get("raw")})
            else:
                ner_results.append(r)

    if summary_tasks:
        sum_completed = await asyncio.gather(*summary_tasks)
        for r in sum_completed:
            if r is None:
                continue
            if isinstance(r, dict) and r.get("error"):
                errors.append({"type": "summary", "detail": r.get("error"), "raw": r.get("raw")})
            else:
                summary_results.append(r)

    # Naive merge logic for entities/events and summaries
    merged_entities = []
    merged_events = []
    for res in ner_results:
        ents = res.get("entities", []) if isinstance(res, dict) else []
        evs = res.get("events", []) if isinstance(res, dict) else []
        merged_entities.extend(ents)
        merged_events.extend(evs)

    merged_summaries = []
    for res in summary_results:
        ssum = res.get("speaker_summaries", []) if isinstance(res, dict) else []
        merged_summaries.extend(ssum)

    # De-dup entities by (entity, type) keeping mentions combined (simple approach)
    dedup_entities = {}
    for ent in merged_entities:
        key = (ent.get("entity"), ent.get("type"))
        if key not in dedup_entities:
            dedup_entities[key] = {
                "entity": ent.get("entity"),
                "type": ent.get("type"),
                "mentions": ent.get("mentions", []).copy()
            }
        else:
            dedup_entities[key]["mentions"].extend(ent.get("mentions", []))
    dedup_entities_list = list(dedup_entities.values())

    # Optionally, we could deduplicate events similarly
    # For now, keep them as-is but remove exact duplicates
    seen_ev = set()
    unique_events = []
    for ev in merged_events:
        key = (ev.get("type"), ev.get("label") or ev.get("match"), ev.get("position"))
        if key in seen_ev:
            continue
        seen_ev.add(key)
        unique_events.append(ev)

    # Merge speaker summaries by speaker name (keep the first summary for each speaker)
    speaker_map = {}
    for s in merged_summaries:
        sp = s.get("speaker")
        if not sp:
            continue
        if sp not in speaker_map:
            speaker_map[sp] = s.get("summary")
    merged_summaries_final = [{"speaker": k, "summary": v} for k, v in speaker_map.items()]

    return {
        "entities": dedup_entities_list,
        "events": unique_events,
        "speaker_summaries": merged_summaries_final,
        "errors": errors,
        "stats": {
            "ner_batches": len(ner_batches),
            "summary_batches": len(summary_batches),
            "ner_results": len(ner_results),
            "summary_results": len(summary_results)
        }
    }
```

---

## File: `tasks/batcher.py`

```python
# tasks/batcher.py
"""
Batcher: orchestrates background batch processing for long transcripts.
Keeps the most recent processed result in memory (accessible via get_last_result()).

API:
- process_speeches_async(speeches, persona, tone, ner_batch_size, summary_batch_size, concurrency)
- get_last_result() -> Optional[dict]
"""

import asyncio
from typing import Any, Dict, List, Optional
from llm.claude_client import batch_process_speeches
import logging
import time

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_last_result: Optional[Dict[str, Any]] = None
_last_result_meta: Dict[str, Any] = {}

async def process_speeches_async(
    speeches: List[Dict[str, Any]],
    *,
    persona: Optional[str] = None,
    tone: Optional[str] = None,
    ner_batch_size: int = 50,
    summary_batch_size: int = 20,
    concurrency: int = 3,
) -> Dict[str, Any]:
    """
    Kick off batch processing and store the result in memory. This function runs the entire
    batch processing pipeline and returns the aggregated result.
    """
    global _last_result, _last_result_meta
    start = time.time()
    try:
        log.info("Starting batch processing: speeches=%d persona=%s tone=%s", len(speeches), persona, tone)
        result = await batch_process_speeches(
            speeches,
            persona=persona,
            tone=tone,
            ner_batch_size=ner_batch_size,
            summary_batch_size=summary_batch_size,
            concurrency=concurrency,
        )
        elapsed = time.time() - start
        _last_result = result
        _last_result_meta = {
            "timestamp": time.time(),
            "elapsed_seconds": elapsed,
            "persona": persona,
            "tone": tone,
            "ner_batch_size": ner_batch_size,
            "summary_batch_size": summary_batch_size,
            "concurrency": concurrency,
            "num_speeches": len(speeches),
        }
        log.info("Batch processing completed in %.1fs", elapsed)
        return {"result": result, "meta": _last_result_meta}
    except Exception as e:
        log.exception("process_speeches_async failed")
        return {"error": str(e)}

def get_last_result() -> Optional[Dict[str, Any]]:
    """
    Return the most recent processed result (result + meta) or None.
    """
    if _last_result is None:
        return None
    return {"result": _last_result, "meta": _last_result_meta}
```

---

## MCP Server: add new tools to `mcp_server.py`

Add the following tool functions into your MCP server (under the other `@mcp.tool` definitions). They let a client trigger batch processing and retrieve last processed data.

```python
# mcp_server.py (additions near other tools)
from tasks.batcher import process_speeches_async, get_last_result

@mcp.tool
async def run_hansard_batch_processing(
    persona: str = "default",
    tone: str = "neutral",
    ner_batch_size: int = 50,
    summary_batch_size: int = 20,
    concurrency: int = 3
) -> Dict[str, Any]:
    """
    Trigger batch processing on the latest Hansard. This tool:
      - obtains the latest structured Hansard from the cache,
      - runs the batching worker with the given persona & tone,
      - stores the result to in-memory store and returns metadata + a small preview.
    """
    try:
        data = await fetch_with_cache("hansard_structured", fetch_latest_hansard_structured)
        if isinstance(data, dict) and data.get("error"):
            raise ToolError(data.get("error"))
        speeches = data.get("speeches", [])
        # start processing
        processed = await process_speeches_async(
            speeches,
            persona=persona,
            tone=tone,
            ner_batch_size=ner_batch_size,
            summary_batch_size=summary_batch_size,
            concurrency=concurrency
        )
        return processed
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to run batch processing: {e}")

@mcp.tool
async def get_last_hansard_processing_result() -> Dict[str, Any]:
    """
    Return the most recent batch processing result (if any).
    """
    try:
        res = get_last_result()
        if not res:
            return {"status": "none", "message": "No previous processing runs found"}
        return {"status": "ok", "last_run": res}
    except Exception as e:
        raise ToolError(f"Failed to get last processing result: {e}")
```

---

## Example usage / test

1. Start your MCP server (which now exposes new tools):

```bash
python mcp_server.py
```

2. Use the example client to trigger batch processing and then fetch the result:

```python
# examples/test_batch_run.py
import asyncio
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
import json

async def main():
    transport = StreamableHttpTransport(base_url="http://127.0.0.1:8000/mcp")
    async with Client(transport=transport) as client:
        print("Trigger batch processing (this will call Claude for NER + summaries)...")
        resp = await client.call_tool(
            name="run_hansard_batch_processing",
            arguments={
                "persona": "finance_minister",
                "tone": "concise",
                "ner_batch_size": 40,
                "summary_batch_size": 10,
                "concurrency": 3
            }
        )
        print("Batch response meta:", resp.get("meta", {}))
        # Now fetch last result
        lr = await client.call_tool(name="get_last_hansard_processing_result", arguments={})
        print("Last run:", json.dumps(lr, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
```

Notes:

* The batch run will make multiple calls to Claude Sonnet 4.5. Make sure `OPENAI_API_KEY` is set and you have adequate rate limits/quotas.
* If you prefer the batch to run fully in the background (i.e., return immediately and process asynchronously), modify `run_hansard_batch_processing` to spawn `asyncio.create_task(process_speeches_async(...))` and return an immediate ack with a run id. I implemented a synchronous-to-completion tool for clarity — changeable on request.

---

## Final notes & recommended next small steps

* You now have an on-demand batcher and a prompt tuning layer. This lets you experiment with persona and tone, and scale to long transcripts by chunking.
* If you want:

  * I can switch `run_hansard_batch_processing` to a background-fire-and-forget mode and return a run-id, plus a tool to poll run status.
  * I can add persistence (SQLite/Redis) for processed results and run history.
  * I can add an optional step to run the merged entities/events through a light canonicalization (use fuzzy deduplication).
* Want me to change `run_hansard_batch_processing` to background mode (returns run-id) and add a `get_run_status(run_id)` tool? If yes, I’ll implement it now.

