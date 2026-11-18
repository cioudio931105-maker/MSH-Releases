from __future__ import annotations

from typing import Optional

import cv2
import numpy as np


def autocrop_black(img: np.ndarray, crop: bool = True, thr: int = 1) -> np.ndarray:
    """將拼接後的黑邊裁掉，只保留非零區域的最小外接矩形。

    Args:
        img: 輸入影像
        crop: 是否裁切黑邊（預設 True；False 時保留黑邊）
        thr: 黑色門檻值，<=thr 視為黑
    """
    if not crop:
        return img

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thr = int(max(1, thr))
    _, mask = cv2.threshold(gray, thr, 255, cv2.THRESH_BINARY)
    coords = cv2.findNonZero(mask)
    if coords is None:
        return img
    x, y, w, h = cv2.boundingRect(coords)
    return img[y : y + h, x : x + w]


def trim_dark_borders(
    img: np.ndarray,
    thr: int = 25,
    frac: float = 0.20,
    max_trim: int = 5,
) -> np.ndarray:
    """裁掉四周「明顯偏黑」的細邊界（通常是 1px 黑線）。

    - 只會從外框向內裁切（不會改動內部）
    - 以每一條邊界 row/col 的暗像素比例判斷，超過 frac 才會裁
    """
    if img is None or img.size == 0:
        return img

    out = img
    for _ in range(max_trim):
        if out is None or out.size == 0:
            return out
        h, w = out.shape[:2]
        if h <= 2 or w <= 2:
            return out

        gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
        dark = (gray < thr)

        top_frac = float(dark[0, :].mean())
        bottom_frac = float(dark[-1, :].mean())
        left_frac = float(dark[:, 0].mean())
        right_frac = float(dark[:, -1].mean())

        # 逐次最多裁一邊，避免一次裁太多
        if top_frac > frac:
            out = out[1:, :]
            continue
        if bottom_frac > frac:
            out = out[:-1, :]
            continue
        if left_frac > frac:
            out = out[:, 1:]
            continue
        if right_frac > frac:
            out = out[:, :-1]
            continue

        break

    return out


