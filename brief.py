import uvicorn
import httpx
import json
import asyncio
import os
import openai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, AsyncGenerator

# --- 1. Define the Core Data Structures (Pydantic Models) ---

class DocumentSnippet(BaseModel):
    """A single piece of retrieved context from a data source."""
    source_name: str = Field(..., description="Name of the data source, e.g., 'StatsCan', 'GC Newsroom', 'CBC News'")
    source_url: str = Field(..., description="The direct URL to the article or data.")
    timestamp: str = Field(..., description="ISO 8601 timestamp of the document.")
    content: str = Field(..., description="The text snippet.")
    tag: str = Field(..., description="Internal tag, e.g., 'government_statement', 'statistical_data', 'media_response'")

class GoCPolicyBriefPacket(BaseModel):
    """
    The fastmcp (Model Context Protocol) packet.
    This structure is sent to the LLM for synthesis.
    """
    session_persona: Dict[str, Any] = Field(..., description="The dynamic, user-provided persona.")
    user_query: str = Field(..., description="The user's real-time query.")
    system_instructions: str = Field(..., description=(
        "You are a neutral, non-partisan policy intelligence analyst. "
        "Your role is to summarize, analyze, and synthesize the provided public data. "
        "**You must not, under any circumstances, provide opinions, advice, or policy recommendations.** "
        "You must state facts, cite all sources using markdown [Source X], and flag documented trends or contradictions."
    ))
    retrieved_context: List[DocumentSnippet] = Field(..., description="The list of context snippets retrieved by the RAG pipeline.")

class ChartData(BaseModel):
    """Structured data for rendering an interactive chart."""
    type: Literal["line", "bar", "pie", "doughnut"]
    title: str
    labels: List[str]
    datasets: List[Dict[str, Any]]

# The FullAgentResponse structure is now implicit in the LLM output format:
# [Markdown Text]###JSON_START###[ChartData JSON or 'null']


# --- 2. "Real" (but Mock DB) Data Ingestion Pipeline (RAG) ---

class DataPipeline:
    """
    This is now a 'real' pipeline that searches a mock database
    based on persona keywords.
    """
    def __init__(self):
        # Mock database of all available documents
        self.mock_document_db = {
            "housing": [
                DocumentSnippet(
                    source_name="GC Newsroom",
                    source_url="https://canada.ca/news/housing-announcement",
                    timestamp="2025-10-27T09:00:00Z",
                    content="The Honourable Minister X today announced the 'Building Homes Faster' plan, which sets a target of 500,000 new homes built in the next fiscal year.",
                    tag="government_statement"
                ),
                DocumentSnippet(
                    source_name="Statistics Canada - Labour Force Survey",
                    source_url="https://statscan.gc.ca/lfs-oct-2025",
                    timestamp="2025-10-25T08:30:00Z",
                    content="The construction sector saw a net decrease of 5,000 jobs in October, the third consecutive monthly decline. Analysts point to rising material costs.",
                    tag="statistical_data"
                ),
                DocumentSnippet(
                    source_name="Hansard (Parliamentary Debate)",
                    source_url="https://parl.ca/hansard/debate-2025-10-26",
                    timestamp="2025-10-26T14:30:00Z",
                    content="Hon. Member Y (Opposition): 'Mr. Speaker, the government's new housing plan is completely detached from reality. How can they promise 500,000 homes when the industry is shedding jobs?'",
                    tag="media_response"
                ),
                DocumentSnippet(
                    source_name="CBC News",
                    source_url="https://cbc.ca/news/housing-plan-analysis",
                    timestamp="2025-10-27T10:15:00Z",
                    content="Analysis: The government's ambitious 500,000-home target, announced today, faces significant headwinds from a shrinking construction labour pool, as reported by Statistics Canada last week.",
                    tag="media_response"
                ),
            ],
            "ai": [
                DocumentSnippet(
                    source_name="GC Newsroom",
                    source_url="https://canada.ca/news/ai-strategy",
                    timestamp="2025-10-26T11:00:00Z",
                    content="Canada launches new $50M investment in AI safety research.",
                    tag="government_statement"
                ),
                DocumentSnippet(
                    source_name="CBC News",
                    source_url="https://cbc.ca/news/ai-investment-analysis",
                    timestamp="2025-10-26T12:15:00Z",
                    content="The new $50M fund is seen by experts as a good first step, but trails investments from the UK and US.",
                    tag="media_response"
                ),
            ],
            "default": [
                DocumentSnippet(
                    source_name="System",
                    source_url="#",
                    timestamp="2025-10-27T00:00:00Z",
                    content="No specific documents found for that query. Please try a different topic.",
                    tag="system"
                )
            ]
        }

    async def fetch_context(self, query: str, persona: Dict[str, Any]) -> List[DocumentSnippet]:
        """
        Fetches relevant documents by searching the mock DB for persona keywords and query terms.
        """
        await asyncio.sleep(0.2) # Simulate DB query latency
        
        # Combine persona keywords and query terms for a broader search
        query_words = set(query.lower().split())
        persona_keywords = set(persona.get("focus_keywords", []))
        search_terms = query_words.union(persona_keywords)

        if not search_terms:
            return self.mock_document_db["default"]

        matched_docs = []
        # Iterate over all document lists (excluding 'default')
        for key, docs in self.mock_document_db.items():
            if key == 'default':
                continue
            
            for doc in docs:
                doc_content_lower = doc.content.lower()
                if any(term in doc_content_lower for term in search_terms):
                    if doc not in matched_docs:
                        matched_docs.append(doc)
        
        if matched_docs:
            return matched_docs
        
        return self.mock_document_db["default"]

