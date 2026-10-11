# Stockfish Studio — Render deployment

A private, browser-based chess analysis workspace backed by Stockfish. The same service exposes MCP tools for a custom GPT.

## Features
- Interactive board with legal move highlighting, drag-and-drop, board flip, and move navigation.
- Position analysis with multiple Stockfish candidate lines.
- PGN import in the browser and engine-based game review with evaluation-loss flags.
- Authenticated JSON API and MCP endpoint.
- No game database: PGNs and positions are processed in memory and are not intentionally saved by this app.

## Deploy to Render
1. Unzip this package on your computer.
2. Upload the **contents** of the unzipped folder to the **root of your GitHub repository**. The repository's main page should directly show `Dockerfile`, `server.py`, `requirements.txt`, `render.yaml`, and the `static` folder. Do not upload only the ZIP file or nest everything inside another folder.
3. In Render, create a **Web Service** from that GitHub repository. Select Docker as the runtime and Free plan if offered.
4. Add the environment variable `CHESS_API_KEY` with a long random secret (at least 24 characters). Do not commit the secret to GitHub.
5. Deploy. The public home page is the chess UI. The MCP endpoint remains `https://YOUR-SERVICE.onrender.com/mcp`.
6. Open the UI, choose **API settings**, enter the Render URL and the same `CHESS_API_KEY`, and select **Save & test**.

## API routes
- `GET /` — Stockfish Studio UI.
- `POST /api/analyze-position` — JSON body `{ "fen": "...", "depth": 15, "multipv": 3 }`.
- `POST /api/review-pgn` — JSON body `{ "pgn_text": "...", "depth": 9, "max_plies": 100 }`.
- `POST /mcp` — Streamable HTTP MCP endpoint with `Authorization: Bearer YOUR_CHESS_API_KEY`.

The UI stores the service URL and API key in the current browser tab's `sessionStorage` and sends authenticated requests directly to the Render service. It does not put the key into the HTML or repository. Anyone with the key can use the private engine API, so protect it. Do not paste the key into public issues or chat.

## Cost and limitations
The Render free instance may sleep while idle and take time to wake up. Analysis depth and review length are capped to reduce CPU usage. The board uses the chess.js browser library from a public CDN, so the first UI load requires an internet connection. Review flags are heuristics based on evaluation loss at limited depth; they are not guaranteed to identify every mistake correctly.

## Stockfish license
Stockfish is GPLv3 software. This deployment installs Stockfish from the Debian package repository at build time; review the package's license and comply with applicable distribution obligations.