def fill_inner_black(
    img: np.ndarray,
    thr: int = 10,
    min_area_ratio: float = 0.0005,
    max_area_ratio: float = 0.08,
    dilate: int = 2,
    open_ksize: int = 0,
    sat_thr: int = 0,
    dark_thr: int = 0,
    dark_sat_thr: int = 0,
    local_diff_thr: int = 0,
    local_diff_sigma: float = 9.0,
    local_gray_max: float = 0.0,
) -> np.ndarray:
    """Fill internal black holes using inpainting."""
    if img is None or img.size == 0:
        return img

    h, w = img.shape[:2]
    if h < 10 or w < 10:
        return img

    thr = int(max(1, thr))
    min_area_ratio = float(max(0.0, min_area_ratio))
    max_area_ratio = float(max(min_area_ratio, max_area_ratio))
    dilate = int(max(0, dilate))
    open_ksize = int(max(0, open_ksize))
    if open_ksize > 1 and open_ksize % 2 == 0:
        open_ksize += 1
    sat_thr = int(max(0, sat_thr))
    dark_thr = int(max(0, dark_thr))
    dark_sat_thr = int(max(0, dark_sat_thr))

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    base_mask = (gray <= thr).astype(np.uint8)

    hsv = None
    if sat_thr > 0 or dark_sat_thr > 0:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    def build_fill(mask: np.ndarray, gray_limit: float | None = None) -> np.ndarray:
        mask_proc = mask
        if open_ksize > 1:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_ksize, open_ksize))
            mask_proc = cv2.morphologyEx(mask_proc, cv2.MORPH_OPEN, k, iterations=1)
        if not np.any(mask_proc):
            return np.zeros_like(gray, dtype=np.uint8)

        num, labels, stats, _ = cv2.connectedComponentsWithStats(mask_proc, connectivity=8)
        if num <= 1:
            return np.zeros_like(gray, dtype=np.uint8)

        total = h * w
        min_area = max(1, int(min_area_ratio * total))
        max_area = max(min_area, int(max_area_ratio * total))
        out = np.zeros_like(gray, dtype=np.uint8)

        for i in range(1, num):
            x, y, ww, hh, area = stats[i]
            if area < min_area or area > max_area:
                continue
            if x <= 0 or y <= 0 or (x + ww) >= w or (y + hh) >= h:
                continue
            if gray_limit is not None:
                comp = labels == i
                if float(gray[comp].mean()) > gray_limit:
                    continue
            out[labels == i] = 255

        return out

    if hsv is not None and sat_thr > 0:
        sat_mask = (base_mask & (hsv[:, :, 1] <= sat_thr)).astype(np.uint8)
        fill_mask_sat = build_fill(sat_mask)
        fill_mask_base = build_fill(base_mask)
        if (not np.any(fill_mask_sat)) or (fill_mask_sat.sum() < 0.5 * fill_mask_base.sum()):
            fill_mask = fill_mask_base
        else:
            fill_mask = fill_mask_sat
    else:
        fill_mask = build_fill(base_mask)

    if dark_thr > 0:
        dark_mask = (gray <= float(dark_thr)).astype(np.uint8)
        if hsv is not None and dark_sat_thr > 0:
            dark_mask = (dark_mask & (hsv[:, :, 1] <= dark_sat_thr)).astype(np.uint8)
        if np.any(dark_mask):
            fill_mask_dark = build_fill(dark_mask)
            if np.any(fill_mask_dark):
                if not np.any(fill_mask):
                    fill_mask = fill_mask_dark
                else:
                    fill_mask = cv2.bitwise_or(fill_mask, fill_mask_dark)

    local_diff_thr = int(max(0, local_diff_thr))
    local_diff_sigma = float(max(0.1, local_diff_sigma))
    local_gray_max = float(max(0.0, local_gray_max))
    if local_diff_thr > 0:
        blur = cv2.GaussianBlur(gray, (0, 0), local_diff_sigma)
        diff = blur - gray
        local_mask = (diff > float(local_diff_thr)).astype(np.uint8)
        gray_limit = local_gray_max if local_gray_max > 0 else None
        fill_mask_local = build_fill(local_mask, gray_limit=gray_limit)
        if np.any(fill_mask_local):
            if not np.any(fill_mask):
                fill_mask = fill_mask_local
            else:
                fill_mask = cv2.bitwise_or(fill_mask, fill_mask_local)

    if not np.any(fill_mask):
        return img

    if dilate > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilate + 1, 2 * dilate + 1))
        fill_mask = cv2.dilate(fill_mask, k, iterations=1)

    return cv2.inpaint(img, fill_mask, 3, cv2.INPAINT_TELEA)


