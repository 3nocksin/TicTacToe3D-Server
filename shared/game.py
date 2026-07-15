from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

BOARD_SIZE = 4
EMPTY = ""
SYMBOLS = ("X", "O")
Coordinate = tuple[int, int, int]
WinningLine = tuple[Coordinate, Coordinate, Coordinate, Coordinate]


class GameError(ValueError):
    """Error de validación producido por una jugada inválida."""


def coordinate_to_index(x: int, y: int, z: int) -> int:
    """Convierte una coordenada (x, y, z) al índice plano del tablero."""
    if not all(isinstance(value, int) for value in (x, y, z)):
        raise GameError("Las coordenadas deben ser números enteros.")
    if not all(0 <= value < BOARD_SIZE for value in (x, y, z)):
        raise GameError("Las coordenadas deben estar entre 0 y 3.")
    return z * BOARD_SIZE * BOARD_SIZE + y * BOARD_SIZE + x


def index_to_coordinate(index: int) -> Coordinate:
    """Convierte un índice plano del tablero a una coordenada (x, y, z)."""
    if not isinstance(index, int) or not 0 <= index < BOARD_SIZE**3:
        raise GameError("El índice debe estar entre 0 y 63.")
    z, remainder = divmod(index, BOARD_SIZE * BOARD_SIZE)
    y, x = divmod(remainder, BOARD_SIZE)
    return x, y, z


def _line(*coords: Coordinate) -> WinningLine:
    return tuple(coords)  # type: ignore[return-value]


def generate_winning_lines() -> tuple[WinningLine, ...]:
    """Genera las 76 líneas ganadoras posibles en un cubo 4×4×4."""
    lines: list[WinningLine] = []

    # Rectas paralelas a X, Y y Z: 16 por eje.
    for z in range(BOARD_SIZE):
        for y in range(BOARD_SIZE):
            lines.append(_line(*((x, y, z) for x in range(BOARD_SIZE))))

    for z in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            lines.append(_line(*((x, y, z) for y in range(BOARD_SIZE))))

    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            lines.append(_line(*((x, y, z) for z in range(BOARD_SIZE))))

    # Diagonales en planos XY (Z fijo): 8.
    for z in range(BOARD_SIZE):
        lines.append(_line(*((i, i, z) for i in range(BOARD_SIZE))))
        lines.append(_line(*((i, BOARD_SIZE - 1 - i, z) for i in range(BOARD_SIZE))))

    # Diagonales en planos XZ (Y fijo): 8.
    for y in range(BOARD_SIZE):
        lines.append(_line(*((i, y, i) for i in range(BOARD_SIZE))))
        lines.append(_line(*((i, y, BOARD_SIZE - 1 - i) for i in range(BOARD_SIZE))))

    # Diagonales en planos YZ (X fijo): 8.
    for x in range(BOARD_SIZE):
        lines.append(_line(*((x, i, i) for i in range(BOARD_SIZE))))
        lines.append(_line(*((x, i, BOARD_SIZE - 1 - i) for i in range(BOARD_SIZE))))

    # Cuatro diagonales que atraviesan el cubo completo.
    lines.extend(
        [
            _line(*((i, i, i) for i in range(BOARD_SIZE))),
            _line(*((i, i, BOARD_SIZE - 1 - i) for i in range(BOARD_SIZE))),
            _line(*((i, BOARD_SIZE - 1 - i, i) for i in range(BOARD_SIZE))),
            _line(
                *((i, BOARD_SIZE - 1 - i, BOARD_SIZE - 1 - i) for i in range(BOARD_SIZE))
            ),
        ]
    )

    unique = tuple(dict.fromkeys(lines))
    if len(unique) != 76:
        raise AssertionError(f"Se esperaban 76 líneas ganadoras y se generaron {len(unique)}.")
    return unique


WINNING_LINES = generate_winning_lines()


@dataclass(frozen=True)
class MoveResult:
    accepted: bool
    x: int
    y: int
    z: int
    symbol: str
    winner: str | None
    winning_line: WinningLine | None
    is_draw: bool
    next_turn: str | None


