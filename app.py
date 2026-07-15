from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from server.room import RoomManager
from shared.game import GameError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tictactoe3d-server")

app = FastAPI(title="Tic Tac Toe 3D Online", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
manager = RoomManager()


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "Tic Tac Toe 3D Online",
        "status": "ok",
        "websocket": "/ws",
    }


@app.get("/health")
async def health() -> dict[str, object]:
    return {"status": "healthy", "active_rooms": len(manager.rooms)}


async def send_error(websocket: WebSocket, message: str, code: str = "error") -> None:
    await websocket.send_json({"type": code, "message": message})


async def handle_create_room(websocket: WebSocket) -> None:
    if manager.room_for(websocket) is not None:
        await send_error(websocket, "Ya estás dentro de una sala.")
        return

    room, player = await manager.create_room(websocket)
    await websocket.send_json(
        {
            "type": "room_created",
            "message": "Sala creada. Comparte el código con el Jugador 2.",
            "room_code": room.code,
            "symbol": player.symbol,
            "player_number": player.player_number,
            "state": room.snapshot(),
        }
    )


async def handle_join_room(websocket: WebSocket, message: dict[str, Any]) -> None:
    if manager.room_for(websocket) is not None:
        await send_error(websocket, "Ya estás dentro de una sala.")
        return

    room_code = str(message.get("room_code", "")).strip().upper()
    if not room_code:
        await send_error(websocket, "Debes escribir un código de sala.", "join_error")
        return

    try:
        room, player = await manager.join_room(websocket, room_code)
    except ValueError as exc:
        await send_error(websocket, str(exc), "join_error")
        return

    await websocket.send_json(
        {
            "type": "joined_room",
            "message": "Te uniste correctamente a la sala.",
            "room_code": room.code,
            "symbol": player.symbol,
            "player_number": player.player_number,
            "state": room.snapshot(),
        }
    )
    await room.broadcast(
        {
            "type": "game_started",
            "message": "Los dos jugadores están conectados. Comienza el Jugador 1 (X).",
            "state": room.snapshot(),
            "rematch": False,
        }
    )


async def handle_move(websocket: WebSocket, message: dict[str, Any]) -> None:
    room = manager.room_for(websocket)
    if room is None:
        await send_error(websocket, "No estás dentro de una sala.", "invalid_move")
        return

    symbol = room.symbol_for(websocket)
    if symbol is None:
        await send_error(websocket, "No se pudo identificar al jugador.", "invalid_move")
        return

    if not room.is_full:
        await send_error(websocket, "Debes esperar a que se conecte el otro jugador.", "invalid_move")
        return

    try:
        x = int(message.get("x"))
        y = int(message.get("y"))
        z = int(message.get("z"))
    except (TypeError, ValueError):
        await send_error(websocket, "Las coordenadas recibidas no son válidas.", "invalid_move")
        return

    async with room.lock:
        try:
            result = room.game.make_move(x, y, z, symbol)
        except GameError as exc:
            await send_error(websocket, str(exc), "invalid_move")
            return

        state = room.snapshot()
        await room.broadcast(
            {
                "type": "state_update",
                "message": f"Jugador {1 if symbol == 'X' else 2} colocó {symbol} en ({x}, {y}, {z}).",
                "last_move": {"x": x, "y": y, "z": z, "symbol": symbol},
                "state": state,
            }
        )

        if result.winner:
            await room.broadcast(
                {
                    "type": "game_over",
                    "message": f"Ganó el Jugador {1 if result.winner == 'X' else 2} ({result.winner}).",
                    "winner": result.winner,
                    "winning_line": [list(coord) for coord in result.winning_line or ()],
                    "state": state,
                }
            )
        elif result.is_draw:
            await room.broadcast(
                {
                    "type": "game_over",
                    "message": "La partida terminó en empate.",
                    "winner": None,
                    "winning_line": None,
                    "state": state,
                }
            )


async def handle_rematch(websocket: WebSocket) -> None:
    room = manager.room_for(websocket)
    if room is None:
        await send_error(websocket, "No estás dentro de una sala.", "rematch_error")
        return

    symbol = room.symbol_for(websocket)
    if symbol is None:
        await send_error(websocket, "No se pudo identificar al jugador.", "rematch_error")
        return

    async with room.lock:
        if not room.game.finished:
            await send_error(websocket, "La partida actual todavía no ha terminado.", "rematch_error")
            return
        if not room.is_full:
            await send_error(websocket, "El otro jugador ya no está conectado.", "rematch_error")
            return

        room.rematch_votes.add(symbol)
        await room.broadcast(
            {
                "type": "rematch_status",
                "message": f"{len(room.rematch_votes)} de 2 jugadores aceptaron la revancha.",
                "accepted": len(room.rematch_votes),
                "required": 2,
                "state": room.snapshot(),
            }
        )

        if len(room.rematch_votes) == 2:
            room.reset_for_rematch()
            await room.broadcast(
                {
                    "type": "game_started",
                    "message": "Ambos jugadores aceptaron. Comienza una nueva partida.",
                    "state": room.snapshot(),
                    "rematch": True,
                }
            )


async def handle_leave(websocket: WebSocket) -> None:
    room, symbol = await manager.remove_connection(websocket)
    if room is not None and room.players:
        await room.broadcast(
            {
                "type": "opponent_disconnected",
                "message": "El otro jugador salió de la sala. La partida fue cerrada.",
                "symbol": symbol,
            }
        )
        for player in list(room.players.values()):
            await manager.remove_connection(player.websocket)
            try:
                await player.websocket.close(code=1000)
            except Exception:
                pass
    await websocket.close(code=1000)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("Cliente conectado: %s", websocket.client)
    await websocket.send_json(
        {
            "type": "connected",
            "message": "Conexión con el servidor establecida.",
        }
    )

    try:
        while True:
            message = await websocket.receive_json()
            message_type = str(message.get("type", "")).strip().lower()

            if message_type == "create_room":
                await handle_create_room(websocket)
            elif message_type == "join_room":
                await handle_join_room(websocket, message)
            elif message_type == "move":
                await handle_move(websocket, message)
            elif message_type == "request_rematch":
                await handle_rematch(websocket)
            elif message_type == "leave_room":
                await handle_leave(websocket)
                return
            elif message_type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await send_error(websocket, "Tipo de mensaje no reconocido.")

    except WebSocketDisconnect:
        logger.info("Cliente desconectado: %s", websocket.client)
    except Exception:
        logger.exception("Error inesperado en la conexión WebSocket")
    finally:
        room, symbol = await manager.remove_connection(websocket)
        if room is not None and room.players:
            await room.broadcast(
                {
                    "type": "opponent_disconnected",
                    "message": "El otro jugador perdió la conexión. La sala fue cerrada.",
                    "symbol": symbol,
                }
            )
            for player in list(room.players.values()):
                await manager.remove_connection(player.websocket)
                try:
                    await player.websocket.close(code=1001)
                except Exception:
                    pass
