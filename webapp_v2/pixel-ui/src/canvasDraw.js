import { ROWS, COLS, FLOWER_COLORS } from './constants';

export function drawGridWithFlowers(ctx, grid, cs) {
  ctx.fillStyle = '#FFFFFF';
  ctx.fillRect(0, 0, COLS * cs, ROWS * cs);
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      if (grid[r * COLS + c]) {
        const cx = c * cs + cs / 2;
        const cy = r * cs + cs / 2;
        const size = cs * 0.6;
        ctx.fillStyle = '#FF6B9D';
        for (let p = 0; p < 6; p++) {
          const angle = (p / 6) * Math.PI * 2;
          ctx.beginPath();
          ctx.ellipse(
            cx + Math.cos(angle) * size * 1.5,
            cy + Math.sin(angle) * size * 1.5,
            size * 0.5, size * 0.8, angle, 0, Math.PI * 2
          );
          ctx.fill();
        }
        ctx.beginPath();
        ctx.arc(cx, cy, size * 0.8, 0, Math.PI * 2);
        ctx.fillStyle = '#F1C40F';
        ctx.fill();
      }
    }
  }
}

export function drawFlower(ctx, cx, cy, size, color, opacity = 1.0) {
  ctx.save();
  ctx.globalAlpha = opacity;
  for (let i = 0; i < 6; i++) {
    const angle = (i / 6) * Math.PI * 2;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    ctx.beginPath();
    ctx.ellipse(0, -(size * 1.2) / 2, size * 0.25, size * 0.6, 0, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.restore();
  }
  ctx.beginPath();
  ctx.arc(cx, cy, size * 0.35, 0, Math.PI * 2);
  ctx.fillStyle = '#F1C40F';
  ctx.fill();
  ctx.strokeStyle = '#E67E22';
  ctx.lineWidth = 0.8;
  ctx.stroke();
  ctx.restore();
}

export function drawSparkle(ctx, cx, cy, size) {
  ctx.save();
  ctx.globalAlpha = 0.7;
  for (let i = 0; i < 8; i++) {
    const angle = (i / 8) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(angle) * (size + 2), cy + Math.sin(angle) * (size + 2));
    ctx.lineTo(cx + Math.cos(angle) * (size + 6), cy + Math.sin(angle) * (size + 6));
    ctx.strokeStyle = '#FA5252';
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
  ctx.restore();
}
