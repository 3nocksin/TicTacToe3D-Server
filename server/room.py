from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from shared.game import GameState

ROOM_CODE_LENGTH = 6
# Sin O/0 ni I/1 para que un código compartido sea fácil de leer por voz.
ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass
class PlayerConnection:
    websocket: WebSocket
    symbol: str
    player_number: int


@dataclass
class GameRoom:
    code: str
    game: GameState = field(default_factory=GameState)
    players: dict[str, PlayerConnection] = field(default_factory=dict)
    rematch_votes: set[str] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def is_full(self) -> bool:
        return len(self.players) == 2

    @property
    def status(self) -> str:
        if not self.is_full:
            return "waiting"
        if self.game.finished:
            return "finished"
        return "playing"

    def add_player(self, websocket: WebSocket) -> PlayerConnection:
        if "X" not in self.players:
            connection = PlayerConnection(websocket=websocket, symbol="X", player_number=1)
            self.players["X"] = connection
            return connection
        if "O" not in self.players:
            connection = PlayerConnection(websocket=websocket, symbol="O", player_number=2)
            self.players["O"] = connection
            return connection
        raise ValueError("La sala ya está llena.")

    def symbol_for(self, websocket: WebSocket) -> str | None:
        for symbol, player in self.players.items():
            if player.websocket is websocket:
                return symbol
        return None

    def remove_player(self, websocket: WebSocket) -> str | None:
        symbol = self.symbol_for(websocket)
        if symbol is not None:
            self.players.pop(symbol, None)
            self.rematch_votes.discard(symbol)
        return symbol

    def reset_for_rematch(self) -> None:
        self.game.reset()
        self.rematch_votes.clear()

    def snapshot(self) -> dict[str, Any]:
        return {
            "room_code": self.code,
            "players_connected": len(self.players),
            "rematch_votes": sorted(self.rematch_votes),
            "game": self.game.snapshot(status=self.status),
        }

    async def broadcast(self, message: dict[str, Any]) -> None:
        disconnected: list[WebSocket] = []
        for player in list(self.players.values()):
            try:
                await player.websocket.send_json(message)
            except Exception:
                disconnected.append(player.websocket)
        for websocket in disconnected:
            self.remove_player(websocket)


class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, GameRoom] = {}
        self.connection_rooms: dict[int, str] = {}
        self.lock = asyncio.Lock()

    @staticmethod
    def _connection_key(websocket: WebSocket) -> int:
        return id(websocket)

    def _generate_code(self) -> str:
        while True:
            code = "".join(secrets.choice(ROOM_ALPHABET) for _ in range(ROOM_CODE_LENGTH))
            if code not in self.rooms:
                return code

    async def create_room(self, websocket: WebSocket) -> tuple[GameRoom, PlayerConnection]:
        async with self.lock:
            code = self._generate_code()
            room = GameRoom(code=code)
            player = room.add_player(websocket)
            self.rooms[code] = room
            self.connection_rooms[self._connection_key(websocket)] = code
            return room, player

    async def join_room(
        self, websocket: WebSocket, room_code: str
    ) -> tuple[GameRoom, PlayerConnection]:
        normalized = room_code.strip().upper()
        async with self.lock:
            room = self.rooms.get(normalized)
            if room is None:
                raise ValueError("La sala no existe.")
            if room.is_full:
                raise ValueError("La sala ya tiene dos jugadores.")
            player = room.add_player(websocket)
            self.connection_rooms[self._connection_key(websocket)] = normalized
            return room, player

    def room_for(self, websocket: WebSocket) -> GameRoom | None:
        code = self.connection_rooms.get(self._connection_key(websocket))
        if code is None:
            return None
        return self.rooms.get(code)

    async def remove_connection(self, websocket: WebSocket) -> tuple[GameRoom | None, str | None]:
        async with self.lock:
            key = self._connection_key(websocket)
            code = self.connection_rooms.pop(key, None)
            if code is None:
                return None, None
            room = self.rooms.get(code)
            if room is None:
                return None, None
            symbol = room.remove_player(websocket)
            if not room.players:
                self.rooms.pop(code, None)
            return room, symbol
