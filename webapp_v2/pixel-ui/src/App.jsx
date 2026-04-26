import React, { useState, useRef, useEffect, useCallback } from 'react';
import { initializeApp } from 'firebase/app';
import { getStorage, ref as storageRef, uploadBytes } from 'firebase/storage';
import { getFirestore, doc, setDoc, onSnapshot } from 'firebase/firestore';

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
  const [showSim, setShowSim]             = useState(false);
  const [paused, setPaused]               = useState(false);
  const [robotProgress, setRobotProgress] = useState(0);
  const [robotTotal, setRobotTotal]       = useState(0);
  const [currentFlower, setCurrentFlower] = useState(0);
  const [showCompleteModal, setShowCompleteModal]   = useState(false);
  const [showProtStopModal, setShowProtStopModal]   = useState(false);
  const [showEmrgStopModal, setShowEmrgStopModal] = useState(false);

  // 로봇 상태
  const [robotState, setRobotState] = useState({
    isConnected: false,
    hwState:     'STANDBY',
    jobStatus:   'idle',
  });

  const normCanvasRef  = useRef(null);
  const pixelCanvasRef = useRef(null);
  const fileInputRef   = useRef(null);
  const unsubRef       = useRef(null);
  const unsubRobotRef  = useRef(null);

  const canAccept = (!!originalImage || pixelGrid.some(Boolean)) && !['uploading', 'processing', 'accepting', 'cancelling'].includes(status) && !showSim;
  const canCancel    = status === 'accepted';
  const editorActive = !showSim;

  const flowerCount = pixelGrid.filter(Boolean).length;
  const totalPrice  = flowerCount * PRICE_PER_FLOWER;
  const progress    = robotTotal > 0 ? Math.round((robotProgress / robotTotal) * 100) : 0;

  // 로봇 상태 라벨
  const getRobotLabel = () => {
    if (!robotState.isConnected) return { text: 'DISCONNECTED', color: '#FA5252' };
    switch (robotState.hwState) {
      case 'Moving':     return { text: 'MOVING',    color: '#339AF0' };
      case 'SAFE_OFF':   return { text: 'SAFE OFF',  color: '#E67E22' }; // 사용 안함
      case 'Prot Stop':  return { text: 'PROT STOP', color: '#FA5252' };
      case 'Emrg Stop':  return { text: 'EMRG STOP', color: '#FA5252' };
      default:           return { text: 'READY',     color: '#40C057' };
    }
  };

  // 앱 시작 시 robot_status/dsr01 구독
  useEffect(() => {
    unsubRobotRef.current = onSnapshot(doc(db, 'robot_status', 'dsr01'), (snap) => {
      if (!snap.exists()) return;
      const data = snap.data();
      setRobotState({
        isConnected: data.robot_connected ?? false,
        hwState:     data.hw_state        ?? 'STANDBY',
        jobStatus:   data.job_status      ?? 'idle',
      });
      if (data.done             !== undefined) setRobotProgress(data.done);
      if (data.total            !== undefined) setRobotTotal(data.total);
      if (data.cur_flower_index !== undefined) setCurrentFlower(data.cur_flower_index);
    });
    return () => { if (unsubRobotRef.current) unsubRobotRef.current(); };
  }, []);

  // // PROT_STOP 감지
  // useEffect(() => {
  //   if (robotState.hwState === 'Prot Stop') {
  //     setShowProtStopModal(true);
  //   } else if (robotState.hwState === 'STANDBY' || robotState.hwState === 'Moving') {
  //     setShowProtStopModal(false);
  //   }
  // }, [robotState.hwState]);

  useEffect(() => {
    if (robotState.hwState === 'Prot Stop') {
      setShowProtStopModal(true);
    } else if (robotState.hwState === 'Emrg Stop') {
      setShowEmrgStopModal(true);
    } else if (robotState.hwState === 'STANDBY' || robotState.hwState === 'Moving') {
      setShowProtStopModal(false);
      setShowEmrgStopModal(false);
    }
  }, [robotState.hwState]);

  // 꽃심기 완료 감지
  useEffect(() => {
    if (robotTotal > 0 && robotProgress >= robotTotal && showSim) {
      setShowCompleteModal(true);
    }
  }, [robotProgress, robotTotal, showSim]);

  const handleReset = () => {
    if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
    setShowSim(false); setStatus('idle'); setCoords(null);
    setOriginalImage(null); setHasPreview(false); setPaused(false);
    setPixelGrid(Array(ROWS * COLS).fill(false));
    setCurrentDocId(null);
    setRobotProgress(0); setRobotTotal(0); setCurrentFlower(0);
    setShowCompleteModal(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleCancel = async () => {
    const confirmed = window.confirm('작업이 초기화 됩니다. 정말 취소 하시겠습니까?');
    if (!confirmed) return;
    try {
      await setDoc(doc(db, 'pixel_coords', 'cancel_signal'), {
        status: 'cancel',
        coords: { '0': { x: 0.0, y: 0.0, z: 0.0, rx: 0.0, ry: 0.0, rz: 0.0 } },
        timestamp: Date.now(),
      });
      await setDoc(doc(db, 'pixel_coords', 'job_status'), {
        done: 0, total: 0, status: 'cancelled', per_flower: [],
      });
      if (currentDocId) {
        await setDoc(doc(db, 'pixel_coords', currentDocId), {
          coords: {}, status: 'cancelled', flowerCount: 0, totalPrice: 0,
        });
      }
    } catch (err) { console.error(err); }
    handleReset();
  };

  // 완료 모달 확인 버튼
  const handleCompleteConfirm = async () => {
    setShowCompleteModal(false);
    try {
      await setDoc(doc(db, 'pixel_coords', 'job_status'), {
        done: 0, total: 0, status: 'completed', per_flower: [],
      });
      if (currentDocId) {
        await setDoc(doc(db, 'pixel_coords', currentDocId), {
          coords: {}, status: 'completed', flowerCount: 0, totalPrice: 0,
        });
      }
    } catch (err) { console.error(err); }
    handleReset();
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
    if (!pc) return;  // hasPreview 조건 제거
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
    const hasEdgeCell = pixelGrid.some((filled, i) => {
      if (!filled) return false;
      const row = Math.floor(i / COLS), col = i % COLS;
      return row === 0 || row === ROWS - 1 || col === 0 || col === COLS - 1;
    });
    if (hasEdgeCell) { alert('꽃 심는 범위를 벗어났습니다.'); return; }

    const confirmed = window.confirm(`${flowerCount}송이 / ${totalPrice.toLocaleString()}원 주문하시겠습니까?`);
    if (!confirmed) return;

    const docId = currentDocId || `images_${originalImage?.file.name || 'manual'}`;
    if (!docId) return;
    setCurrentDocId(docId); setStatus('accepting');
    try {
      const newCoords = gridToCoords(pixelGrid, symmetry);
      await setDoc(doc(db, 'pixel_coords', docId), {
        coords: newCoords, status: 'done', flowerCount, totalPrice,
      });
      setCoords(newCoords);
      setStatus('accepted');
      setShowSim(true);
      setPaused(false);
      setRobotProgress(0);
      setRobotTotal(flowerCount);
      setCurrentFlower(0);
    } catch (err) { console.error(err); setStatus('error'); }
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
    idle:         originalImage ? '크기 조정과 픽셀 수정을 하시고 주문해주세요' : '이미지를 선택하면 실시간 미리보기가 표시됩니다',
    uploading:    '⏫ 업로드 중...',
    processing:   '⚙️ 처리 중...',
    preprocessed: '✏️ 픽셀을 조정하고 주문하기를 누르세요',
    accepting:    '💾 좌표 저장 중...',
    accepted:     paused ? '⏸ 일시정지' : `🌸 작업 중 (${coords ? Object.keys(coords).length : 0}송이)`,
    cancelling:   '🚫 주문 취소 중...',
    cancelled:    '❌ 주문이 취소되었습니다',
    error:        '❌ 오류 발생',
  }[status];

  const { text: robotText, color: robotColor } = getRobotLabel();

  return (
    <div style={styles.outerContainer}>
      <div style={styles.appWrapper}>

        {/* 완료 모달 */}
        {showCompleteModal && (
          <div style={{
            position: 'fixed', inset: 0,
            backgroundColor: 'rgba(0,0,0,0.6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 999,
          }}>
            <div style={{
              background: 'linear-gradient(135deg, #fff9fc 0%, #fff0f6 100%)',
              borderRadius: '28px',
              padding: '56px 64px',
              textAlign: 'center',
              boxShadow: '0 32px 80px rgba(233,100,128,0.25)',
              border: '1.5px solid #ffd6e7',
              minWidth: '340px',
            }}>
              <div style={{ fontSize: '72px', marginBottom: '8px', lineHeight: 1 }}>💐</div>
              <div style={{
                fontSize: '13px', fontWeight: '600', letterSpacing: '3px',
                color: '#E64980', marginBottom: '12px',
                fontFamily: '"Noto Sans KR", sans-serif', textTransform: 'uppercase',
              }}>
                DRAWING FLOWER
              </div>
              <div style={{
                fontSize: '30px', fontWeight: '900', color: '#2C3E50',
                marginBottom: '6px', fontFamily: '"Noto Sans KR", sans-serif',
                letterSpacing: '-0.5px',
              }}>
                완성되었습니다!
              </div>
              <div style={{
                fontSize: '15px', color: '#ADB5BD', marginBottom: '36px',
                fontFamily: '"Noto Sans KR", sans-serif',
              }}>
                꽃꽂이 작업이 완료되었어요 🌸
              </div>
              <button
                onClick={handleCompleteConfirm}
                style={{
                  padding: '16px 56px', borderRadius: '14px', border: 'none',
                  background: 'linear-gradient(135deg, #FF6B9D, #E64980)',
                  color: '#fff', fontSize: '18px', fontWeight: '800',
                  fontFamily: '"Noto Sans KR", sans-serif', cursor: 'pointer',
                  boxShadow: '0 8px 24px rgba(230,73,128,0.35)',
                  letterSpacing: '0.5px',
                }}
              >
                확인
              </button>
            </div>
          </div>
        )}

        {/* PROT_STOP 모달 */}
        {showProtStopModal && (
          <div style={{
            position: 'fixed', inset: 0,
            backgroundColor: 'rgba(0,0,0,0.7)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 998,
          }}>
            <div style={{
              background: 'linear-gradient(135deg, #fff9f0 0%, #fff3e0 100%)',
              borderRadius: '28px',
              padding: '56px 72px',
              textAlign: 'center',
              boxShadow: '0 32px 80px rgba(230,119,0,0.3)',
              border: '2px solid #FFB347',
              minWidth: '420px',
            }}>
              <div style={{ fontSize: '80px', marginBottom: '16px', lineHeight: 1 }}>⚠️</div>
              <div style={{
                fontSize: '13px', fontWeight: '700', letterSpacing: '4px',
                color: '#E67E22', marginBottom: '14px',
                fontFamily: '"Noto Sans KR", sans-serif',
              }}>
                PROT STOP
              </div>
              <div style={{
                fontSize: '32px', fontWeight: '900', color: '#2C3E50',
                marginBottom: '12px', fontFamily: '"Noto Sans KR", sans-serif',
                letterSpacing: '-0.5px',
              }}>
                안전 정지(충돌 감지) 상태입니다
              </div>
              <div style={{
                fontSize: '18px', fontWeight: '500', color: '#7F8C8D',
                fontFamily: '"Noto Sans KR", sans-serif', lineHeight: 1.6,
              }}>
                장애물을 치워주세요.<br/>
                <span style={{ fontSize: '15px', color: '#ADB5BD' }}>장애물 제거 후 관리자에게 문의하세요.</span>
              </div>
            </div>
          </div>
        )}

        {/* EMRG_STOP 모달 */}
        {showEmrgStopModal && (
          <div style={{
            position: 'fixed', inset: 0,
            backgroundColor: 'rgba(0,0,0,0.75)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 997,
          }}>
            <div style={{
              background: 'linear-gradient(135deg, #fff5f5 0%, #ffe0e0 100%)',
              borderRadius: '28px',
              padding: '56px 72px',
              textAlign: 'center',
              boxShadow: '0 32px 80px rgba(250,82,82,0.3)',
              border: '2px solid #FA5252',
              minWidth: '420px',
            }}>
              <div style={{ fontSize: '80px', marginBottom: '16px', lineHeight: 1 }}>🚨</div>
              <div style={{
                fontSize: '13px', fontWeight: '700', letterSpacing: '4px',
                color: '#FA5252', marginBottom: '14px',
                fontFamily: '"Noto Sans KR", sans-serif',
              }}>
                EMERGENCY STOP
              </div>
              <div style={{
                fontSize: '32px', fontWeight: '900', color: '#2C3E50',
                marginBottom: '12px', fontFamily: '"Noto Sans KR", sans-serif',
                letterSpacing: '-0.5px',
              }}>
                비상 정지 상태입니다
              </div>
              <div style={{
                fontSize: '18px', fontWeight: '500', color: '#7F8C8D',
                fontFamily: '"Noto Sans KR", sans-serif', lineHeight: 1.6,
              }}>
                관리자에게 문의하세요.<br/>
                <span style={{ fontSize: '15px', color: '#ADB5BD' }}>상태 복구 시 자동으로 해제됩니다.</span>
              </div>
            </div>
          </div>
        )}

        {/* 헤더 */}
        <header style={styles.header}>
          <div style={{ ...typography.title, fontSize: '28px', color: colors.textDark }}>DRAWING-FLOWER v2.0</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ ...typography.caption, fontSize: '16px', color: status === 'error' || status === 'cancelled' ? '#FA5252' : status === 'accepted' ? colors.accent : colors.textMedium }}>
              {statusLabel}
            </span>
            <div style={{ ...typography.caption, fontSize: '16px', fontWeight: 'bold', color: robotColor }}>
              ● Doosan M0609 - {robotText}
            </div>
            {showSim && (
              <button onClick={handleCancel}
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
                {(hasPreview || pixelGrid.some(Boolean)) 
                  ? <canvas ref={pixelCanvasRef} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                  : <><span style={{ ...typography.caption, fontSize: '18px' }}>이미지를 선택하세요</span><canvas ref={pixelCanvasRef} style={{ display: 'none' }} /></>
                }
              </div>
            </div>
          </section>

          <section style={styles.bottomSection}>
            {showSim ? (
              <div style={{ flex: 2.5, borderRadius: '16px', overflow: 'hidden' }}>
                <FlowerSimulator
                  coords={coords}
                  paused={paused}
                  robotProgress={robotProgress}
                  robotTotal={robotTotal}
                  currentFlower={currentFlower}
                />
              </div>
            ) : (
              <div style={{ ...styles.editorContainer, border: editorActive ? `2px solid ${colors.pastelBlue}` : '1px solid #F1F3F5' }}>
                <div style={{ ...styles.editorHeader, flexWrap: 'wrap', gap: '12px' }}>
                  <div style={{ ...typography.title, fontSize: '20px', color: colors.textDark, flexShrink: 0 }}>픽셀 에디터</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '20px', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ ...typography.content, fontSize: '16px', color: colors.textMedium }}>크기 조정</span>
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
              {showSim && (
                <div>
                  <div style={{ ...typography.title, fontSize: '18px', textAlign: 'center', marginBottom: '14px' }}>진행율</div>
                  <div style={styles.progressBarBg}><div style={{ ...styles.progressBarFill, width: `${progress}%` }} /></div>
                  <div style={{ ...typography.content, fontSize: '16px', display: 'flex', justifyContent: 'space-between', marginTop: '10px' }}>
                    <span>{progress > 0 ? '작동중' : '대기중'}</span>
                    <span>{robotTotal > 0 ? `${robotProgress} / ${robotTotal}` : `${progress}%`}</span>
                  </div>
                </div>
              )}

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

                {!showSim && (
                  <button
                    style={{ ...styles.btn, ...typography.button, backgroundColor: canAccept ? colors.accent : '#ADB5BD', opacity: canAccept ? 1 : 0.5 }}
                    disabled={!canAccept}
                    onClick={handleAccept}
                  >
                    {status === 'accepting' ? '저장 중...' : '주문하기'}
                  </button>
                )}

                {showSim && (
                  <button
                    style={{ ...styles.btn, ...typography.button, backgroundColor: canCancel ? '#FA5252' : '#ADB5BD', opacity: canCancel ? 1 : 0.4, fontSize: '25px' }}
                    disabled={!canCancel}
                    onClick={handleCancel}
                  >
                    {status === 'cancelling' ? '취소 중...' : status === 'cancelled' ? '취소됨' : '주문 취소'}
                  </button>
                )}
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}