class GameState:
    """Motor autoritativo del Tic Tac Toe 3D, sin interfaz ni red."""

    def __init__(self) -> None:
        self.board: list[str] = [EMPTY] * (BOARD_SIZE**3)
        self.current_turn = "X"
        self.winner: str | None = None
        self.winning_line: WinningLine | None = None
        self.is_draw = False
        self.move_count = 0

    @property
    def finished(self) -> bool:
        return self.winner is not None or self.is_draw

    def reset(self) -> None:
        self.board = [EMPTY] * (BOARD_SIZE**3)
        self.current_turn = "X"
        self.winner = None
        self.winning_line = None
        self.is_draw = False
        self.move_count = 0

    def get_cell(self, x: int, y: int, z: int) -> str:
        return self.board[coordinate_to_index(x, y, z)]

    def make_move(self, x: int, y: int, z: int, symbol: str) -> MoveResult:
        if symbol not in SYMBOLS:
            raise GameError("El símbolo debe ser X u O.")
        if self.finished:
            raise GameError("La partida ya terminó.")
        if symbol != self.current_turn:
            raise GameError("No es el turno de ese jugador.")

        index = coordinate_to_index(x, y, z)
        if self.board[index] != EMPTY:
            raise GameError("La casilla seleccionada ya está ocupada.")

        self.board[index] = symbol
        self.move_count += 1
        self.winning_line = self._find_winning_line(symbol)

        if self.winning_line is not None:
            self.winner = symbol
            return MoveResult(
                accepted=True,
                x=x,
                y=y,
                z=z,
                symbol=symbol,
                winner=symbol,
                winning_line=self.winning_line,
                is_draw=False,
                next_turn=None,
            )

        if self.move_count == BOARD_SIZE**3:
            self.is_draw = True
            return MoveResult(
                accepted=True,
                x=x,
                y=y,
                z=z,
                symbol=symbol,
                winner=None,
                winning_line=None,
                is_draw=True,
                next_turn=None,
            )

        self.current_turn = "O" if symbol == "X" else "X"
        return MoveResult(
            accepted=True,
            x=x,
            y=y,
            z=z,
            symbol=symbol,
            winner=None,
            winning_line=None,
            is_draw=False,
            next_turn=self.current_turn,
        )

    def _find_winning_line(self, symbol: str) -> WinningLine | None:
        for line in WINNING_LINES:
            if all(self.get_cell(x, y, z) == symbol for x, y, z in line):
                return line
        return None

    def load_board(
        self,
        cells: Sequence[str],
        *,
        current_turn: str = "X",
        move_count: int | None = None,
    ) -> None:
        """Carga un tablero para pruebas o recuperación controlada."""
        if len(cells) != BOARD_SIZE**3:
            raise GameError("El tablero debe contener exactamente 64 casillas.")
        if any(cell not in (EMPTY, *SYMBOLS) for cell in cells):
            raise GameError("El tablero contiene símbolos no válidos.")
        if current_turn not in SYMBOLS:
            raise GameError("El turno actual debe ser X u O.")

        self.board = list(cells)
        self.current_turn = current_turn
        self.move_count = move_count if move_count is not None else sum(cell != EMPTY for cell in cells)
        self.winner = None
        self.winning_line = None
        self.is_draw = False

        for symbol in SYMBOLS:
            line = self._find_winning_line(symbol)
            if line is not None:
                self.winner = symbol
                self.winning_line = line
                break
        if self.winner is None and self.move_count == BOARD_SIZE**3:
            self.is_draw = True

    def snapshot(self, status: str = "playing") -> dict[str, object]:
        return {
            "board": self.board.copy(),
            "current_turn": self.current_turn,
            "winner": self.winner,
            "winning_line": [list(coord) for coord in self.winning_line]
            if self.winning_line
            else None,
            "is_draw": self.is_draw,
            "move_count": self.move_count,
            "finished": self.finished,
            "status": status,
        }


def line_as_indices(line: Iterable[Coordinate]) -> tuple[int, ...]:
    return tuple(coordinate_to_index(*coord) for coord in line)
