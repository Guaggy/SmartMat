"""Plot-only interpolation of the real sensor grid."""

import numpy as np


def interpolate_grid(grid, method="None", scale=4):
    if method == "None" or scale == 1:
        return grid.copy()
    if method != "Linear" or scale < 1:
        raise ValueError("Choose None or Linear and a positive display scale")

    rows, cols = grid.shape
    dense_rows = (rows - 1) * scale + 1
    dense_cols = (cols - 1) * scale + 1
    row_positions = np.linspace(0, rows - 1, dense_rows)
    col_positions = np.linspace(0, cols - 1, dense_cols)
    left_rows = np.floor(row_positions).astype(int)
    left_cols = np.floor(col_positions).astype(int)
    right_rows = np.minimum(left_rows + 1, rows - 1)
    right_cols = np.minimum(left_cols + 1, cols - 1)
    row_fraction = (row_positions - left_rows)[:, None]
    col_fraction = (col_positions - left_cols)[None, :]
    top = grid[left_rows[:, None], left_cols[None, :]] * (1 - col_fraction)
    top += grid[left_rows[:, None], right_cols[None, :]] * col_fraction
    bottom = grid[right_rows[:, None], left_cols[None, :]] * (1 - col_fraction)
    bottom += grid[right_rows[:, None], right_cols[None, :]] * col_fraction
    return top * (1 - row_fraction) + bottom * row_fraction
