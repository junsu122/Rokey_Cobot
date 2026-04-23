import { useState, useRef, useEffect, useCallback } from 'react';
import {
  ROWS, COLS, FLOWER_COLORS,
  OUTPUT_BASE_X, OUTPUT_BASE_Z, CELL_W, CELL_H, OUTPUT_GAP,
} from './constants';
import { drawFlower, drawSparkle } from './canvasDraw';

export default function FlowerSimulator({ coords, paused }) {
  const canvasRef  = useRef(null);
  const animRef    = useRef(null);
  const frameRef   = useRef(0);
  const plantedRef = useRef(new Set());
  const currentRef = useRef(-1);
  const animIdxRef = useRef(0);
  const pausedRef  = useRef(false);

  const [currentIdx, setCurrentIdx]     = useState(-1);
  const [plantedCount, setPlantedCount] = useState(0);
  const [isAnimating, setIsAnimating]   = useState(false);

  useEffect(() => { pausedRef.current = paused; }, [paused]);

  const coordList = Object.entries(coords || {})
    .map(([, v]) => v)
    .sort((a, b) => {
      if (a.z !== b.z) return a.z - b.z;
      return a.x - b.x;
    });

  const toCanvasGrid = useCallback((x, z, W, H) => {
    const col = Math.round((x - OUTPUT_BASE_X - CELL_W / 2) / (CELL_W + OUTPUT_GAP));
    const row = Math.round((z - OUTPUT_BASE_Z - CELL_H / 2) / CELL_H);
    const clampedCol = Math.max(0, Math.min(COLS - 1, col));
    const clampedRow = Math.max(0, Math.min(ROWS - 1, row));
    const px = 30 + ((clampedCol + 0.5) / COLS) * (W - 60);
    const py = 30 + ((ROWS - 1 - clampedRow + 0.5) / ROWS) * (H - 60);
    return [px, py];
  }, []);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    const cur = currentRef.current;
    frameRef.current += 1;

    ctx.fillStyle = '#0d1117';
    ctx.fillRect(0, 0, W, H);

    for (let c = 0; c <= COLS; c++) {
      const x = 30 + (c / COLS) * (W - 60);
      ctx.strokeStyle = '#1e2a1e'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, 30); ctx.lineTo(x, H - 30); ctx.stroke();
    }
    for (let r = 0; r <= ROWS; r++) {
      const y = 30 + (r / ROWS) * (H - 60);
      ctx.strokeStyle = '#1e2a1e'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(30, y); ctx.lineTo(W - 30, y); ctx.stroke();
    }
    ctx.strokeStyle = '#1e3a1e'; ctx.lineWidth = 1.5;
    ctx.strokeRect(30, 30, W - 60, H - 60);

    if (!coordList.length) return;

    coordList.forEach((c, i) => {
      if (plantedRef.current.has(i)) return;
      const [px, py] = toCanvasGrid(c.x, c.z, W, H);
      ctx.beginPath();
      ctx.arc(px, py, 6, 0, Math.PI * 2);
      ctx.strokeStyle = '#1e3a1e'; ctx.lineWidth = 1;
      ctx.setLineDash([2, 3]); ctx.stroke(); ctx.setLineDash([]);
    });

    plantedRef.current.forEach(i => {
      if (i >= coordList.length) return;
      const [px, py] = toCanvasGrid(coordList[i].x, coordList[i].z, W, H);
      drawFlower(ctx, px, py, 12, FLOWER_COLORS[i % FLOWER_COLORS.length]);
    });

    if (cur >= 0 && cur < coordList.length) {
      const [px, py] = toCanvasGrid(coordList[cur].x, coordList[cur].z, W, H);
      const pulse = Math.abs(Math.sin(frameRef.current * 0.12));
      ctx.beginPath();
      ctx.arc(px, py, 16 + pulse * 6, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(250,82,82,${0.3 + pulse * 0.4})`;
      ctx.lineWidth = 2; ctx.stroke();
      drawSparkle(ctx, px, py, 12 + pulse * 3);
      drawFlower(ctx, px, py, 13, FLOWER_COLORS[cur % FLOWER_COLORS.length], 0.7 + pulse * 0.3);
    }

    if (pausedRef.current) {
      ctx.fillStyle = 'rgba(13,17,23,0.6)';
      ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = '#E67E22';
      ctx.font = 'bold 24px monospace';
      ctx.textAlign = 'center';
      ctx.fillText('⏸ 일시정지', W / 2, H / 2);
    }

    ctx.fillStyle = 'rgba(13,17,23,0.85)';
    if (ctx.roundRect) ctx.roundRect(8, H - 36, 200, 28, 6);
    else ctx.rect(8, H - 36, 200, 28);
    ctx.fill();
    ctx.fillStyle = pausedRef.current ? '#E67E22' : cur >= 0 ? '#FA5252' : '#40C057';
    ctx.font = 'bold 12px monospace';
    ctx.textAlign = 'left';
    if (pausedRef.current) ctx.fillText(`⏸ 일시정지 중... ${cur + 1} / ${coordList.length}`, 16, H - 17);
    else if (cur >= 0) ctx.fillText(`🌸 심는 중... ${cur + 1} / ${coordList.length}`, 16, H - 17);
    else if (plantedRef.current.size === coordList.length && coordList.length > 0)
      ctx.fillText(`✅ 완료! ${coordList.length}송이`, 16, H - 17);
    else ctx.fillText(`대기 중...`, 16, H - 17);
  }, [coordList, toCanvasGrid]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => { canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight; };
    resize();
    window.addEventListener('resize', resize);
    const loop = () => { draw(); animRef.current = requestAnimationFrame(loop); };
    loop();
    return () => { window.removeEventListener('resize', resize); cancelAnimationFrame(animRef.current); };
  }, [draw]);

  useEffect(() => {
    if (!coords || isAnimating) return;
    startAnimation();
  }, [coords]);

  const startAnimation = () => {
    if (isAnimating || !coordList.length) return;
    plantedRef.current = new Set();
    setPlantedCount(0);
    setIsAnimating(true);
    animIdxRef.current = 0;

    const step = () => {
      if (pausedRef.current) { setTimeout(step, 200); return; }
      const idx = animIdxRef.current;
      if (idx >= coordList.length) {
        plantedRef.current.add(idx - 1);
        setPlantedCount(coordList.length);
        setIsAnimating(false);
        currentRef.current = -1;
        setCurrentIdx(-1);
        return;
      }
      if (idx > 0) { plantedRef.current.add(idx - 1); setPlantedCount(idx); }
      currentRef.current = idx;
      setCurrentIdx(idx);
      animIdxRef.current += 1;
      setTimeout(step, 700);
    };
    step();
  };

  const progress = coordList.length > 0 ? Math.round((plantedCount / coordList.length) * 100) : 0;

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', backgroundColor: '#0d1117', borderRadius: '16px', overflow: 'hidden' }}>
      <div style={{ height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 16px', borderBottom: '1px solid #2a2a3e', flexShrink: 0 }}>
        <span style={{ fontSize: '13px', fontWeight: '700', color: '#e8e8f0', fontFamily: 'monospace' }}>🌸 꽃꽂이 시뮬레이션</span>
        <span style={{ fontSize: '12px', color: paused ? '#E67E22' : '#40C057', fontFamily: 'monospace' }}>
          {paused ? '⏸ 일시정지' : `${plantedCount} / ${coordList.length} 송이`}
        </span>
      </div>
      <div style={{ height: '4px', backgroundColor: '#2a2a3e', flexShrink: 0 }}>
        <div style={{ height: '100%', width: `${progress}%`, background: 'linear-gradient(90deg, #2ECC71, #40C057)', transition: 'width 0.5s' }} />
      </div>
      <canvas ref={canvasRef} style={{ flex: 1, display: 'block', width: '100%' }} />
    </div>
  );
}
