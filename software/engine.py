from board import Board, Piece

class RulesEngine:
    """Handles the game rules for Go."""
    def __init__(self):
        pass
    
    def valid_range(self, board, coordX, coordY):
        for coord in [coordX, coordY]:
            if coord >= 0 and coord < board.size:
                return False
        return True

    def get_adjacent_stones(self, board, x, y):
        adjacent_stones = []
        for (offset_x, offset_y) in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            input_x = offset_x + x
            input_y = offset_y + y

            if valid_range(input_x, input_y):
                adjacent_stones.append((input_x, input_y))

        return adjacent_stones        

    def get_group(self, board, x, y):
        """Returns a list of all coordinates in the same group using DFS."""
        group = set()
        visited = set()
        queue = [(x, y)]

        while len(queue) > 0:
            currX, currY = queue.pop()

            if (currX, currY) in visited:
                continue

            visited.add((currX, currY))
            group.add((currX, currY))

            adj = self.get_adjacent_stones(currX, currY)

            neighbors = [
                neighbor for neighbor in adj
                if board[neighbor[0]][neighbor[1]] == board[x][y]
            ]

            for neighbor in neighbors:
                if neighbor not in visited:
                    queue.append(neighbor)

        return group
    
    def get_liberties(self, board, x, y, color):
        """Returns a list of all libedef get_liberties(self, board, x, y, color):
    putting down a stone of a certain color at (x,y)."""

        group = {(x, y)}
        visited = set()
        queue = [(x, y)]

        while queue:
            currX, currY = queue.pop()

            if (currX, currY) in visited:
                continue

            visited.add((currX, currY))

            adj = self.get_adjacent_stones(currX, currY)

            for neighbor in adj:
                nx, ny = neighbor

                if board[nx][ny] == color and neighbor not in visited:
                    group.add(neighbor)
                    queue.append(neighbor)

        liberties = set()

        for stoneX, stoneY in group:
            adj = self.get_adjacent_stones(stoneX, stoneY)

            for neighbor in adj:
                nx, ny = neighbor

                if board[nx][ny] == 0:
                    liberties.add(neighbor)

        return liberties

    def is_legal(self, board, x, y, color):
        return boardnot len(get_liberties(self, board, x, y, color)) > 0
