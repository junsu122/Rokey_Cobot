import React, { useState, useRef, useEffect, useCallback } from 'react';
import { initializeApp } from 'firebase/app';
import { getStorage, ref as storageRef, uploadBytes } from 'firebase/storage';
import { getFirestore, doc, setDoc, onSnapshot } from 'firebase/firestore';

const firebaseConfig = {
  apiKey:            import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain:        import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId:         import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket:     import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId:             import.meta.env.VITE_FIREBASE_APP_ID,
};
const firebaseApp = initializeApp(firebaseConfig);
const storage = getStorage(firebaseApp);
const db = getFirestore(firebaseApp);

const colors = {
  textDark:    '#2C3E50',
  textMedium:  '#7F8C8D',
  pastelPink:  '#E9C3E1',
  pastelPurple:'#D3CDEE',
  pastelBlue:  '#339AF0',
  gridLine:    '#F1F3F5',
  appBg:       '#F1F3F5',
  panelBg:     '#FFFFFF',
  viewerBg:    '#FAFAFF',
  accent:      '#40C057',
};

const typography = {
  title:   { fontSize: '40px', fontWeight: '800', letterSpacing: '-0.5px', fontFamily: '"Noto Sans KR", sans-serif' },
  content: { fontSize: '18px', fontWeight: '600', fontFamily: '"Noto Sans KR", sans-serif' },
  caption: { fontSize: '16px', fontWeight: '500', color: colors.textMedium, fontFamily: '"Noto Sans KR", sans-serif' },
  button:  { fontSize: '25px', fontWeight: '800', letterSpacing: '0.5px', fontFamily: '"Noto Sans KR", sans-serif' },
};

const ROWS = 8, COLS = 9;
const NORM_W = 180, NORM_H = 160;
const OUTPUT_AREA_W = 200.0, OUTPUT_AREA_H = 200.0;
const OUTPUT_GAP = 2.0, OUTPUT_BASE_X = 0.0, OUTPUT_BASE_Z = -30.0;
const PRICE_PER_FLOWER = 2000;
const THRESHOLD = 210;

const FLOWER_COLORS = [
  "#E74C3C","#FF6B9D","#E67E22","#F1C40F",
  "#2ECC71","#3498DB","#9B59B6","#1ABC9C",
];

const CELL_W = OUTPUT_AREA_W / COLS;
const CELL_H = OUTPUT_AREA_H / ROWS;

function drawGridWithFlowers(ctx, grid, cs) {
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
        ctx.fillStyle = "#F1C40F";
        ctx.fill();
      }
    }
  }
}

function drawFlower(ctx, cx, cy, size, color, opacity = 1.0) {
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
  ctx.fillStyle = "#F1C40F";
  ctx.fill();
  ctx.strokeStyle = "#E67E22";
  ctx.lineWidth = 0.8;
  ctx.stroke();
  ctx.restore();
}

function drawSparkle(ctx, cx, cy, size) {
  ctx.save();
  ctx.globalAlpha = 0.7;
  for (let i = 0; i < 8; i++) {
    const angle = (i / 8) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(angle) * (size + 2), cy + Math.sin(angle) * (size + 2));
    ctx.lineTo(cx + Math.cos(angle) * (size + 6), cy + Math.sin(angle) * (size + 6));
    ctx.strokeStyle = "#FA5252";
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
  ctx.restore();
}

