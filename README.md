# Monday.com Business Intelligence Agent

A conversational AI agent that answers founder-level business questions by querying live data
from two monday.com boards — **Work Orders** (project execution) and **Deals** (sales pipeline) —
cleaning it on the fly, and surfacing data-quality caveats alongside the answer.

Built for the Skylark Drones full-stack assignment.

**Hosted link:** `[ADD YOUR DEPLOYED URL HERE]`

---

## Result

Recorded runs of the agent answering the queries below, straight from the VSCode chat session
(monday.com MCP + `data-cleaner` MCP active, invoked via `/bi-agent`):

| Query | Result |
|---|---|
| "Show me all deals stuck in Proposal/Commercials Sent stage for more than a month?" | [result](q1.md) |
| "What's our average deal value?" (181/346 rows null — answer should state how many were excluded and why?" | [results](q2.md) |

### Demo look :
<img width="607" height="980" alt="image" src="https://github.com/user-attachments/assets/e30591f6-176d-4996-ae92-1b2d144c995d" />

---

## How it was built

1. **Connected monday.com's official MCP server** through the VSCode MCP marketplace/extension,
   which exposes monday.com's boards, items, and columns as tools directly inside VSCode's agent
   chat — no custom API client needed for read access.
2. **Authenticated with a monday.com API token** (read-only scope), supplied through VSCode's
   MCP input prompt (`${input:Authorization}` in `.vscode/mcp.json`), so the agent queries live
   board data and never touches the original CSVs directly.
3. **Added a custom local MCP server (`data-cleaner`)** alongside monday's server, exposing a
   `clean_board_data` tool that normalizes dates, categories, and malformed fields, drops
   duplicate/junk rows, and flags data-quality issues before any analysis happens.
4. **Wrote the agent's operating rules in `.github/prompts/bi-agent.prompt.md`** — defines how
   the agent should interpret founder-level questions, when to ask clarifying questions, and
   that it must always route raw monday.com data through the cleaning tool before analyzing it.
5. **Invoked on demand as a slash command** — typing `/bi-agent <question>` in VSCode's Copilot
   Chat attaches this prompt file's instructions for that turn and puts the session into agent
   mode, giving it access to both the monday.com MCP tools and the `data-cleaner` tool together.

This is the local development/testing setup. See **Setup → Hosted deployment** below for how the
same cleaning logic and prompt rules were carried over into the publicly accessible version.

---

## How it works

```
┌─────────────┐     ┌──────────────────┐      ┌──────────────────────┐
│   User      │ ──▶ │   Agent (Claude) │ ──▶  │  monday.com MCP/API  │
│(VSCode UI)  │     │  + tool-use loop │      │  (read-only)         │
└─────────────┘     └──────────────────┘      └──────────────────────┘
                             │
                             ▼
                   ┌──────────────────────┐
                   │  data-cleaner tool    │
                   │  (this repo)          │
                   └──────────────────────┘
                             │
                             ▼
                  cleaned records + quality report
                             │
                             ▼
                    answer + caveats to user
```

1. The user asks a business question in plain language (e.g. *"How's our pipeline looking for
   the energy sector this quarter?"*).
2. The agent interprets the query and decides which board(s) it needs (Deals, Work Orders, or
   both), and asks a clarifying question first if the request is ambiguous (no sector, no
   timeframe, undefined metric, etc.).
3. It fetches the relevant items **live from monday.com** via MCP/API — raw data is never
   hardcoded or cached from the original CSVs.
4. Before doing any analysis, the agent routes the raw records through the **`clean_board_data`**
   tool, which:
   - normalizes inconsistent date formats, category casing/typos, and multi-value fields
   - parses fields with embedded units (e.g. `"5360 HA"` → `{value: 5360, unit: "HA"}`)
   - flags missing values, unparseable fields, and negative amounts rather than silently
     dropping or miscounting them
   - detects and removes structural junk: duplicate rows and embedded header-leak rows
     (copy-paste artifacts from the source export)
   - returns a **data-quality report** alongside the cleaned records
5. The agent reasons over the cleaned data and answers the question, **explicitly stating any
   caveats** from the quality report (e.g. "excluded 12 records with missing close dates") instead
   of presenting a number as if it were complete.

---

## Architecture & tech stack

| Component | Choice | Why |
|---|---|---|
| LLM / agent runtime | Claude (Anthropic API), tool-use loop | Native tool-calling, good at reasoning over messy data + explaining caveats |
| Data source | monday.com read-only API/MCP | Required by the assignment; boards queried live, never hardcoded |
| Data cleaning | Custom Python tool (`clean_board_data`) | Deterministic cleaning is far more reliable than asking an LLM to normalize dates/text on the fly |
| Dev environment | VSCode + local MCP server (stdio) | Fast iteration loop for building/testing the cleaning tool against monday's hosted MCP server |
| Hosted deployment | `[FastAPI / Flask / Express — fill in]` on `[Render / Railway / Vercel — fill in]` | Assignment requires a link testable without local setup; local MCP servers can't be part of that, so cleaning logic (plain Python, no MCP-specific code) was ported into a hosted backend that calls the monday.com API directly |

See `DECISION_LOG.md` for the full reasoning behind these trade-offs, including why MCP was used
for local development but not for the hosted deployment.

---

## Project structure

```
.
├── .github/prompts/
│   └── bi-agent.prompt.md     # Agent operating rules, invoked via /bi-agent in Copilot Chat
├── .vscode/
│   └── mcp.json               # monday.com MCP + data-cleaner MCP server config
├── mcp-servers/
│   └── data-cleaner/           # Local MCP server exposing clean_board_data (dev/testing)
│       ├── server.py
│       └── pyproject.toml
└── README.md
```

---

## Setup

### 1. monday.com board configuration

1. Create two boards: **Work Orders** and **Deals**.
2. Import the provided CSVs (`Deal_funnel_Data.xlsx`, `Work_Order_Tracker_Data.xlsx`) as items.
   - Note: the Work Order source file has its real header on row 2 (row 1 is blank) — if
     importing manually, skip the first row or the board will pick up blank column names.
3. Set column types to match the data (Date columns as **Date**, monetary fields as
   **Numbers**, `Deal Stage` / `Sector` / `Status` fields as **Status** or **Dropdown**, etc.).
4. Generate a monday.com API token: **Admin → API → Generate token** (read-only scope is
   sufficient — this agent never writes to monday.com).

### 2. Local development (VSCode + MCP)

```bash
# clone the repo
git clone [repo url]
cd [repo]

# set up the local cleaning MCP server
cd mcp-servers/data-cleaner
uv sync
```

Add both servers to `.vscode/mcp.json` (already included in this repo):

```jsonc
{
  "servers": {
    "com.monday/monday.com": {
      "type": "http",
      "url": "https://mcp.monday.com/mcp",
      "headers": { "Authorization": "${input:Authorization}" }
    },
    "data-cleaner": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "${workspaceFolder}/mcp-servers/data-cleaner", "python", "server.py"]
    }
  },
  "inputs": [
    {
      "id": "Authorization",
      "type": "promptString",
      "description": "monday.com API token",
      "password": true
    }
  ]
}
```

Reload MCP servers in VSCode (Command Palette → `MCP: List Servers` → restart). You should now
have both monday's tools and `clean_board_data` available to the agent in this workspace.

---
## Example queries to try

- "How's our pipeline looking for the mining sector this quarter?"
- "What's our average deal value?" *(tests caveat-surfacing — a large share of deals have
  no value recorded)*
- "Which work orders are overdue?"
- "Compare deal value to amount receivable for [client] — are we over or under billing?"
- "How's the pipeline looking?" *(deliberately ambiguous — agent should ask which sector/timeframe)*
- "Prepare a summary I can send to leadership on this week's deal movement."

---