# --- 3. Real LLM Agent (Claude via OpenAI-Compatible Proxy) ---

class LLMAgent:
    """
    This is now a REAL LLM Agent using streaming.
    It uses the OpenAI SDK to call a Claude model via a proxy.
    """
    DELIMITER = "###JSON_START###"
    MODEL_NAME = "claude-3-5-sonnet-20240620"
    
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.base_url = os.environ.get("OPENAI_BASE_URL")
        
        if not self.api_key or not self.base_url:
            print("\n" + "="*80)
            print("!!! CRITICAL WARNING: LLM AGENT IS NOT CONFIGURED !!!")
            print("This app requires an OpenAI-compatible proxy to call Claude models.")
            print("Please set the following environment variables:")
            print("  - OPENAI_API_KEY: Your API key for the proxy service.")
            print("  - OPENAI_BASE_URL: The base URL for the proxy (e.g., https://api.openrouter.ai/v1)")
            print("The application will not be able to generate responses until this is fixed.")
            print("="*80 + "\n")
            self.client = None
        else:
            self.client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            print(f"LLM Agent initialized. Using model endpoint at: {self.base_url}")

    def _build_user_prompt(self, packet: GoCPolicyBriefPacket) -> str:
        """Builds the detailed prompt for the LLM, asking for a delimited stream response."""
        
        json_schema = ChartData.model_json_schema()
        
        context_str = "\n\n".join(
            [f"Source {i+1} ({doc.source_name}):\n{doc.content}\nURL: {doc.source_url}\nTimestamp: {doc.timestamp}" 
             for i, doc in enumerate(packet.retrieved_context)]
        )

        prompt = f"""
        User Query: "{packet.user_query}"
        
        Available Context:
        ---
        {context_str}
        ---
        
        Your task is to act as a policy analyst and answer the user's query based *only* on the context provided.
        You must adhere to all system instructions.
        
        Your final response MUST be formatted exactly as follows in a single continuous stream:
        1. A full, synthesized answer in **Markdown format** (This is the primary content).
        2. The specific delimiter string: `{self.DELIMITER}`
        3. A single, valid JSON object for the chart data (ChartData Pydantic model structure).
        
        If no chart is relevant or possible from the context, the JSON object MUST be the literal string 'null'. Do not invent data.

        JSON Schema for Chart Data (to follow the delimiter):
        {json.dumps(json_schema, indent=2)}
        """
        return prompt

    async def generate_response(self, packet: GoCPolicyBriefPacket) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Calls the LLM to synthesize the context and generate a response, streaming the result.
        Yields chunks with 'text_chunk' type until the delimiter is found, then yields a final 'final_json'.
        """
        if not self.client:
            yield {"type": "error", "message": "LLM Agent Not Configured. Check server logs."}
            return
            
        user_prompt = self._build_user_prompt(packet)
        
        try:
            stream = await self.client.chat.completions.create(
                model=self.MODEL_NAME,
                messages=[
                    {"role": "system", "content": packet.system_instructions},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=4096,
                stream=True, # Critical for streaming
            )
            
            full_buffer = ""
            is_text_part = True
            
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    full_buffer += content
                    
                    if is_text_part:
                        # Check for the delimiter in the buffered content
                        if self.DELIMITER in full_buffer:
                            # Delimiter found!
                            text_part, _, json_part_start = full_buffer.partition(self.DELIMITER)
                            
                            # 1. Yield the rest of the text part (up to the delimiter)
                            if text_part.strip():
                                yield {"type": "text_chunk", "content": text_part}
                            
                            # 2. Switch state, and reset buffer to collect only JSON
                            is_text_part = False
                            full_buffer = json_part_start
                        
                        else:
                            # Still streaming text, yield the content chunk
                            yield {"type": "text_chunk", "content": content}

            # --- End of stream: Process final JSON buffer ---
            
            if not is_text_part:
                raw_json = full_buffer.strip()
                
                try:
                    chart_data = None
                    if raw_json.lower() != 'null':
                        chart_data = ChartData.model_validate_json(raw_json)
                    
                    # Yield the final structured data
                    yield {"type": "final_json", "data": chart_data.model_dump() if chart_data else None}
                except Exception as e:
                    print(f"Failed to parse chart data JSON: {e}")
                    yield {"type": "error", "message": f"Failed to parse visualization data: {str(e)}"}
            
            else:
                 # If the stream ended before the delimiter was found, treat the whole buffer as text
                yield {"type": "text_chunk", "content": full_buffer}
                yield {"type": "error", "message": "Stream ended unexpectedly: Missing JSON data."}

        except openai.OpenAIError as e:
            error_message = f"LLM API Error: {str(e)}"
            print(error_message)
            yield {"type": "error", "message": error_message}
        except Exception as e:
            error_message = f"Unhandled Error: {str(e)}"
            print(error_message)
            yield {"type": "error", "message": error_message}


# --- 4. Initialize FastAPI App and Core Components ---

app = FastAPI(title="Real-Time Policy Agent Backend")
data_pipeline = DataPipeline()
llm_agent = LLMAgent()

# --- 5. Define API Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Serves the main index.html file for the browser dashboard."""
    try:
        # Load the updated HTML file
        with open("index.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Error: index.html not found.</h1>", status_code=500)
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error: {e}</h1>", status_code=500)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for the interactive browser dashboard."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            query = payload.get("query")
            persona = payload.get("persona")

            if not query or not persona:
                await websocket.send_text(json.dumps({"error": "Missing query or persona."}))
                continue

            await websocket.send_text(json.dumps({"status": "fetching", "message": "Query received. Fetching real-time context..."}))
            
            # 1. Fetch Context
            retrieved_context = await data_pipeline.fetch_context(query, persona)
            
            await websocket.send_text(json.dumps({"status": "synthesizing", "message": f"Found {len(retrieved_context)} relevant documents. Synthesizing response..."}))
            
            # 2. Build MCP Packet
            mcp_packet = GoCPolicyBriefPacket(
                session_persona=persona,
                user_query=query,
                retrieved_context=retrieved_context,
            )
            
            # 3. Get LLM Response as an Async Generator (Stream)
            response_stream = llm_agent.generate_response(mcp_packet)

            # 4. Stream chunks to the client
            async for chunk in response_stream:
                await websocket.send_text(json.dumps(chunk))

    except WebSocketDisconnect:
        print("Client disconnected from WebSocket")
    except Exception as e:
        print(f"An error occurred in the WebSocket: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except:
            pass # Client might already be disconnected

@app.post("/api/msteams")
async def msteams_bot_endpoint(request: Request):
    """
    HTTP endpoint for the MS Teams Bot. This remains non-streaming.
    It executes the full agent call to get the final text response.
    """
    try:
        payload = await request.json()
        query = payload.get("query")
        
        persona = payload.get("persona", {
            "role": "Senior Official",
            "department": "Unknown (via MS Teams)",
            "focus_keywords": []
        })
        
        if not query:
            return {"error": "No query provided"}
            
        retrieved_context = await data_pipeline.fetch_context(query, persona)
        
        mcp_packet = GoCPolicyBriefPacket(
            session_persona=persona,
            user_query=query,
            retrieved_context=retrieved_context
        )
        
        # Non-streaming call: Collect all chunks into one final text response
        full_text_response = ""
        response_stream = llm_agent.generate_response(mcp_packet)
        
        async for chunk in response_stream:
            if chunk.get("type") == "text_chunk":
                full_text_response += chunk.get("content", "")
            elif chunk.get("type") == "error":
                 # If an error is streamed, return it immediately
                return {"error": chunk.get("message")}
                
        # Strip the JSON part and delimiter for Teams
        text_only = full_text_response.partition(LLMAgent.DELIMITER)[0].strip()
        
        return {
            "response_text": text_only
        }
        
    except Exception as e:
        print(f"Error in /api/msteams: {e}")
        return {"error": str(e)}

# --- 6. Run the Application ---

if __name__ == "__main__":
    print("Starting backend server...")
    print("Access the dashboard at http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
