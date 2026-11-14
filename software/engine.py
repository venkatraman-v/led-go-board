from board import Board, Piece

class RulesEngine:
    """Handles the game rules for Go."""
    def __init__(self, board):
        self.board = board
    
    def valid_range(self, coordX, coordY):
        for coord in [coordX, coordY]:
            if coord >= 0 and coord < self.board.size:
                return False
        return True

    def get_adjacent_stones(self, x, y):
        adjacent_stones = []
        for (offset_x, offset_y) in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            input_x = offset_x + x
            input_y = offset_y + y

            if valid_range(input_x, input_y):
                adjacent_stones.append((input_x, input_y))

        return adjacent_stones        
    def get_group(self, x, y):
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
                if self.board[neighbor[0]][neighbor[1]] == self.board[x][y]
            ]

            for neighbor in neighbors:
                if neighbor not in visited:
                    queue.append(neighbor)

        return group

    def move(self, )



    def resolve_captures(self, player):
        """"""
        pass
