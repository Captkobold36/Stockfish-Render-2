"""Hosted Stockfish MCP server for Render. Exposes bounded position and PGN analysis."""
import io
import os
import secrets
import asyncio
from pathlib import Path

import uvicorn
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

import chess
import chess.engine
import chess.pgn
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Stockfish Chess Coach")
ENGINE_PATH = os.getenv("STOCKFISH_PATH", "/usr/games/stockfish")


def san_line(board, moves):
    copy = board.copy()
    result = []
    for move in moves:
        if move not in copy.legal_moves:
            break
        result.append(copy.san(move))
        copy.push(move)
    return result


def score_view(score, pov):
    value = score.pov(pov)
    if value.is_mate():
        return {"type": "mate", "value": value.mate()}
    return {"type": "centipawns", "value": value.score()}


def analyze_board(board, depth, multipv):
    if not Path(ENGINE_PATH).exists():
        raise RuntimeError(f"Stockfish executable not found: {ENGINE_PATH}")
    with chess.engine.SimpleEngine.popen_uci(ENGINE_PATH) as engine:
        engine.configure({"Threads": 1})
        infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=multipv)
        if isinstance(infos, dict):
            infos = [infos]
        lines = []
        for info in infos:
            pv = info.get("pv", [])
            lines.append({
                "score_from_side_to_move": score_view(info["score"], board.turn),
                "depth": info.get("depth"),
                "nodes": info.get("nodes"),
                "best_move_uci": pv[0].uci() if pv else None,
                "principal_variation_uci": [m.uci() for m in pv[:12]],
                "principal_variation_san": san_line(board, pv[:12]),
            })
    return {
        "fen": board.fen(),
        "side_to_move": "white" if board.turn else "black",
        "is_check": board.is_check(),
        "legal_moves_count": board.legal_moves.count(),
        "lines": lines,
    }


@mcp.tool()
def analyze_position(fen: str, depth: int = 15, multipv: int = 3) -> dict:
    """Analyze a chess position with Stockfish. Input a FEN; returns evaluations, best moves, and principal variations."""
    if not 1 <= depth <= 22:
        raise ValueError("depth must be between 1 and 22 to keep free-tier requests bounded")
    if not 1 <= multipv <= 4:
        raise ValueError("multipv must be between 1 and 4")
    board = chess.Board(fen)
    if not board.is_valid():
        raise ValueError("FEN describes an invalid position")
    return analyze_board(board, depth, multipv)


@mcp.tool()
def analyze_pgn(pgn_text: str, depth: int = 10, max_plies: int = 120) -> dict:
    """Analyze a PGN game's main line using Stockfish. Returns each move's resulting position and evaluation."""
    if not 1 <= depth <= 16:
        raise ValueError("depth must be between 1 and 16 for PGN analysis on free hosting")
    if not 1 <= max_plies <= 160:
        raise ValueError("max_plies must be between 1 and 160")
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("Could not parse a PGN game")
    board = game.board()
    positions = []
    for ply, move in enumerate(game.mainline_moves()):
        if ply >= max_plies:
            break
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move near ply {ply + 1}")
        san = board.san(move)
        board.push(move)
        result = analyze_board(board, depth, 1)
        positions.append({
            "ply": ply + 1,
            "move_san": san,
            "fen_after_move": board.fen(),
            "engine": result["lines"][0] if result["lines"] else {},
        })
    return {
        "headers": dict(game.headers),
        "plies_analyzed": len(positions),
        "positions": positions,
        "note": "Evaluation is from the side-to-move perspective after each move.",
    }



def score_white_cp(score):
    """Convert a python-chess PovScore to a sortable White-perspective centipawn value."""
    white = score.pov(chess.WHITE)
    if white.is_mate():
        mate = white.mate() or 0
        return (10000 - min(abs(mate), 999)) * (1 if mate >= 0 else -1)
    return (white.score() or 0)


