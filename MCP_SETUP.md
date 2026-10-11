# Stockfish MCP Connector Setup

This repository's `server.py` already implements a remote MCP server using the
Python MCP SDK. It exposes the MCP endpoint at:

`https://stockfish-render.onrender.com/mcp`

## Connect it to Claude

Claude's custom remote MCP connectors are available on the Free plan, with a
limit of one custom connector. (Availability and UI labels can change.)

1. Open Claude and go to **Settings → Connectors** (sometimes **Customize → Connectors**).
2. Choose **Add custom connector**.
3. Name it `Stockfish Chess Coach`.
4. Use this connector URL:

   `https://stockfish-render.onrender.com/mcp`

5. In authentication/request headers, configure a fixed header:
   - Header name: `Authorization`
   - Header value: `Bearer YOUR_CHESS_API_KEY`

   Replace `YOUR_CHESS_API_KEY` with the value of the `CHESS_API_KEY` environment
   variable already stored in Render. Do not paste the key into GitHub, this
   README, or a public chat.
6. Save/connect, then enable the connector in a conversation.
7. Ask Claude to list the available Stockfish tools or analyze a position.

## Available tools

- `analyze_position`: Analyze a FEN position. Optional `depth` (1–22) and
  `multipv` (1–4). Higher depth takes longer; the hosted service is intentionally
  bounded for free-tier resources.
- `analyze_pgn`: Analyze a PGN main line with bounded depth and number of plies.

The same service also exposes the existing HTTP endpoints:
- `POST /api/analyze-position`
- `POST /api/review-pgn`

Both HTTP endpoints also require `Authorization: Bearer YOUR_CHESS_API_KEY`.

## Important security notes

- Keep `CHESS_API_KEY` in Render's Environment settings only.
- Do not commit the secret to GitHub.
- If the key has ever been exposed, rotate it in Render and update the connector's
  request header.
- The Render service must be running and reachable over HTTPS for Claude to connect.

## Do I need another MCP server file?

No. `server.py` already registers the MCP tools and serves the remote MCP endpoint.
Adding a second `mcp_server.py` would duplicate the existing implementation and
could cause deployment confusion. This document is the only repository addition
needed for setup instructions.
