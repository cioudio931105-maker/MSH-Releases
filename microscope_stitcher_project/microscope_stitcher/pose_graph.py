from __future__ import annotations

import numpy as np

from .types import PairEdge


def solve_positions(initial: np.ndarray, edges: list[PairEdge], anchor_weight: float = 0.04) -> np.ndarray:
    try:
        from scipy.sparse import lil_matrix
        from scipy.sparse.linalg import lsqr
    except Exception:
        return _solve_bfs(initial, edges)

    n = initial.shape[0]
    rows = len(edges) + n
    a = lil_matrix((rows, n), dtype=np.float64)
    bx = np.zeros(rows, dtype=np.float64)
    by = np.zeros(rows, dtype=np.float64)

    row = 0
    for edge in edges:
        weight = max(0.05, min(5.0, edge.score * 8.0)) if edge.success else 0.05
        a[row, edge.mov] = weight
        a[row, edge.ref] = -weight
        bx[row] = edge.dx * weight
        by[row] = edge.dy * weight
        row += 1

    for idx in range(n):
        a[row, idx] = anchor_weight
        bx[row] = initial[idx, 0] * anchor_weight
        by[row] = initial[idx, 1] * anchor_weight
        row += 1

    solved_x = lsqr(a.tocsr(), bx)[0]
    solved_y = lsqr(a.tocsr(), by)[0]
    result = np.column_stack([solved_x, solved_y])
    result[:, 0] -= np.min(result[:, 0])
    result[:, 1] -= np.min(result[:, 1])
    return result


def _solve_bfs(initial: np.ndarray, edges: list[PairEdge]) -> np.ndarray:
    n = initial.shape[0]
    positions = np.full((n, 2), np.nan, dtype=np.float64)
    positions[0] = initial[0]
    changed = True
    while changed:
        changed = False
        for edge in edges:
            if np.isfinite(positions[edge.ref, 0]) and not np.isfinite(positions[edge.mov, 0]):
                positions[edge.mov] = positions[edge.ref] + np.array([edge.dx, edge.dy])
                changed = True
            elif np.isfinite(positions[edge.mov, 0]) and not np.isfinite(positions[edge.ref, 0]):
                positions[edge.ref] = positions[edge.mov] - np.array([edge.dx, edge.dy])
                changed = True
    missing = ~np.isfinite(positions[:, 0])
    positions[missing] = initial[missing]
    positions[:, 0] -= np.min(positions[:, 0])
    positions[:, 1] -= np.min(positions[:, 1])
    return positions