def repair_top_vertical_dark_line(
    img: np.ndarray,
    top_frac: float = 0.35,
    thr: int = 25,
    band: int = 2,
    col_frac_thr: float = 0.06,
    x_range_frac: Optional[tuple[float, float]] = None,
    min_dip: float = 3.0,
    min_dark_frac: float = 0.002,
    px_dip_thr: float = 8.0,
) -> np.ndarray:
    """修補「上方區域」出現的細垂直黑線（通常是拼接縫殘留）。

    只在影像上方 top_frac 的高度內：
    - 偵測暗像素比例最高的 column
    - 若足夠顯著，僅替換該 column 附近 band 範圍內的「暗像素」
    - 以左右相鄰欄像素做拷貝/平均，不做模糊
    """
    if img is None or img.size == 0:
        return img

    h, w = img.shape[:2]
    if h < 10 or w < 10:
        return img

    h_top = int(max(1, min(h, round(h * top_frac))))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    dark = (gray < thr)

    top_dark = dark[:h_top, :]
    col_top = top_dark.mean(axis=0)

    # 限制偵測區段（例如使用者指出 1/7 位置附近）
    x_start = 1
    x_end = w - 2
    if x_range_frac is not None:
        lo, hi = x_range_frac
        lo = float(max(0.0, min(1.0, lo)))
        hi = float(max(0.0, min(1.0, hi)))
        if hi < lo:
            lo, hi = hi, lo
        x_start = max(1, int(round(w * lo)))
        x_end = min(w - 2, int(round(w * hi)))
        if x_end <= x_start:
            return img

    # 更敏感：看「比左右欄更暗」的 dip（避免黑線很細但不一定是純黑）
    top_gray = gray[:h_top, :].astype(np.float32)
    col_mean = top_gray.mean(axis=0)
    best_x = None
    best_score = -1.0
    for xx in range(x_start, x_end + 1):
        dip = float((col_mean[xx - 1] + col_mean[xx + 1]) * 0.5 - col_mean[xx])
        df = float(col_top[xx])
        # 舊條件：暗像素比例很高
        if df >= col_frac_thr:
            score = df * 1000.0 + dip
        else:
            # 新條件：暗比例不高但有明顯 dip
            if dip < min_dip:
                continue
            score = dip * (0.1 + df * 10.0)

        if score > best_score:
            best_score = score
            best_x = xx

    if best_x is None:
        return img

    x = int(best_x)

    x0 = max(0, x - band)
    x1 = min(w - 1, x + band)
    left = x0 - 1
    right = x1 + 1
    if left < 0 and right >= w:
        return img

    out = img.copy()

    for y in range(h_top):
        # replacement color from neighbor columns
        if 0 <= left < w and 0 <= right < w:
            repl = ((out[y, left, :].astype(np.uint16) + out[y, right, :].astype(np.uint16)) // 2).astype(np.uint8)
        elif 0 <= left < w:
            repl = out[y, left, :]
        elif 0 <= right < w:
            repl = out[y, right, :]
        else:
            continue
        # 以「相對左右更暗」作為修補條件（可處理非純黑的 seam）
        if 0 <= left < w and 0 <= right < w:
            neigh = (gray[y, left].astype(np.float32) + gray[y, right].astype(np.float32)) * 0.5
        elif 0 <= left < w:
            neigh = gray[y, left].astype(np.float32)
        elif 0 <= right < w:
            neigh = gray[y, right].astype(np.float32)
        else:
            neigh = None

        for xx in range(x0, x1 + 1):
            if neigh is not None:
                if float(gray[y, xx]) < float(neigh) - float(px_dip_thr):
                    out[y, xx, :] = repl
            else:
                # 退化情況：只能用絕對暗像素判斷
                if dark[y, xx]:
                    out[y, xx, :] = repl

    return out


def repair_vertical_band_if_needed(
    img: np.ndarray,
    x_center: int,
    top_frac: float = 0.20,
    band: int = 2,
    px_dip_thr: float = 6.0,
    min_hits: int = 10,
) -> np.ndarray:
    """在指定 x 位置附近修補上方垂直暗帶（僅在偵測到明顯暗像素時才動手）。

    用途：使用者已指出明確位置（例如 1/7 處），但自動偵測不一定抓得到。
    修補條件採「相對左右更暗」以避免模糊。
    """
    if img is None or img.size == 0:
        return img
    h, w = img.shape[:2]
    if h < 10 or w < 10:
        return img

    x_center = int(np.clip(x_center, 0, w - 1))
    h_top = int(max(1, min(h, round(h * top_frac))))
    x0 = max(0, x_center - band)
    x1 = min(w - 1, x_center + band)
    left = x0 - 1
    right = x1 + 1
    if left < 0 and right >= w:
        return img

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    top = gray[:h_top, :]

    # 計算需要修補的像素數（hits），太少就不動
    hits = 0
    for y in range(h_top):
        if 0 <= left < w and 0 <= right < w:
            neigh = 0.5 * (top[y, left] + top[y, right])
        elif 0 <= left < w:
            neigh = top[y, left]
        elif 0 <= right < w:
            neigh = top[y, right]
        else:
            continue
        row = top[y, x0 : x1 + 1]
        hits += int(np.sum(row < (neigh - px_dip_thr)))

    if hits < min_hits:
        return img

    out = img.copy()
    for y in range(h_top):
        if 0 <= left < w and 0 <= right < w:
            repl = ((out[y, left, :].astype(np.uint16) + out[y, right, :].astype(np.uint16)) // 2).astype(np.uint8)
            neigh = 0.5 * (gray[y, left] + gray[y, right])
        elif 0 <= left < w:
            repl = out[y, left, :]
            neigh = gray[y, left]
        elif 0 <= right < w:
            repl = out[y, right, :]
            neigh = gray[y, right]
        else:
            continue

        for xx in range(x0, x1 + 1):
            if float(gray[y, xx]) < float(neigh) - float(px_dip_thr):
                out[y, xx, :] = repl

    return out


def repair_top_horizontal_dark_line(
    img: np.ndarray,
    top_frac: float = 0.60,
    x_range_frac: tuple[float, float] = (0.50, 0.90),
    band: int = 2,
    min_dip: float = 1.5,
    px_dip_thr: float = 3.0,
    min_hits: int = 20,
) -> np.ndarray:
    """修補右上方（或指定區段）出現的細水平縫線。

    - 只在影像上方 top_frac 的高度內找最明顯的 row dip
    - 只在 x_range_frac 的範圍內修補
    - 只替換相對上下鄰居更暗的像素，不做模糊
    """
    if img is None or img.size == 0:
        return img
    h, w = img.shape[:2]
    if h < 10 or w < 10:
        return img

    h_top = int(max(3, min(h, round(h * top_frac))))
    x_lo = int(np.clip(round(w * float(x_range_frac[0])), 0, w - 1))
    x_hi = int(np.clip(round(w * float(x_range_frac[1])), 0, w - 1))
    if x_hi < x_lo:
        x_lo, x_hi = x_hi, x_lo
    if x_hi - x_lo < 5:
        return img

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    top = gray[:h_top, :]

    # 用 row mean dip 找疑似水平縫（同時支援偏暗/偏亮縫線）
    row_mean = top[:, x_lo : x_hi + 1].mean(axis=1)
    dip = np.zeros(h_top, dtype=np.float32)
    dip[1:-1] = 0.5 * (row_mean[:-2] + row_mean[2:]) - row_mean[1:-1]
    dip_abs = np.abs(dip)
    y = int(dip_abs.argmax())
    if float(dip_abs[y]) < float(min_dip):
        return img

    y0 = max(0, y - band)
    y1 = min(h - 1, y + band)
    up = y0 - 1
    down = y1 + 1
    if up < 0 and down >= h:
        return img

    # 先計算 hits，避免誤修正常結構
    hits = 0
    for yy in range(y0, y1 + 1):
        if 0 <= up < h and 0 <= down < h:
            neigh = 0.5 * (gray[up, x_lo : x_hi + 1] + gray[down, x_lo : x_hi + 1])
        elif 0 <= up < h:
            neigh = gray[up, x_lo : x_hi + 1]
        elif 0 <= down < h:
            neigh = gray[down, x_lo : x_hi + 1]
        else:
            continue
        row = gray[yy, x_lo : x_hi + 1]
        hits += int(np.sum(np.abs(row - neigh) > px_dip_thr))

    if hits < min_hits:
        return img

    out = img.copy()
    for yy in range(y0, y1 + 1):
        if 0 <= up < h and 0 <= down < h:
            repl = ((out[up, x_lo : x_hi + 1, :].astype(np.uint16) + out[down, x_lo : x_hi + 1, :].astype(np.uint16)) // 2).astype(np.uint8)
            neigh = 0.5 * (gray[up, x_lo : x_hi + 1] + gray[down, x_lo : x_hi + 1])
        elif 0 <= up < h:
            repl = out[up, x_lo : x_hi + 1, :]
            neigh = gray[up, x_lo : x_hi + 1]
        elif 0 <= down < h:
            repl = out[down, x_lo : x_hi + 1, :]
            neigh = gray[down, x_lo : x_hi + 1]
        else:
            continue

        row = gray[yy, x_lo : x_hi + 1]
        mask = np.abs(row - neigh) > px_dip_thr
        if np.any(mask):
            out[yy, x_lo : x_hi + 1, :][mask] = repl[mask]

    return out


def remove_seam_lines(image: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    """完美Pro版本：檢測所有暗邊 + 雙向自適應融合 + 紋理還原"""
    if image is None:
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 優先處理「細黑線」：用極小半徑 inpaint，避免大面積模糊
    # 典型情況：拼接接縫出現 1~2px 的純黑線
    thin_black = gray < 12
    thin_ratio = float(np.mean(thin_black))
    if thin_ratio > 0 and thin_ratio < 0.01:
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        thin_mask = cv2.morphologyEx(thin_black.astype(np.uint8) * 255, cv2.MORPH_OPEN, k, iterations=1)
        thin_mask = cv2.dilate(thin_mask, k, iterations=1)
        if np.any(thin_mask):
            # 半徑小一點，保持清晰度
            return cv2.inpaint(image, thin_mask, 2, cv2.INPAINT_TELEA)

    # 次要處理：偵測「固定位置的長直黑線」（常見於兩張影像之間的小縫隙）
    # 用窄條 inpaint 修掉，不做大範圍模糊
    thr = 25
    dark = (gray < thr)
    if dark.size > 0:
        row_frac = dark.mean(axis=1)
        col_frac = dark.mean(axis=0)
        # 避免外框黑邊影響判斷
        if row_frac.shape[0] > 4:
            row_frac[:2] = 0
            row_frac[-2:] = 0
        if col_frac.shape[0] > 4:
            col_frac[:2] = 0
            col_frac[-2:] = 0

        max_row = float(row_frac.max()) if row_frac.size else 0.0
        max_col = float(col_frac.max()) if col_frac.size else 0.0

        seam_mask = None
        if max_col >= 0.05 and max_col >= max_row:
            x = int(col_frac.argmax())
            # 只在窄條區域做修補，且只修暗像素附近
            w = 2
            x0, x1 = max(0, x - w), min(gray.shape[1], x + w + 1)
            band = np.zeros_like(gray, dtype=np.uint8)
            band[:, x0:x1] = 255
            # 放寬閾值，包含抗鋸齒/近黑像素，但限制在 band 內
            seam_mask = ((gray < 80) & (band > 0)).astype(np.uint8) * 255
            # 讓斷續的縫合併起來，但避免擴散太寬
            vk_close = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 21))
            vk_open = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 7))
            seam_mask = cv2.morphologyEx(seam_mask, cv2.MORPH_CLOSE, vk_close, iterations=1)
            seam_mask = cv2.morphologyEx(seam_mask, cv2.MORPH_OPEN, vk_open, iterations=1)
            seam_mask = cv2.dilate(seam_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)
        elif max_row >= 0.05:
            y = int(row_frac.argmax())
            h = 2
            y0, y1 = max(0, y - h), min(gray.shape[0], y + h + 1)
            band = np.zeros_like(gray, dtype=np.uint8)
            band[y0:y1, :] = 255
            seam_mask = ((gray < 80) & (band > 0)).astype(np.uint8) * 255
            hk_close = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 1))
            hk_open = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 1))
            seam_mask = cv2.morphologyEx(seam_mask, cv2.MORPH_CLOSE, hk_close, iterations=1)
            seam_mask = cv2.morphologyEx(seam_mask, cv2.MORPH_OPEN, hk_open, iterations=1)
            seam_mask = cv2.dilate(seam_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)

        if seam_mask is not None and np.any(seam_mask):
            # 直線縫通常是「缺一條像素」，直接用左右鄰近像素補，比 inpaint 更穩定
            if max_col >= max_row:
                # vertical
                x = int(col_frac.argmax())
                w = 2
                x0, x1 = max(0, x - w), min(gray.shape[1], x + w + 1)
                xl = max(0, x0 - 2)
                xr = min(gray.shape[1] - 1, x1 + 1)
                result = image.copy().astype(np.float32)
                seam_bool = seam_mask.astype(bool)
                for xi in range(x0, x1):
                    # 左右都存在就平均；若靠邊則退回 inpaint
                    if xl == xi or xr == xi:
                        return cv2.inpaint(image, seam_mask, 3, cv2.INPAINT_TELEA)
                    left = result[:, xl, :]
                    right = result[:, xr, :]
                    m = seam_bool[:, xi]
                    if np.any(m):
                        result[m, xi, :] = 0.5 * left[m, :] + 0.5 * right[m, :]
                return np.clip(result, 0, 255).astype(np.uint8)
            else:
                # horizontal
                y = int(row_frac.argmax())
                h = 2
                y0, y1 = max(0, y - h), min(gray.shape[0], y + h + 1)
                yt = max(0, y0 - 2)
                yb = min(gray.shape[0] - 1, y1 + 1)
                result = image.copy().astype(np.float32)
                seam_bool = seam_mask.astype(bool)
                for yi in range(y0, y1):
                    if yt == yi or yb == yi:
                        return cv2.inpaint(image, seam_mask, 3, cv2.INPAINT_TELEA)
                    top = result[yt, :, :]
                    bottom = result[yb, :, :]
                    m = seam_bool[yi, :]
                    if np.any(m):
                        result[yi, m, :] = 0.5 * top[m, :] + 0.5 * bottom[m, :]
                return np.clip(result, 0, 255).astype(np.uint8)

    # 檢測暗邊（包含所有可能的接縫區域）
    dark_mask = gray < 45  # 包括純黑和暗邊

    if not np.any(dark_mask):
        return image

    # 形態學清理
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    cleaned = cv2.morphologyEx(dark_mask.astype(np.uint8), cv2.MORPH_OPEN, kernel)

    # 邊界擴展
    seam_mask = cv2.dilate(cleaned, kernel, iterations=2)
    kernel_expand = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size * 3, kernel_size * 3))
    transition_zone = cv2.dilate(seam_mask, kernel_expand, iterations=1)

    result = image.copy().astype(np.float32)

    if np.any(transition_zone):
        # 多層高斯金字塔
        layers = [image.astype(np.float32)]
        for i in range(3):
            kernel_size_blur = 2 * (i + 1) * kernel_size + 1
            layers.append(cv2.GaussianBlur(layers[-1], (kernel_size_blur, kernel_size_blur), 0))

        # 智能遮罩
        seam_float = seam_mask.astype(np.float32) / 255.0
        transition_float = transition_zone.astype(np.float32) / 255.0

        # 多層過渡
        smooth1 = cv2.GaussianBlur(seam_float, (kernel_size * 2 + 1, kernel_size * 2 + 1), 0)
        smooth2 = cv2.GaussianBlur(transition_float, (kernel_size * 4 + 1, kernel_size * 4 + 1), 0)

        for c in range(3):
            # 主層：暗邊用強模糊（層2）+ 30% 原始
            main = 0.75 * layers[2][:, :, c] + 0.25 * layers[0][:, :, c]

            # 過渡層：邊界用輕模糊（層1）
            transition = 0.5 * layers[1][:, :, c] + 0.5 * layers[0][:, :, c]

            # 融合：暗邊優先，邊界漸進
            blend = smooth1 * main + (1 - smooth1) * (smooth2 * transition + (1 - smooth2) * layers[0][:, :, c])

            # 最終平滑
            result[:, :, c] = 0.9 * blend + 0.1 * layers[1][:, :, c]

    return np.clip(result, 0, 255).astype(np.uint8)
