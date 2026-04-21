import React, { useState, useRef, useEffect } from 'react';

// 1. 변수 통합 (Colors & Typography)
const colors = {
  textDark: '#2C3E50',
  textMedium: '#7F8C8D',
  pastelPink: '#E9C3E1',
  pastelPurple: '#D3CDEE',
  pastelBlue: '#339AF0',
  gridLine: '#F1F3F5',
  appBg: '#F1F3F5',
  panelBg: '#FFFFFF',
  viewerBg: '#FAFAFF',
};

const typography = {
  title: { fontSize: '24px', fontWeight: '800', letterSpacing: '-0.5px', fontFamily: '"Noto Sans KR", sans-serif' }, 
  content: { fontSize: '14px', fontWeight: '600', fontFamily: '"Noto Sans KR", sans-serif' }, 
  caption: { fontSize: '11px', fontWeight: '500', color: colors.textMedium, fontFamily: '"Noto Sans KR", sans-serif' },
  button: { fontSize: '16px', fontWeight: '800', letterSpacing: '0.5px', fontFamily: '"Noto Sans KR", sans-serif' }
};

const App = () => {
  const [progress, setProgress] = useState(0); 
  const [robotStatus, setRobotStatus] = useState({
    isConnected: true,
    modelName: "Doosan M0609",
    isReady: true
  });
  
  const [zoom, setZoom] = useState(1);
  const canvasWrapperRef = useRef(null);

  useEffect(() => {
    document.body.style.margin = "0";
    document.body.style.padding = "0";
    document.body.style.overflow = "hidden";

    const wrapper = canvasWrapperRef.current;
    if (!wrapper) return;
    const handleWheel = (e) => {
      e.preventDefault();
      const delta = e.deltaY * -0.001;
      setZoom((prevZoom) => Math.min(Math.max(0.5, prevZoom + delta), 3));
    };
    wrapper.addEventListener('wheel', handleWheel, { passive: false });
    return () => wrapper.removeEventListener('wheel', handleWheel);
  }, []);

  return (
    <div style={styles.outerContainer}>
      <div style={styles.appWrapper}>
        {/* 헤더 */}
        <header style={styles.header}>
          <div style={{ ...typography.title, fontSize: '14px', color: colors.textDark }}>
            DRAWING FLOWER v2.0
          </div>
          <div style={{
            ...typography.caption,
            fontWeight: 'bold',
            color: robotStatus.isReady ? '#40C057' : '#FA5252'
          }}>
            ● {robotStatus.isConnected ? `${robotStatus.modelName} - READY` : "DISCONNECTED"}
          </div>
        </header>

        <main style={styles.main}>
          {/* 상단 3단 뷰어 */}
          <section style={styles.topSection}>
            {["원본 이미지", "정규화된 이미지", "픽셀화된 이미지"].map((text, i) => (
              <div key={i} style={styles.viewerContainer}>
                <div style={{ ...typography.title, color: colors.textDark, marginBottom: '8px' }}>{text}</div>
                <div style={styles.viewerDisplay}>
                  <span style={typography.caption}>미리보기</span>
                </div>
              </div>
            ))}
          </section>

          <section style={styles.bottomSection}>
            {/* 좌측 에디터 */}
            <div style={styles.editorContainer}>
              <div style={styles.editorHeader}>
                <div style={{ ...typography.title, color: colors.textDark }}>픽셀 에디터</div>
                <div style={typography.caption}>Zoom: {Math.round(zoom * 100)}%</div>
              </div>
              <div style={styles.canvasWrapper} ref={canvasWrapperRef}>
                <div style={{ ...styles.canvas, transform: `scale(${zoom})`, transformOrigin: 'center' }}>
                  <div style={styles.pixelGrid}>
                    {Array.from({ length: 72 }).map((_, i) => (
                      <div key={i} style={styles.pixel} />
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* 우측 유틸리티 */}
            <div style={styles.utilityPanel}>
              <div>
                <div style={{ ...typography.title, textAlign: 'center', marginBottom: '20px' }}>파라미터</div>
                {["Threshold", "Margin (mm)"].map((label) => (
                  <div key={label} style={styles.sliderGroup}>
                    <div style={{ ...typography.content, textAlign: 'center', marginBottom: '10px' }}>{label}</div>
                    <input type="range" style={styles.slider} />
                  </div>
                ))}
              </div>

              <div style={styles.progressSection}>
                <div style={{ ...typography.title, textAlign: 'center', marginBottom: '15px' }}>진행율</div>
                <div style={styles.progressBarBg}>
                  <div style={{ ...styles.progressBarFill, width: `${progress}%` }}></div>
                </div>
                <div style={{ ...typography.content, display: 'flex', justifyContent: 'space-between', marginTop: '10px' }}>
                  <span>{progress > 0 ? "작동중" : "대기중"}</span>
                  <span>{progress}%</span>
                </div>
              </div>

              <button 
                style={{
                  ...styles.runButton,
                  ...typography.button,
                  backgroundColor: robotStatus.isReady ? colors.pastelBlue : '#ADB5BD',
                }}
                disabled={!robotStatus.isReady}
              >
                RUN SYSTEM
              </button>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
};

const styles = {
  outerContainer: { 
    height: '100vh', width: '100%', backgroundColor: colors.appBg, 
    display: 'flex', alignItems: 'center', justifyContent: 'center', 
    overflow: 'hidden', position: 'fixed', top: 0, left: 0, boxSizing: 'border-box'
  },
  appWrapper: { 
    width: '90vw', height: '85vh', maxWidth: '1200px', maxHeight: '800px',
    backgroundColor: colors.panelBg, borderRadius: '24px', boxShadow: '0 30px 60px rgba(0,0,0,0.1)', 
    display: 'flex', flexDirection: 'column', overflow: 'hidden', border: '1px solid #E9ECEF', boxSizing: 'border-box' 
  },
  header: { height: '55px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 30px', borderBottom: '1px solid #F1F3F5' },
  main: { flex: 1, padding: '25px', display: 'flex', flexDirection: 'column', gap: '20px', overflow: 'hidden' },
  topSection: { height: '28%', display: 'flex', gap: '20px' },
  viewerContainer: { flex: 1, display: 'flex', flexDirection: 'column' },
  viewerDisplay: { flex: 1, backgroundColor: colors.viewerBg, border: '1px solid #F1F3F5', borderRadius: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  bottomSection: { flex: 1, display: 'flex', gap: '25px', overflow: 'hidden' },
  editorContainer: { flex: 2.2, display: 'flex', flexDirection: 'column', backgroundColor: colors.panelBg, border: '1px solid #F1F3F5', borderRadius: '16px', padding: '20px', boxSizing: 'border-box' },
  editorHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '15px' },
  canvasWrapper: { flex: 1, backgroundColor: colors.appBg, borderRadius: '12px', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  canvas: { width: '225px', height: '200px', backgroundColor: '#FFFFFF', border: '1px solid #E9ECEF' },
  pixelGrid: { width: '100%', height: '100%', display: 'grid', gridTemplateColumns: 'repeat(9, 1fr)', gridTemplateRows: 'repeat(8, 1fr)' },
  pixel: { border: `0.5px solid ${colors.gridLine}` },
  utilityPanel: { flex: 1, minWidth: '260px', backgroundColor: colors.viewerBg, borderRadius: '16px', padding: '25px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', boxSizing: 'border-box' },
  sliderGroup: { marginBottom: '15px' },
  slider: { width: '100%', height: '6px', cursor: 'pointer', borderRadius: '10px', appearance: 'none', backgroundColor: '#E9ECEF' },
  progressSection: { margin: '10px 0' },
  progressBarBg: { height: '10px', backgroundColor: '#E9ECEF', borderRadius: '10px' },
  progressBarFill: { height: '100%', backgroundImage: `linear-gradient(90deg, ${colors.pastelPink} 0%, ${colors.pastelPurple} 100%)`, borderRadius: '10px' },
  runButton: { height: '60px', color: '#FFFFFF', border: 'none', borderRadius: '16px', cursor: 'pointer', boxShadow: '0 8px 20px rgba(51, 154, 240, 0.2)' }
};

export default App;