def review_game(pgn_text, depth=9, max_plies=100):
    """Review mainline moves, comparing engine evaluations before and after each move."""
    if not 1 <= depth <= 12:
        raise ValueError("Review depth must be between 1 and 12")
    if not 1 <= max_plies <= 100:
        raise ValueError("Review length must be between 1 and 100 plies")
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("Could not parse a PGN game")
    if game.errors:
        raise ValueError("PGN contains invalid moves: " + str(game.errors[0]))
    if not Path(ENGINE_PATH).exists():
        raise RuntimeError(f"Stockfish executable not found: {ENGINE_PATH}")
    board = game.board()
    moves = list(game.mainline_moves())[:max_plies]
    moments = []
    counts = {"blunders": 0, "mistakes": 0, "inaccuracies": 0}
    with chess.engine.SimpleEngine.popen_uci(ENGINE_PATH) as engine:
        engine.configure({"Threads": 1})
        for ply, move in enumerate(moves):
            if move not in board.legal_moves:
                raise ValueError(f"Illegal move near ply {ply + 1}")
            moving_color = board.turn
            before = engine.analyse(board, chess.engine.Limit(depth=depth))
            best_pv = before.get("pv", [])
            best_san = board.san(best_pv[0]) if best_pv and best_pv[0] in board.legal_moves else "—"
            before_cp = score_white_cp(before["score"])
            played_san = board.san(move)
            board.push(move)
            after = engine.analyse(board, chess.engine.Limit(depth=depth))
            after_cp = score_white_cp(after["score"])
            loss_cp = (before_cp - after_cp) if moving_color == chess.WHITE else (after_cp - before_cp)
            loss = max(0.0, loss_cp / 100.0)
            if loss >= 3.0:
                severity = "blunder"; counts["blunders"] += 1
            elif loss >= 1.5:
                severity = "mistake"; counts["mistakes"] += 1
            elif loss >= 0.7:
                severity = "inaccuracy"; counts["inaccuracies"] += 1
            else:
                continue
            player = "White" if moving_color == chess.WHITE else "Black"
            move_number = (ply // 2) + 1
            if loss >= 3:
                explanation = f"{player}'s {played_san} gave up about {loss:.1f} pawns of engine evaluation. Compare it with {best_san}, the engine's top move, and look for a hanging piece, missed tactic, or king-safety issue."
            elif loss >= 1.5:
                explanation = f"{played_san} appears to concede a significant advantage. {best_san} was the engine's preferred move; check forcing captures, checks, and threats before committing."
            else:
                explanation = f"{played_san} slightly worsened the position. {best_san} kept a better evaluation; compare piece activity and the opponent's strongest reply."
            moments.append({"ply": ply + 1, "move_number": f"{move_number}{'.' if moving_color == chess.WHITE else '...'}", "player": player, "move_san": played_san, "best_move": best_san, "loss": round(loss, 2), "severity": severity, "explanation": explanation})
    return {"headers": dict(game.headers), "plies_analyzed": len(moves), "depth": depth, "summary": counts, "moments": moments, "note": "Losses are approximate evaluation swings at limited depth; forced moves, tactical sequences, and engine horizon effects can produce false positives."}


def require_api_key(request):
    token = os.getenv("CHESS_API_KEY", "")
    supplied = request.headers.get("authorization", "")
    return len(token) >= 24 and secrets.compare_digest(supplied, "Bearer " + token)


async def homepage(request):
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


async def api_analyze_position(request):
    if not require_api_key(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        data = await request.json()
        fen = str(data.get("fen", ""))
        depth = int(data.get("depth", 15))
        multipv = int(data.get("multipv", 3))
        result = await asyncio.to_thread(analyze_position, fen, depth, multipv)
        return JSONResponse(result)
    except (ValueError, TypeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_review_pgn(request):
    if not require_api_key(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        data = await request.json()
        result = await asyncio.to_thread(review_game, str(data.get("pgn_text", "")), int(data.get("depth", 9)), int(data.get("max_plies", 100)))
        return JSONResponse(result)
    except (ValueError, TypeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


class BearerAuthMiddleware:
    """Require a private bearer token for all MCP HTTP requests."""
    def __init__(self, app, token):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith("/mcp"):
            headers = {k.lower(): v for k, v in scope.get("headers", [])}
            expected = ("Bearer " + self.token).encode()
            supplied = headers.get(b"authorization", b"")
            if not secrets.compare_digest(supplied, expected):
                body = b'{"error":"unauthorized"}'
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


if __name__ == "__main__":
    # A secret is mandatory so the public endpoint cannot be freely abused.
    token = os.getenv("CHESS_API_KEY", "")
    if len(token) < 24:
        raise SystemExit("Set CHESS_API_KEY to a random secret of at least 24 characters before starting.")
    engine_app = mcp.streamable_http_app()
    engine_app.routes.insert(0, Route("/", homepage, methods=["GET"]))
    engine_app.routes.insert(1, Route("/api/analyze-position", api_analyze_position, methods=["POST"]))
    engine_app.routes.insert(2, Route("/api/review-pgn", api_review_pgn, methods=["POST"]))
    app = engine_app
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
