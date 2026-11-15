from board import Board, Piece


class RulesEngine:
    """Handles the game rules for Go.

    The engine is stateless: every method receives the board it should inspect.
    Moves are applied transactionally by :meth:`apply_move`, which returns the
    stones that were captured.
    """

    NEIGHBOUR_OFFSETS = ((-1, 0), (1, 0), (0, -1), (0, 1))

    def valid_range(self, board: Board, coord_x: int, coord_y: int) -> bool:
        """Returns True if the coordinate is inside the board."""
        return board.is_valid_position(coord_x, coord_y)

    def get_adjacent_stones(self, board: Board, x: int, y: int) -> list:
        """Returns the coordinates directly adjacent to ``(x, y)``."""
        adjacent = []
        for offset_x, offset_y in self.NEIGHBOUR_OFFSETS:
            neighbour = (x + offset_x, y + offset_y)
            if self.valid_range(board, *neighbour):
                adjacent.append(neighbour)
        return adjacent

    def get_group(self, board: Board, x: int, y: int) -> set:
        """Returns all coordinates in the same group using DFS.

        An empty or invalid starting point has no group.
        """
        color = board.stone_at(x, y)
        if color not in (Piece.BLUE, Piece.RED):
            return set()

        group = set()
        visited = set()
        stack = [(x, y)]

        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            group.add(current)

            for neighbour in self.get_adjacent_stones(board, *current):
                if neighbour not in visited and board.stone_at(*neighbour) is color:
                    stack.append(neighbour)

        return group

    def get_liberties(self, board: Board, x: int, y: int, color: Piece = None) -> set:
        """Returns the empty intersections adjacent to a group.

        ``color`` may be supplied to inspect a hypothetical stone that has not
        been placed on the board yet.
        """
        if color is None:
            color = board.stone_at(x, y)
        if color not in (Piece.BLUE, Piece.RED):
            return set()
        if not board.is_valid_position(x, y):
            return set()

        if board.stone_at(x, y) is Piece.EMPTY:
            # The stone has not been placed yet.  Treat the origin as a stone
            # of ``color`` so hypothetical moves can be checked.
            group = {(x, y)}
            visited = {(x, y)}
            stack = self.get_adjacent_stones(board, x, y)
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                if board.stone_at(*current) is color:
                    group.add(current)
                    stack.extend(self.get_adjacent_stones(board, *current))
        else:
            group = self.get_group(board, x, y)
            if not group:
                return set()

        liberties = set()
        for stone_x, stone_y in group:
            for neighbour in self.get_adjacent_stones(board, stone_x, stone_y):
                if board.stone_at(*neighbour) is Piece.EMPTY:
                    liberties.add(neighbour)
        return liberties

    def _group_has_liberties(self, board: Board, group: set) -> bool:
        """Returns True if any stone in ``group`` has an adjacent empty point."""
        for stone_x, stone_y in group:
            for neighbour in self.get_adjacent_stones(board, stone_x, stone_y):
                if board.stone_at(*neighbour) is Piece.EMPTY:
                    return True
        return False

    def get_captured_stones(self, board: Board, x: int, y: int, color: Piece) -> set:
        """Opponent stones captured by ``color`` playing at ``(x, y)``.

        The move is applied to a copy of the board so the caller's board is
        never mutated.  The returned set is empty for illegal placements.
        """
        if not board.is_valid_move(x, y):
            return set()

        simulated = board.copy()
        simulated.place_stone(x, y, color)
        captured = set()
        opponent = color.opponent

        for neighbour in self.get_adjacent_stones(simulated, x, y):
            if simulated.stone_at(*neighbour) is not opponent:
                continue
            group = self.get_group(simulated, *neighbour)
            if group and not self._group_has_liberties(simulated, group):
                captured |= group

        return captured

    def is_suicide(self, board: Board, x: int, y: int, color: Piece) -> bool:
        """Returns True if the move would leave its own group without liberties."""
        if not board.is_valid_move(x, y):
            return True

        simulated = board.copy()
        self.apply_move(simulated, x, y, color)
        # The stone is always present after apply_move (it may capture a
        # neighbouring group, but it can never remove itself).
        return len(self.get_liberties(simulated, x, y, color)) == 0

    def is_legal(
        self,
        board: Board,
        x: int,
        y: int,
        color: Piece,
        ko_point: tuple | None = None,
    ) -> bool:
        """Returns True if ``color`` may play at ``(x, y)``."""
        if color not in (Piece.BLUE, Piece.RED):
            return False
        if not board.is_valid_move(x, y):
            return False
        if ko_point is not None and (x, y) == tuple(ko_point):
            return False
        return not self.is_suicide(board, x, y, color)

    def apply_move(self, board: Board, x: int, y: int, color: Piece) -> set:
        """Places a stone and removes any captured groups.

        The board is mutated in place.  The caller is responsible for checking
        legality first.  Returns the set of captured coordinates.
        """
        if not board.place_stone(x, y, color):
            return set()

        captured = set()
        opponent = color.opponent

        for neighbour in self.get_adjacent_stones(board, x, y):
            if board.stone_at(*neighbour) is not opponent:
                continue
            group = self.get_group(board, *neighbour)
            if group and not self._group_has_liberties(board, group):
                captured |= group

        for stone_x, stone_y in captured:
            board.remove_stone(stone_x, stone_y)

        return captured

    def ko_point(self, board: Board, x: int, y: int, color: Piece, captured: set) -> tuple | None:
        """Returns the point forbidden by the simple ko rule, if any.

        ``board`` is the position after the move and ``captured`` the stones
        that move removed.  A ko occurs when exactly one stone is captured and
        the capturing group is a single stone with one liberty: the captured
        point.  The opponent may not immediately recapture there.
        """
        if len(captured) != 1:
            return None
        group = self.get_group(board, x, y)
        if group != {(x, y)}:
            return None
        liberties = self.get_liberties(board, x, y, color)
        if len(liberties) != 1:
            return None
        return next(iter(liberties))
