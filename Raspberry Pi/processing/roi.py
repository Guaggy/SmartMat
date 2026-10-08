"""A region of interest is a set of cells: a boolean mask the size of the mat."""

import numpy as np


def rectangle_mask(shape, first, second):
    """Cells in the box spanned by two (row, col) cells, in any order"""
    mask = np.zeros(shape, dtype=bool)
    row0, row1 = sorted((first[0], second[0]))
    col0, col1 = sorted((first[1], second[1]))
    mask[max(row0, 0):max(row1 + 1, 0), max(col0, 0):max(col1 + 1, 0)] = True
    return mask


def polygon_mask(shape, corners):
    """Cells whose centre is inside or on the outline of the polygon through (row, col) corners"""
    mask = np.zeros(shape, dtype=bool)
    if len(corners) < 3:
        return mask
    edges = list(zip(corners, list(corners[1:]) + [corners[0]]))
    for row in range(shape[0]):
        for col in range(shape[1]):
            inside = False
            for (row1, col1), (row2, col2) in edges:
                cross = (col2 - col1) * (row - row1) - (row2 - row1) * (col - col1)
                if (cross == 0 and min(row1, row2) <= row <= max(row1, row2)
                        and min(col1, col2) <= col <= max(col1, col2)):
                    inside = True  # on the outline
                    break
                if (row1 > row) != (row2 > row) and col < (col2 - col1) * (row - row1) / (row2 - row1) + col1:
                    inside = not inside
            mask[row, col] = inside
    return mask


def stroke_cells(first, second):
    """Cells on the straight line between two (row, col) cells, so a fast drag leaves no gaps"""
    steps = max(abs(second[0] - first[0]), abs(second[1] - first[1]))
    if steps == 0:
        return [tuple(first)]
    return [(round(first[0] + (second[0] - first[0]) * step / steps),
             round(first[1] + (second[1] - first[1]) * step / steps)) for step in range(steps + 1)]


def cells_mask(shape, cells):
    """Mask of the given (row, col) cells; cells outside the grid are ignored"""
    mask = np.zeros(shape, dtype=bool)
    for row, col in cells:
        if 0 <= row < shape[0] and 0 <= col < shape[1]:
            mask[row, col] = True
    return mask


def mask_to_cells(mask):
    """Sorted [[row, col], ...] of the selected cells, for JSON"""
    return [[int(row), int(col)] for row, col in np.argwhere(mask)]


def roi_centre(mask):
    """Mean (row, col) position of the selected cells"""
    rows, cols = np.nonzero(mask)
    return float(rows.mean()), float(cols.mean())


def _side(positions, centre):
    """Share of each row/column that lies before the centre: 1, 0, or 0.5 on the dividing line"""
    return np.where(positions < centre, 1.0, np.where(positions == centre, 0.5, 0.0))


def roi_balance(grid, mask):
    """How the load inside the region is shared around the region's own centre, None without load.

    x and y run -1..1; right and up (as drawn on screen) are positive.
    """
    values = np.where(mask & np.isfinite(grid), np.maximum(grid, 0), 0.0)
    total = float(values.sum())
    if total <= 0:
        return None
    centre_row, centre_col = roi_centre(mask)
    upper = _side(np.arange(grid.shape[0]), centre_row)[:, None]
    left = _side(np.arange(grid.shape[1]), centre_col)[None, :]

    def share(weights):
        return float((values * weights).sum() / total * 100)

    left_share, upper_share = share(left), share(upper)
    return {
        "left": left_share, "right": 100 - left_share,
        "upper": upper_share, "lower": 100 - upper_share,
        "quadrants": {"upper_left": share(upper * left), "upper_right": share(upper * (1 - left)),
                      "lower_left": share((1 - upper) * left), "lower_right": share((1 - upper) * (1 - left))},
        "x": (100 - 2 * left_share) / 100, "y": (2 * upper_share - 100) / 100,
    }
