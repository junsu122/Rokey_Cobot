import {
  ROWS, COLS, NORM_W, NORM_H,
  OUTPUT_BASE_X, OUTPUT_BASE_Z,
  CELL_W, CELL_H, OUTPUT_GAP, THRESHOLD,
} from './constants';

export function preprocessImage(imageData, margin, symmetry) {
  const { width, height, data } = imageData;
  const binary = new Uint8Array(width * height);
  for (let i = 0; i < width * height; i++) {
    const gray = 0.299 * data[i*4] + 0.587 * data[i*4+1] + 0.114 * data[i*4+2];
    binary[i] = gray < THRESHOLD ? 0 : 255;
  }
  let minX = width, maxX = 0, minY = height, maxY = 0;
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++)
      if (binary[y * width + x] === 0) {
        if (x < minX) minX = x; if (x > maxX) maxX = x;
        if (y < minY) minY = y; if (y > maxY) maxY = y;
      }
  if (minX > maxX || minY > maxY)
    return { normImageData: null, grid: Array(ROWS * COLS).fill(false) };

  const cropW = maxX - minX + 1, cropH = maxY - minY + 1;
  const usableW = Math.max(1, NORM_W - 2 * margin);
  const usableH = Math.max(1, NORM_H - 2 * margin);
  const scale = Math.min(usableW / cropW, usableH / cropH);
  const newW = Math.max(1, Math.round(cropW * scale));
  const newH = Math.max(1, Math.round(cropH * scale));
  const offsetX = Math.floor((NORM_W - newW) / 2);
  const offsetY = Math.floor((NORM_H - newH) / 2);
  const normArr = new Uint8ClampedArray(NORM_W * NORM_H * 4).fill(255);
  for (let y = 0; y < newH; y++)
    for (let x = 0; x < newW; x++) {
      const srcX = Math.floor((x / newW) * cropW) + minX;
      const srcY = Math.floor((y / newH) * cropH) + minY;
      const val = binary[srcY * width + srcX];
      const dstIdx = ((y + offsetY) * NORM_W + (x + offsetX)) * 4;
      normArr[dstIdx] = normArr[dstIdx+1] = normArr[dstIdx+2] = val;
      normArr[dstIdx+3] = 255;
    }
  let grid = Array(ROWS * COLS).fill(false);
  const cellW = NORM_W / COLS, cellH = NORM_H / ROWS;
  for (let row = 0; row < ROWS; row++)
    for (let col = 0; col < COLS; col++) {
      const px = Math.floor((col + 0.5) * cellW);
      const py = Math.floor((row + 0.5) * cellH);
      grid[row * COLS + col] = normArr[(py * NORM_W + px) * 4] < 128;
    }
  if (symmetry)
    for (let row = 0; row < ROWS; row++)
      for (let col = 0; col < Math.floor(COLS / 2); col++) {
        const mirror = COLS - 1 - col;
        if (grid[row * COLS + col] || grid[row * COLS + mirror])
          grid[row * COLS + col] = grid[row * COLS + mirror] = true;
      }
  return { normImageData: new ImageData(normArr, NORM_W, NORM_H), grid };
}

export function gridToCoords(pixelGrid, symmetry = false) {
  const coords = {};
  let idx = 0;
  for (let row = ROWS - 1; row >= 0; row--)
    for (let col = 0; col < COLS; col++)  // col 0→8 (반전 후 x 큰 것부터)
      if (pixelGrid[row * COLS + col]) {
        const xCol = symmetry ? col : COLS - 1 - col;
        coords[String(idx++)] = {
          x: Math.round((OUTPUT_BASE_X + CELL_W / 2 + xCol * (CELL_W + OUTPUT_GAP)) * 10) / 10,
          y: 2.0,
          z: Math.round((CELL_H / 2 + (ROWS - 1 - row) * CELL_H + OUTPUT_BASE_Z) * 10) / 10,
          rx: 0.0, ry: 180.0, rz: 0.0,
        };
      }
  return coords;
}
