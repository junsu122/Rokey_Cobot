import React, { useState, useRef, useEffect, useCallback } from 'react';
import { initializeApp } from 'firebase/app';
import { getStorage, ref as storageRef, uploadBytes } from 'firebase/storage';
import { getFirestore, doc, setDoc, onSnapshot } from 'firebase/firestore';

const firebaseConfig = {
  apiKey: "YOUR_API_KEY",
  authDomain: "drawing-flower.firebaseapp.com",
  projectId: "drawing-flower",
  storageBucket: "drawing-flower.firebasestorage.app",
  messagingSenderId: "YOUR_SENDER_ID",
  appId: "YOUR_APP_ID",
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
  button:  { fontSize: '20px', fontWeight: '800', letterSpacing: '0.5px', fontFamily: '"Noto Sans KR", sans-serif' },
};

const ROWS = 8, COLS = 9;
const NORM_W = 180, NORM_H = 160;
const OUTPUT_AREA_W = 200.0, OUTPUT_AREA_H = 200.0;
const OUTPUT_GAP = 2.0, OUTPUT_BASE_X = 0.0, OUTPUT_BASE_Z = -30.0;
const PRICE_PER_FLOWER = 2000;

function preprocessImage(imageData, threshold, margin, symmetry) {
  const { width, height, data } = imageData;
  const binary = new Uint8Array(width * height);
  for (let i = 0; i < width * height; i++) {
    const gray = 0.299 * data[i*4] + 0.587 * data[i*4+1] + 0.114 * data[i*4+2];
    binary[i] = gray < threshold ? 0 : 255;
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
  const cellW = OUTPUT_AREA_W / COLS, cellH = OUTPUT_AREA_H / ROWS;
  const coords = {};
  let idx = 0;
  for (let row = ROWS - 1; row >= 0; row--)
    for (let col = 0; col < COLS; col++)
      if (pixelGrid[row * COLS + col])
        coords[String(idx++)] = {
          x: Math.round((OUTPUT_BASE_X + cellW / 2 + col * (cellW + OUTPUT_GAP)) * 10) / 10,
          y: 2.0,
          z: Math.round((cellH / 2 + (ROWS - 1 - row) * cellH + OUTPUT_BASE_Z) * 10) / 10,
          rx: 0.0, ry: 180.0, rz: 0.0,
        };
  return coords;
}

export default function App() {
  const [originalImage, setOriginalImage] = useState(null);
  const [hasPreview, setHasPreview]       = useState(false);
  const [status, setStatus]               = useState('idle');
  const [coords, setCoords]               = useState(null);
  const [pixelGrid, setPixelGrid]         = useState(Array(ROWS * COLS).fill(false));
  const [currentDocId, setCurrentDocId]   = useState(null);
  const [threshold, setThreshold]         = useState(160);
  const [margin, setMargin]               = useState(12);
  const [symmetry, setSymmetry]           = useState(true);
  const [progress]                        = useState(0);

  const normCanvasRef  = useRef(null);
  const pixelCanvasRef = useRef(null);
  const fileInputRef   = useRef(null);
  const unsubRef       = useRef(null);

  const robotStatus  = { isConnected: true, modelName: "Doosan M0609", isReady: true };
  const isRunning    = status === 'uploading' || status === 'processing';
  const canRun       = robotStatus.isReady && !!originalImage && !isRunning;
  const canAccept    = !!originalImage && !['uploading', 'processing', 'accepting'].includes(status);
  const editorActive = !!originalImage;

  const flowerCount = pixelGrid.filter(Boolean).length;
  const totalPrice  = flowerCount * PRICE_PER_FLOWER;

  const runLocalPreprocess = useCallback((imgData, thresh, marg, sym) => {
    if (!imgData) return;
    const { normImageData, grid } = preprocessImage(imgData, thresh, marg, sym);
    if (!normImageData) return;
    const nc = normCanvasRef.current;
    if (nc) { nc.width = NORM_W; nc.height = NORM_H; nc.getContext('2d').putImageData(normImageData, 0, 0); }
    const pc = pixelCanvasRef.current;
    if (pc) {
      const cs = 20;
      pc.width = COLS * cs; pc.height = ROWS * cs;
      const ctx = pc.getContext('2d');
      ctx.imageSmoothingEnabled = false;
      for (let r = 0; r < ROWS; r++)
        for (let c = 0; c < COLS; c++) {
          ctx.fillStyle = grid[r * COLS + c] ? '#2C3E50' : '#FFFFFF';
          ctx.fillRect(c * cs, r * cs, cs, cs);
        }
    }
    setPixelGrid(grid);
    setHasPreview(true);
  }, []);

  useEffect(() => {
    if (originalImage?.imageData)
      runLocalPreprocess(originalImage.imageData, threshold, margin, symmetry);
  }, [threshold, margin, symmetry, originalImage, runLocalPreprocess]);

  useEffect(() => {
    document.body.style.margin = "0";
    document.body.style.padding = "0";
    document.body.style.overflow = "hidden";
  }, []);

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
      setStatus('idle'); setCoords(null); setCurrentDocId(null); setHasPreview(false);
      runLocalPreprocess(imageData, threshold, margin, symmetry);
    };
    img.src = url;
  };

  const handleRun = async () => {
    if (!originalImage || isRunning) return;
    setStatus('uploading');
    try {
      const { file } = originalImage;
      const docId = `images_${file.name}`;
      setCurrentDocId(docId);
      await uploadBytes(storageRef(storage, `images/${file.name}`), file);
      await setDoc(doc(db, 'pixel_jobs', docId), {
        file: `images/${file.name}`, status: 'pending',
        params: { threshold, margin, symmetry },
      });
      setStatus('processing');
      if (unsubRef.current) unsubRef.current();
      unsubRef.current = onSnapshot(doc(db, 'pixel_coords', docId), (snap) => {
        if (!snap.exists() || snap.data().status !== 'preprocessed') return;
        const grid = Array(ROWS * COLS).fill(false);
        (snap.data().text_preview || '').split('\n').forEach((rowStr, r) =>
          rowStr.trim().split(/\s+/).forEach((cell, c) => { if (cell === '■') grid[r * COLS + c] = true; })
        );
        setPixelGrid(grid); setStatus('preprocessed'); unsubRef.current?.();
      });
    } catch (err) { console.error(err); setStatus('error'); }
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
      setCoords(newCoords); setStatus('accepted');
    } catch (err) { console.error(err); setStatus('error'); }
  };

  const statusLabel = {
    idle:         '이미지를 선택하면 실시간 미리보기가 표시됩니다',
    uploading:    '⏫ 업로드 중...',
    processing:   '⚙️ 처리 중...',
    preprocessed: '✏️ 픽셀을 조정하고 ACCEPT를 누르세요',
    accepting:    '💾 좌표 저장 중...',
    accepted:     `✅ 완료 (좌표 ${coords ? Object.keys(coords).length : 0}개)`,
    error:        '❌ 오류 발생',
  }[status];

  return (
    <div style={styles.outerContainer}>
      <div style={styles.appWrapper}>

        {/* 헤더 */}
        <header style={styles.header}>
          <div style={{ ...typography.title, fontSize: '28px', color: colors.textDark }}>DRAWING-FLOWER v2.0</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <span style={{ ...typography.caption, fontSize: '16px', color: status === 'error' ? '#FA5252' : status === 'accepted' ? colors.accent : colors.textMedium }}>
              {statusLabel}
            </span>
            <div style={{ ...typography.caption, fontSize: '16px', fontWeight: 'bold', color: robotStatus.isReady ? '#40C057' : '#FA5252' }}>
              ● {robotStatus.modelName} - READY
            </div>
          </div>
        </header>

        <main style={styles.main}>
          {/* 상단 3단 뷰어 */}
          <section style={styles.topSection}>
            <div style={styles.viewerContainer}>
              <div style={{ ...typography.title, fontSize: '20px', color: colors.textDark, marginBottom: '8px' }}>원본 이미지</div>
              <div style={{ ...styles.viewerDisplay, cursor: 'pointer' }} onClick={() => fileInputRef.current?.click()}>
                {originalImage
                  ? <img src={originalImage.url} alt="original" style={styles.viewerImg} />
                  : <span style={{ ...typography.caption, fontSize: '18px' }}>클릭하여 이미지 선택</span>
                }
                <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFileChange} style={{ display: 'none' }} />
              </div>
            </div>

            <div style={styles.viewerContainer}>
              <div style={{ ...typography.title, fontSize: '20px', color: colors.textDark, marginBottom: '8px' }}>정규화된 이미지</div>
              <div style={styles.viewerDisplay}>
                {hasPreview
                  ? <canvas ref={normCanvasRef} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                  : <><span style={{ ...typography.caption, fontSize: '18px' }}>이미지를 선택하세요</span><canvas ref={normCanvasRef} style={{ display: 'none' }} /></>
                }
              </div>
            </div>

            <div style={styles.viewerContainer}>
              <div style={{ ...typography.title, fontSize: '20px', color: colors.textDark, marginBottom: '8px' }}>픽셀화된 이미지</div>
              <div style={styles.viewerDisplay}>
                {hasPreview
                  ? <canvas ref={pixelCanvasRef} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', imageRendering: 'pixelated' }} />
                  : <><span style={{ ...typography.caption, fontSize: '18px' }}>이미지를 선택하세요</span><canvas ref={pixelCanvasRef} style={{ display: 'none' }} /></>
                }
              </div>
            </div>
          </section>

          <section style={styles.bottomSection}>
            {/* 픽셀 에디터 */}
            <div style={{ ...styles.editorContainer, border: editorActive ? `2px solid ${colors.pastelBlue}` : '1px solid #F1F3F5' }}>
              <div style={{ ...styles.editorHeader, flexWrap: 'wrap', gap: '12px' }}>
                <div style={{ ...typography.title, fontSize: '20px', color: colors.textDark, flexShrink: 0 }}>픽셀 에디터</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '20px', flexWrap: 'wrap' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ ...typography.content, fontSize: '16px', color: colors.textMedium }}>Threshold</span>
                    <span style={{ ...typography.content, fontSize: '16px', color: colors.pastelBlue, minWidth: '32px', textAlign: 'right' }}>{threshold}</span>
                    <input type="range" min={0} max={255} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} style={{ ...styles.slider, width: '100px' }} />
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ ...typography.content, fontSize: '16px', color: colors.textMedium }}>Margin</span>
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

            {/* 우측 패널 */}
            <div style={styles.utilityPanel}>

              {/* 진행율 */}
              <div>
                <div style={{ ...typography.title, fontSize: '18px', textAlign: 'center', marginBottom: '14px' }}>진행율</div>
                <div style={styles.progressBarBg}><div style={{ ...styles.progressBarFill, width: `${progress}%` }} /></div>
                <div style={{ ...typography.content, fontSize: '16px', display: 'flex', justifyContent: 'space-between', marginTop: '10px' }}>
                  <span>{progress > 0 ? '작동중' : '대기중'}</span><span>{progress}%</span>
                </div>
              </div>

              {/* 꽃 개수 + 가격 */}
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

              {/* 좌표 미리보기 */}
              {coords && (
                <div style={{ backgroundColor: colors.appBg, borderRadius: '10px', padding: '12px', maxHeight: '100px', overflowY: 'auto' }}>
                  <div style={{ ...typography.caption, fontSize: '14px', marginBottom: '4px' }}>좌표 ({Object.keys(coords).length}개)</div>
                  <pre style={{ fontSize: '13px', margin: 0, color: colors.textDark, lineHeight: 1.6 }}>
                    {Object.entries(coords).slice(0, 4).map(([k, v]) => `${k}: [${v.x}, ${v.y}, ${v.z}]`).join('\n')}
                    {Object.keys(coords).length > 4 ? '\n...' : ''}
                  </pre>
                </div>
              )}

              {/* 버튼 */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <button style={{ ...styles.btn, ...typography.button, backgroundColor: canAccept ? colors.accent : '#ADB5BD', opacity: canAccept ? 1 : 0.5 }} disabled={!canAccept} onClick={handleAccept}>
                  {status === 'accepting' ? '저장 중...' : status === 'accepted' ? '✅ ACCEPTED' : 'ACCEPT'}
                </button>
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