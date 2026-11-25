Graduation Project Proposal: Local Smart Notebook - Privacy-First Local AI Knowledge &amp; Analytics Workspace

## 1. Project Overview &amp; Abstract

Project Title: Local Smart Notebook: A Multi-Agent Local Knowledge &amp; Analytics Platform

Target Domain: Local Generative AI, Retrieval-Augmented Generation (RAG), Autonomous AI Agents, Data Science Automation

## Abstract:

Local Smart Notebook is an open-source, fully offline, privacy-first alternative to cloudbased research tools like Google NotebookLM. Designed to run completely on local consumer hardware without sending data to external cloud APIs, Local Smart Notebook enables users to ingest multi-format documents (PDFs, DOCX, CSV, XLSX, TXT), perform contextual multi-document Retrieval-Augmented Generation (RAG), synthesize research summaries, execute code-driven data analytics on Excel spreadsheets, and automatically compile findings into customizable PowerPoint presentations (.pptx), images, graphs, or excel sheets.

## 2. Problem Statement &amp; Motivation

Cloud-based AI workspaces like Google NotebookLM offer strong analytical capabilities, but they introduce critical limitations for sensitive domains:

1. Data Privacy &amp; Compliance: Healthcare providers, legal teams, financial institutions, and government agencies cannot upload confidential contracts, medical records, or proprietary research to third-party cloud servers.
2. API Costs &amp; Bandwidth Limitations: Heavy querying across thousands of pages of documentation incurs high token usage costs and requires constant high-speed internet.
3. Lack of Native Data Processing: Existing tools focus primarily on textual Q&amp;A and lack native execution environments to compute complex formulaic operations, filter large dataset files (Excel/CSV), or export native presentation slides.

Local Smart Notebook solves these issues by embedding open-source Large Language Models (LLMs), local vector embeddings, and sandboxed Python code execution environments entirely on the user's workstation.

## 3. Core Features &amp; Technical Feasibility

All requested features can be delivered strictly using Python and standard open-source libraries.

## Feature 1: Multi-Document Local RAG Engine

- Capability: Ingests dozens of files simultaneously (PDF, DOCX, Markdown, Text, Code files).

## · Technical Strategy:

- o Parser: Unstructured, PyPDF, or pdfplumber for semantic text chunking.
- o Local Embeddings: bge-m3 or nomic-embed-text-v1.5 running locally via HuggingFace sentence-transformers or Ollama.
- o Vector Database: Qdrant (Embedded local mode) or ChromaDB stored on local disk.
- o Hybrid Search: Dense vector search combined with BM25 sparse keyword retrieval (Reciprocal Rank Fusion - RRF) to maximize context retrieval accuracy.

## Feature 2: Automated Summarization &amp; Synthesis Engine

- Capability: Generates executive summaries, thematic comparisons, study guides, and bulleted briefings across single or combined sources.

## · Technical Strategy:

- o Uses map-reduce or hierarchical chunk summarization chains managed by local LLMs (e.g., Llama 3.1 8B, Qwen 2.5 14B, or DeepSeek-R1-DistillQwen-14B).
- o Enforces structured output formatting (JSON/Markdown schemas) to extract key takeaways, entities, and citations pointing directly to source page numbers.

## Feature 3: Automated Presentation Generator (.pptx)

- Capability: Transforms summarized insights or document collections into fully editable PowerPoint (.pptx) decks.

## · Technical Strategy:

- o An AI agent decomposes the document context into slide outlines: Title, Subtitle, Bullet Points, and Speaker Notes in JSON format.
- o A custom Python script powered by python-pptx ingests the JSON schema and builds formatted slides using standard templates (Title Slide, 2-Column Comparison, Stat Highlight, Conclusion).

Document Context -&gt; Local Agent -&gt; Structured JSON -&gt; python-pptx -&gt; Downloadable .pptx

## Feature 4: Spreadsheet Data Analysis Engine (Excel &amp; CSV)

- Capability: Cleans, filters, aggregates, visualizes, and performs statistical analysis on .xlsx / .csv files via natural language queries.

## · Technical Strategy:

- o Code Interpreter Agent Pattern: Instead of having the LLM guess numeric calculations (which leads to math errors), an agent generates sandboxed Python pandas / openpyxl code.
- o The local system executes the generated code on the local dataset and returns the resulting table summary or Matplotlib/Seaborn plot image back to the UI.

## Feature 5: Multi-Agent Coordination (Local AI Agents)

- Capability: Routes complex queries to specialized sub-agents (e.g., Research Agent, Coding/Data Agent, Slide Builder Agent).

## · Technical Strategy:

- o Built using LangGraph or CrewAI to manage stateful graph execution and tool calling with local models.

## 4. Recommended Technology Stack

| Layer                     | Recommended Tool / Library          | Reason for Selection                                                                  |
|---------------------------|-------------------------------------|---------------------------------------------------------------------------------------|
| LLM Inference Server      | Ollama or vLLM                      | Lightweight, cross-platform, exposes an OpenAI-compatible API locally.                |
| Local LLM Models          | Qwen 2.5 (7B/14B) or Llama 3.1 (8B) | Outstanding instruction- following, structured JSON generation, and function calling. |
| Local Embedding Model     | BAAI/bge-m3 or nomic- embed-text    | State-of-the-art multilingual vector representations, 100% offline.                   |
| Vector Database           | Qdrant (Local) or ChromaDB          | Native Python support, disk- persistent storage, fast vector indexing.                |
| Orchestration & Agents    | LangGraph / LlamaIndex              | State machine management for agent execution loops, memory, and tool calls.           |
| Data & Spreadsheet Engine | Pandas, OpenPyXL, DuckDB            | Fast array and relational data querying directly in memory.                           |

| Layer                                                        | Recommended Tool / Library                                                          | Reason for Selection   |
|--------------------------------------------------------------|-------------------------------------------------------------------------------------|------------------------|
| python-pptx                                                  | Declarative generation of native, editable PowerPoint presentations.                | Slide Generation       |
| FastAPI (Python)                                             | Async support, high performance, clean REST API endpoints for frontend interaction. | Backend API Framework  |
| React.js + Tailwind CSS (or Streamlit for rapid prototyping) | Responsive, modern split-pane UI matching NotebookLM's workspace layout.            | Frontend UI Framework  |