// ── 인라인 꽃꽂이 시뮬레이터 ─────────────
function FlowerSimulator({ coords, paused }) {
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
    if (a.z !== b.z) return a.z - b.z;  // z 작은 것(위)부터
    return a.x - b.x;                    // x 작은 것(왼쪽)부터
  });

  // 좌표 → grid 셀 인덱스 → 캔버스 픽셀 (셀 중앙)
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
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    const cur = currentRef.current;
    frameRef.current += 1;

    ctx.fillStyle = "#0d1117";
    ctx.fillRect(0, 0, W, H);

    // 세로선 (COLS+1개)
    for (let c = 0; c <= COLS; c++) {
      const x = 30 + (c / COLS) * (W - 60);
      ctx.strokeStyle = "#1e2a1e";
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, 30); ctx.lineTo(x, H - 30); ctx.stroke();
    }
    // 가로선 (ROWS+1개)
    for (let r = 0; r <= ROWS; r++) {
      const y = 30 + (r / ROWS) * (H - 60);
      ctx.strokeStyle = "#1e2a1e";
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(30, y); ctx.lineTo(W - 30, y); ctx.stroke();
    }
    ctx.strokeStyle = "#1e3a1e";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(30, 30, W - 60, H - 60);

    if (!coordList.length) return;

    // 빈 자리
    coordList.forEach((c, i) => {
      if (plantedRef.current.has(i)) return;
      const [px, py] = toCanvasGrid(c.x, c.z, W, H);
      ctx.beginPath();
      ctx.arc(px, py, 6, 0, Math.PI * 2);
      ctx.strokeStyle = "#1e3a1e";
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
    });

    // 심어진 꽃
    plantedRef.current.forEach(i => {
      if (i >= coordList.length) return;
      const [px, py] = toCanvasGrid(coordList[i].x, coordList[i].z, W, H);
      drawFlower(ctx, px, py, 12, FLOWER_COLORS[i % FLOWER_COLORS.length]);
    });

    // 현재 심는 중
    if (cur >= 0 && cur < coordList.length) {
      const [px, py] = toCanvasGrid(coordList[cur].x, coordList[cur].z, W, H);
      const pulse = Math.abs(Math.sin(frameRef.current * 0.12));
      ctx.beginPath();
      ctx.arc(px, py, 16 + pulse * 6, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(250,82,82,${0.3 + pulse * 0.4})`;
      ctx.lineWidth = 2;
      ctx.stroke();
      drawSparkle(ctx, px, py, 12 + pulse * 3);
      drawFlower(ctx, px, py, 13, FLOWER_COLORS[cur % FLOWER_COLORS.length], 0.7 + pulse * 0.3);
    }

    // 일시정지 오버레이
    if (pausedRef.current) {
      ctx.fillStyle = "rgba(13,17,23,0.6)";
      ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = "#E67E22";
      ctx.font = "bold 24px monospace";
      ctx.textAlign = "center";
      ctx.fillText("⏸ 일시정지", W / 2, H / 2);
    }

    ctx.fillStyle = "rgba(13,17,23,0.85)";
    if (ctx.roundRect) ctx.roundRect(8, H - 36, 200, 28, 6);
    else ctx.rect(8, H - 36, 200, 28);
    ctx.fill();
    ctx.fillStyle = pausedRef.current ? "#E67E22" : cur >= 0 ? "#FA5252" : "#40C057";
    ctx.font = "bold 12px monospace";
    ctx.textAlign = "left";
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
    window.addEventListener("resize", resize);
    const loop = () => { draw(); animRef.current = requestAnimationFrame(loop); };
    loop();
    return () => { window.removeEventListener("resize", resize); cancelAnimationFrame(animRef.current); };
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

// ── 전처리 ────────────────────────────────
function preprocessImage(imageData, margin, symmetry) {
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

function gridToCoords(pixelGrid) {
  const coords = {};
  let idx = 0;
  for (let row = ROWS - 1; row >= 0; row--)
    for (let col = 0; col < COLS; col++)
      if (pixelGrid[row * COLS + col])
        coords[String(idx++)] = {
          x: Math.round((OUTPUT_BASE_X + CELL_W / 2 + col * (CELL_W + OUTPUT_GAP)) * 10) / 10,
          y: 2.0,
          z: Math.round((CELL_H / 2 + (ROWS - 1 - row) * CELL_H + OUTPUT_BASE_Z) * 10) / 10,
          rx: 0.0, ry: 180.0, rz: 0.0,
        };
  return coords;
}

// ── 메인 앱 ──────────────────────────────
export default function App() {
  const [originalImage, setOriginalImage] = useState(null);
  const [hasPreview, setHasPreview]       = useState(false);
  const [status, setStatus]               = useState('idle');
  const [coords, setCoords]               = useState(null);
  const [pixelGrid, setPixelGrid]         = useState(Array(ROWS * COLS).fill(false));
  const [currentDocId, setCurrentDocId]   = useState(null);
  const [margin, setMargin]               = useState(21);
  const [symmetry, setSymmetry]           = useState(true);
  const [progress]                        = useState(0);
  const [showSim, setShowSim]             = useState(false);
  const [paused, setPaused]               = useState(false);

  const normCanvasRef  = useRef(null);
  const pixelCanvasRef = useRef(null);
  const fileInputRef   = useRef(null);
  const unsubRef       = useRef(null);

  const robotStatus  = { isConnected: true, modelName: "Doosan M0609", isReady: true };
  const canAccept    = !!originalImage && !['uploading', 'processing', 'accepting', 'cancelling'].includes(status) && !showSim;
  const canCancel    = status === 'accepted';
  const editorActive = !!originalImage && !showSim;

  const flowerCount = pixelGrid.filter(Boolean).length;
  const totalPrice  = flowerCount * PRICE_PER_FLOWER;

  const handleReset = () => {
  setShowSim(false); setStatus('idle'); setCoords(null);
  setOriginalImage(null); setHasPreview(false); setPaused(false);
  setPixelGrid(Array(ROWS * COLS).fill(false));
  setCurrentDocId(null);
  // 파일 입력 초기화
  if (fileInputRef.current) fileInputRef.current.value = '';
};

  const runLocalPreprocess = useCallback((imgData, marg, sym) => {
    if (!imgData) return;
    const { normImageData, grid } = preprocessImage(imgData, marg, sym);
    if (!normImageData) return;
    const nc = normCanvasRef.current;
    if (nc) { nc.width = NORM_W; nc.height = NORM_H; nc.getContext('2d').putImageData(normImageData, 0, 0); }
    const pc = pixelCanvasRef.current;
    if (pc) {
      const cs = 20;
      pc.width = COLS * cs; pc.height = ROWS * cs;
      const ctx = pc.getContext('2d');
      ctx.imageSmoothingEnabled = false;
      drawGridWithFlowers(ctx, grid, cs);
    }
    setPixelGrid(grid);
    setHasPreview(true);
  }, []);

  useEffect(() => {
    if (originalImage?.imageData)
      runLocalPreprocess(originalImage.imageData, margin, symmetry);
  }, [margin, symmetry, originalImage, runLocalPreprocess]);

  useEffect(() => {
    document.body.style.margin = "0";
    document.body.style.padding = "0";
    document.body.style.overflow = "hidden";
  }, []);

  useEffect(() => {
    const pc = pixelCanvasRef.current;
    if (!pc || !hasPreview) return;
    const cs = 20;
    pc.width = COLS * cs;
    pc.height = ROWS * cs;
    const ctx = pc.getContext('2d');
    ctx.imageSmoothingEnabled = false;
    drawGridWithFlowers(ctx, pixelGrid, cs);
  }, [pixelGrid, hasPreview]);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.width; canvas.height = img.height;
      canvas.getContext('2d').drawImage(img, 0, 0);
      const imageData = canvas.getContext('2d').getImageData(0, 0, img.width, img.height);
      setOriginalImage({ file, url, imageData });
      setStatus('idle'); setCoords(null); setCurrentDocId(null);
      setHasPreview(false); setShowSim(false); setPaused(false);
      runLocalPreprocess(imageData, margin, symmetry);
    };
    img.src = url;
  };

  const handleAccept = async () => {
    const docId = currentDocId || `images_${originalImage?.file.name}`;
    if (!docId) return;
    setCurrentDocId(docId); setStatus('accepting');
    try {
      const newCoords = gridToCoords(pixelGrid);
      await setDoc(doc(db, 'pixel_coords', docId), {
        coords: newCoords, status: 'done',
        flowerCount, totalPrice,
      });
      setCoords(newCoords);
      setStatus('accepted');
      setShowSim(true);
      setPaused(false);
    } catch (err) { console.error(err); setStatus('error'); }
  };

  const handleCancel = async () => {
  if (!canCancel) return;
  try {
    await setDoc(doc(db, 'pixel_coords', 'cancel_signal'), {
      status: 'cancel',
      coords: { "0": { x: 0.0, y: 0.0, z: 0.0, rx: 0.0, ry: 0.0, rz: 0.0 } },
      timestamp: Date.now(),
    });
  } catch (err) { console.error(err); }
  // 취소 후 바로 초기화면으로
  handleReset();
};

  const handlePause = async () => {
    setPaused(true);
    try {
      await setDoc(doc(db, 'pixel_coords', 'control_signal'), {
        status: 'pause',
        coords: { "0": { x: 1.0, y: 1.0, z: 1.0, rx: 1.0, ry: 1.0, rz: 1.0 } },
        timestamp: Date.now(),
      });
    } catch (err) { console.error(err); }
  };

  const handleResume = async () => {
    setPaused(false);
    try {
      await setDoc(doc(db, 'pixel_coords', 'control_signal'), {
        status: 'resume',
        coords: { "0": { x: 2.0, y: 2.0, z: 2.0, rx: 2.0, ry: 2.0, rz: 2.0 } },
        timestamp: Date.now(),
      });
    } catch (err) { console.error(err); }
  };

  const statusLabel = {
    idle:         '이미지를 선택하면 실시간 미리보기가 표시됩니다',
    uploading:    '⏫ 업로드 중...',
    processing:   '⚙️ 처리 중...',
    preprocessed: '✏️ 픽셀을 조정하고 ACCEPT를 누르세요',
    accepting:    '💾 좌표 저장 중...',
    accepted:     `✅ 완료 (좌표 ${coords ? Object.keys(coords).length : 0}개)`,
    cancelling:   '🚫 주문 취소 중...',
    cancelled:    '❌ 주문이 취소되었습니다',
    error:        '❌ 오류 발생',
  }[status];

  return (
    <div style={styles.outerContainer}>
      <div style={styles.appWrapper}>

        <header style={styles.header}>
          <div style={{ ...typography.title, fontSize: '28px', color: colors.textDark }}>DRAWING-FLOWER v2.0</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ ...typography.caption, fontSize: '16px', color: status === 'error' || status === 'cancelled' ? '#FA5252' : status === 'accepted' ? colors.accent : colors.textMedium }}>
              {statusLabel}
            </span>
            <div style={{ ...typography.caption, fontSize: '16px', fontWeight: 'bold', color: robotStatus.isReady ? '#40C057' : '#FA5252' }}>
              ● {robotStatus.modelName} - READY
            </div>
            {showSim && (
              <button onClick={handleReset}
                style={{ padding: '8px 18px', borderRadius: '10px', border: 'none', backgroundColor: '#2a2a3e', color: '#8b8ba0', cursor: 'pointer', fontSize: '14px', fontWeight: '600', fontFamily: '"Noto Sans KR", sans-serif', whiteSpace: 'nowrap' }}>
                ↺ 처음으로
              </button>
            )}
          </div>
        </header>

        <main style={styles.main}>
          <section style={styles.topSection}>
            <div style={styles.viewerContainer}>
              <div style={{ ...typography.title, fontSize: '20px', color: colors.textDark, marginBottom: '8px' }}>원본 이미지</div>
              <div style={{ ...styles.viewerDisplay, cursor: 'pointer' }} onClick={() => fileInputRef.current?.click()}>
                {originalImage ? <img src={originalImage.url} alt="original" style={styles.viewerImg} /> : <span style={{ ...typography.caption, fontSize: '18px' }}>클릭하여 이미지 선택</span>}
                <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFileChange} style={{ display: 'none' }} />
              </div>
            </div>
            <div style={styles.viewerContainer}>
              <div style={{ ...typography.title, fontSize: '20px', color: colors.textDark, marginBottom: '8px' }}>이미지 크기</div>
              <div style={styles.viewerDisplay}>
                {hasPreview ? <canvas ref={normCanvasRef} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} /> : <><span style={{ ...typography.caption, fontSize: '18px' }}>이미지를 선택하세요</span><canvas ref={normCanvasRef} style={{ display: 'none' }} /></>}
              </div>
            </div>
            <div style={styles.viewerContainer}>
              <div style={{ ...typography.title, fontSize: '20px', color: colors.textDark, marginBottom: '8px' }}>미리보기</div>
              <div style={styles.viewerDisplay}>
                {hasPreview ? <canvas ref={pixelCanvasRef} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} /> : <><span style={{ ...typography.caption, fontSize: '18px' }}>이미지를 선택하세요</span><canvas ref={pixelCanvasRef} style={{ display: 'none' }} /></>}
              </div>
            </div>
          </section>

          <section style={styles.bottomSection}>
            {showSim ? (
              <div style={{ flex: 2.5, borderRadius: '16px', overflow: 'hidden' }}>
                <FlowerSimulator coords={coords} paused={paused} />
              </div>
            ) : (
              <div style={{ ...styles.editorContainer, border: editorActive ? `2px solid ${colors.pastelBlue}` : '1px solid #F1F3F5' }}>
                <div style={{ ...styles.editorHeader, flexWrap: 'wrap', gap: '12px' }}>
                  <div style={{ ...typography.title, fontSize: '20px', color: colors.textDark, flexShrink: 0 }}>픽셀 에디터</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '20px', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ ...typography.content, fontSize: '16px', color: colors.textMedium }}>크기 조정</span>
                      <span style={{ ...typography.content, fontSize: '16px', color: colors.pastelBlue, minWidth: '24px', textAlign: 'right' }}>{margin}</span>
                      <input type="range" min={0} max={40} value={margin} onChange={(e) => setMargin(Number(e.target.value))} style={{ ...styles.slider, width: '100px' }} />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ ...typography.content, fontSize: '16px', color: colors.textMedium }}>좌우 대칭</span>
                      <div onClick={() => setSymmetry(!symmetry)}
                        style={{ width: '44px', height: '24px', borderRadius: '12px', cursor: 'pointer', backgroundColor: symmetry ? colors.pastelBlue : '#DEE2E6', position: 'relative', transition: 'background 0.2s', flexShrink: 0 }}>
                        <div style={{ position: 'absolute', top: '3px', left: symmetry ? '22px' : '3px', width: '18px', height: '18px', borderRadius: '50%', backgroundColor: '#fff', transition: 'left 0.2s' }} />
                      </div>
                    </div>
                    {editorActive && <span style={{ ...typography.caption, fontSize: '14px', color: colors.pastelBlue }}>클릭으로 셀 토글</span>}
                  </div>
                </div>
                <div style={styles.canvasWrapper}>
                  <div style={{ ...styles.canvas, transform: 'scale(1.96)', transformOrigin: 'center' }}>
                    <div style={styles.pixelGrid}>
                      {pixelGrid.map((filled, i) => {
                        const row = Math.floor(i / COLS), col = i % COLS;
                        const isEdge = row === 0 || row === ROWS-1 || col === 0 || col === COLS-1;
                        return (
                          <div key={i}
                            style={{ ...styles.pixel, backgroundColor: filled ? (isEdge ? '#FA5252' : '#2C3E50') : '#FFFFFF', cursor: editorActive ? 'pointer' : 'default' }}
                            onClick={() => { if (!editorActive) return; const n = [...pixelGrid]; n[i] = !n[i]; setPixelGrid(n); }}
                          />
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div style={styles.utilityPanel}>
              <div>
                <div style={{ ...typography.title, fontSize: '18px', textAlign: 'center', marginBottom: '14px' }}>진행율</div>
                <div style={styles.progressBarBg}><div style={{ ...styles.progressBarFill, width: `${progress}%` }} /></div>
                <div style={{ ...typography.content, fontSize: '16px', display: 'flex', justifyContent: 'space-between', marginTop: '10px' }}>
                  <span>{progress > 0 ? '작동중' : '대기중'}</span><span>{progress}%</span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ backgroundColor: '#FFF0F6', borderRadius: '12px', padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '17px', fontWeight: '600', fontFamily: '"Noto Sans KR", sans-serif', color: '#E64980' }}>꽃 개수</span>
                  <span style={{ fontSize: '26px', fontWeight: '800', fontFamily: '"Noto Sans KR", sans-serif', color: '#E64980' }}>{flowerCount} 송이</span>
                </div>
                <div style={{ backgroundColor: '#F3F0FF', borderRadius: '12px', padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '17px', fontWeight: '600', fontFamily: '"Noto Sans KR", sans-serif', color: '#7048E8' }}>총 가격</span>
                  <span style={{ fontSize: '26px', fontWeight: '800', fontFamily: '"Noto Sans KR", sans-serif', color: '#7048E8' }}>{totalPrice.toLocaleString()}원</span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <button
                  style={{ ...styles.btn, ...typography.button, backgroundColor: canAccept ? colors.accent : '#ADB5BD', opacity: canAccept ? 1 : 0.5 }}
                  disabled={!canAccept}
                  onClick={handleAccept}
                >
                  {status === 'accepting' ? '저장 중...' : status === 'accepted' ? '주문 처리중' : '주문하기'}
                </button>
                <button
                  style={{ ...styles.btn, ...typography.button, backgroundColor: canCancel ? '#FA5252' : '#ADB5BD', opacity: canCancel ? 1 : 0.4, fontSize: '25px' }}
                  disabled={!canCancel}
                  onClick={handleCancel}
                >
                  {status === 'cancelling' ? '취소 중...' : status === 'cancelled' ? '취소됨' : '주문 취소'}
                </button>
                {showSim && (
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      style={{ ...styles.btn, flex: 1, fontSize: '20px', fontWeight: '700', backgroundColor: paused ? '#ADB5BD' : '#E67E22', fontFamily: '"Noto Sans KR", sans-serif' }}
                      disabled={paused}
                      onClick={handlePause}
                    >
                      ⏸ 일시정지
                    </button>
                    <button
                      style={{ ...styles.btn, flex: 1, fontSize: '18px', fontWeight: '700', backgroundColor: !paused ? '#ADB5BD' : '#40C057', fontFamily: '"Noto Sans KR", sans-serif' }}
                      disabled={!paused}
                      onClick={handleResume}
                    >
                      ▶ 재개
                    </button>
                  </div>
                )}
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

const styles = {
  outerContainer:  { height: '100vh', width: '100%', backgroundColor: colors.appBg, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', position: 'fixed', top: 0, left: 0, boxSizing: 'border-box' },
  appWrapper:      { width: '100vw', height: '90vh', maxWidth: '1600px', maxHeight: '1200px', backgroundColor: colors.panelBg, borderRadius: '24px', boxShadow: '0 30px 60px rgba(0,0,0,0.1)', display: 'flex', flexDirection: 'column', overflow: 'hidden', border: '1px solid #E9ECEF', boxSizing: 'border-box' },
  header:          { height: '70px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 32px', borderBottom: '1px solid #F1F3F5', flexShrink: 0 },
  main:            { flex: 1, padding: '24px', display: 'flex', flexDirection: 'column', overflow: 'hidden', gap: '24px' },
  topSection:      { height: '30%', display: 'flex', gap: '24px' },
  viewerContainer: { flex: 1, display: 'flex', flexDirection: 'column' },
  viewerDisplay:   { flex: 1, backgroundColor: colors.viewerBg, border: '1px solid #F1F3F5', borderRadius: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  viewerImg:       { maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', borderRadius: '12px' },
  bottomSection:   { flex: 1, display: 'flex', gap: '24px', overflow: 'hidden' },
  editorContainer: { flex: 2.5, display: 'flex', flexDirection: 'column', backgroundColor: colors.panelBg, borderRadius: '16px', padding: '20px 24px', boxSizing: 'border-box' },
  editorHeader:    { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' },
  canvasWrapper:   { flex: 1, backgroundColor: colors.appBg, borderRadius: '12px', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  canvas:          { width: '225px', height: '200px', backgroundColor: '#FFFFFF', border: '1px solid #E9ECEF' },
  pixelGrid:       { width: '100%', height: '100%', display: 'grid', gridTemplateColumns: 'repeat(9, 1fr)', gridTemplateRows: 'repeat(8, 1fr)' },
  pixel:           { border: `0.5px solid ${colors.gridLine}`, transition: 'background-color 0.1s' },
  utilityPanel:    { flex: 1, minWidth: '260px', backgroundColor: colors.viewerBg, borderRadius: '16px', padding: '24px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', boxSizing: 'border-box' },
  slider:          { width: '100%', height: '8px', cursor: 'pointer', borderRadius: '10px', appearance: 'none', backgroundColor: '#E9ECEF' },
  progressBarBg:   { height: '12px', backgroundColor: '#E9ECEF', borderRadius: '10px' },
  progressBarFill: { height: '100%', backgroundImage: `linear-gradient(90deg, ${colors.pastelPink} 0%, ${colors.pastelPurple} 100%)`, borderRadius: '10px' },
  btn:             { height: '64px', color: '#FFFFFF', border: 'none', borderRadius: '16px', cursor: 'pointer', width: '100%', transition: 'background-color 0.2s', fontFamily: '"Noto Sans KR", sans-serif' },
};