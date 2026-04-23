import React, { useState, useRef, useEffect, useCallback } from 'react';
import { initializeApp } from 'firebase/app';
import { getStorage, ref as storageRef, uploadBytes } from 'firebase/storage';
import { getFirestore, doc, setDoc } from 'firebase/firestore';

import { ROWS, COLS, NORM_W, NORM_H, PRICE_PER_FLOWER, colors, typography, styles } from './constants';
import { preprocessImage, gridToCoords } from './imageProcess';
import { drawGridWithFlowers } from './canvasDraw';
import FlowerSimulator from './FlowerSimulator';

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

  const robotStatus  = { modelName: 'Doosan M0609', isReady: true };
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
    document.body.style.margin = '0';
    document.body.style.padding = '0';
    document.body.style.overflow = 'hidden';
  }, []);

  useEffect(() => {
    const pc = pixelCanvasRef.current;
    if (!pc || !hasPreview) return;
    const cs = 20;
    pc.width = COLS * cs; pc.height = ROWS * cs;
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
        coords: newCoords, status: 'done', flowerCount, totalPrice,
      });
      setCoords(newCoords); setStatus('accepted');
      setShowSim(true); setPaused(false);
    } catch (err) { console.error(err); setStatus('error'); }
  };

  const handleCancel = async () => {
    if (!canCancel) return;
    try {
      await setDoc(doc(db, 'pixel_coords', 'cancel_signal'), {
        status: 'cancel',
        coords: { '0': { x: 0.0, y: 0.0, z: 0.0, rx: 0.0, ry: 0.0, rz: 0.0 } },
        timestamp: Date.now(),
      });
    } catch (err) { console.error(err); }
    handleReset();
  };

  const handlePause = async () => {
    setPaused(true);
    try {
      await setDoc(doc(db, 'pixel_coords', 'control_signal'), {
        status: 'pause',
        coords: { '0': { x: 1.0, y: 1.0, z: 1.0, rx: 1.0, ry: 1.0, rz: 1.0 } },
        timestamp: Date.now(),
      });
    } catch (err) { console.error(err); }
  };

  const handleResume = async () => {
    setPaused(false);
    try {
      await setDoc(doc(db, 'pixel_coords', 'control_signal'), {
        status: 'resume',
        coords: { '0': { x: 2.0, y: 2.0, z: 2.0, rx: 2.0, ry: 2.0, rz: 2.0 } },
        timestamp: Date.now(),
      });
    } catch (err) { console.error(err); }
  };

  const statusLabel = {
    idle:         '이미지를 선택하면 실시간 미리보기가 표시됩니다',
    uploading:    '⏫ 업로드 중...',
    processing:   '⚙️ 처리 중...',
    preprocessed: '✏️ 픽셀을 조정하고 주문하기를 누르세요',
    accepting:    '💾 좌표 저장 중...',
    accepted:     `✅ 완료 (좌표 ${coords ? Object.keys(coords).length : 0}개)`,
    cancelling:   '🚫 주문 취소 중...',
    cancelled:    '❌ 주문이 취소되었습니다',
    error:        '❌ 오류 발생',
  }[status];

  return (
    <div style={styles.outerContainer}>
      <div style={styles.appWrapper}>

        {/* 헤더 */}
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
              <div style={{ ...typography.title, fontSize: '20px', color: colors.textDark, marginBottom: '8px' }}>이미지 크기</div>
              <div style={styles.viewerDisplay}>
                {hasPreview
                  ? <canvas ref={normCanvasRef} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                  : <><span style={{ ...typography.caption, fontSize: '18px' }}>이미지를 선택하세요</span><canvas ref={normCanvasRef} style={{ display: 'none' }} /></>
                }
              </div>
            </div>
            <div style={styles.viewerContainer}>
              <div style={{ ...typography.title, fontSize: '20px', color: colors.textDark, marginBottom: '8px' }}>미리보기</div>
              <div style={styles.viewerDisplay}>
                {hasPreview
                  ? <canvas ref={pixelCanvasRef} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                  : <><span style={{ ...typography.caption, fontSize: '18px' }}>이미지를 선택하세요</span><canvas ref={pixelCanvasRef} style={{ display: 'none' }} /></>
                }
              </div>
            </div>
          </section>

          <section style={styles.bottomSection}>
            {/* 픽셀 에디터 OR 시뮬레이션 */}
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

            {/* 우측 패널 */}
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
