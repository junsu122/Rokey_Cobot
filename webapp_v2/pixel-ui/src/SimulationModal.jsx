import { useEffect, useRef, useState, useCallback } from "react";

const ROSBRIDGE_URL = "ws://localhost:9090";

function drawFlower(ctx, cx, cy, size, color, opacity = 1.0) {
  ctx.save();
  ctx.globalAlpha = opacity;
  const petalCount = 6;
  const petalLen   = size * 1.2;
  const petalW     = size * 0.5;
  for (let i = 0; i < petalCount; i++) {
    const angle = (i / petalCount) * Math.PI * 2;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    ctx.beginPath();
    ctx.ellipse(0, -petalLen / 2, petalW / 2, petalLen / 2, 0, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.restore();
  }
  ctx.beginPath();
  ctx.arc(cx, cy, size * 0.35, 0, Math.PI * 2);
  ctx.fillStyle = "#F1C40F";
  ctx.fill();
  ctx.strokeStyle = "#E67E22";
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.restore();
}

function drawSparkle(ctx, cx, cy, size) {
  ctx.save();
  ctx.globalAlpha = 0.8;
  for (let i = 0; i < 8; i++) {
    const angle = (i / 8) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(angle) * (size + 2), cy + Math.sin(angle) * (size + 2));
    ctx.lineTo(cx + Math.cos(angle) * (size + 7), cy + Math.sin(angle) * (size + 7));
    ctx.strokeStyle = "#FA5252";
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
  ctx.restore();
}

export default function SimulationModal({ coords, onClose }) {
  const canvasRef    = useRef(null);
  const animFrameRef = useRef(null);
  const rosbridgeRef = useRef(null);

  const [connected, setConnected]       = useState(false);
  const [currentIdx, setCurrentIdx]     = useState(-1);
  const [isAnimating, setIsAnimating]   = useState(false);
  const [plantedCount, setPlantedCount] = useState(0);
  const [jointAngles, setJointAngles]   = useState([0, 0, 0, 0, 0, 0]);

  const animIdxRef = useRef(0);
  const currentRef = useRef(-1);
  const plantedRef = useRef(new Set());
  const frameRef   = useRef(0);

  const coordList = Object.entries(coords || {})
  .map(([, v]) => v)
  .sort((a, b) => {
    if (b.z !== a.z) return b.z - a.z;  // z 큰 것(아래)부터
    return a.x - b.x;                    // x 작은 것(왼쪽)부터
  });

  const xs = coordList.map(c => c.x);
  const zs = coordList.map(c => c.z);
  const minX = Math.min(...xs, 0)   - 30;
  const maxX = Math.max(...xs, 200) + 30;
  const minZ = Math.min(...zs, 0)   - 30;
  const maxZ = Math.max(...zs, 200) + 30;

  const toCanvas = useCallback((x, z, W, H) => {
    const px = (1 - (x - minX) / (maxX - minX)) * (W - 60) + 30;  // x 반전
    const py = (1 - (z - minZ) / (maxZ - minZ)) * (H - 60) + 30;  // z 반전
    return [px, py];
  }, [minX, maxX, minZ, maxZ]);

  const flowerColors = [
    "#E74C3C", "#FF6B9D", "#E67E22", "#F1C40F",
    "#2ECC71", "#3498DB", "#9B59B6", "#1ABC9C",
  ];

  const coordList = Object.entries(coords || {})
    .map(([, v]) => v)
    .sort((a, b) => {
      if (b.z !== a.z) return b.z - a.z;
      return a.x - b.x;
    });

  console.log("첫 번째 좌표:", coordList[0]);
  console.log("마지막 좌표:", coordList[coordList.length - 1]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    const cur     = currentRef.current;
    const planted = plantedRef.current;
    frameRef.current += 1;

    ctx.fillStyle = "#0d1117";
    ctx.fillRect(0, 0, W, H);

    for (let i = 0; i <= 12; i++) {
      const x = 40 + (i / 12) * (W - 80);
      const y = 40 + (i / 12) * (H - 80);
      ctx.strokeStyle = i % 3 === 0 ? "#1e2a1e" : "#161e16";
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, 40); ctx.lineTo(x, H - 40); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(40, y); ctx.lineTo(W - 40, y); ctx.stroke();
    }

    ctx.strokeStyle = "#1e3a1e";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(40, 40, W - 80, H - 80);

    ctx.fillStyle = "#3a5a3a";
    ctx.font = "11px monospace";
    ctx.fillText("X →", W - 38, H - 14);
    ctx.fillText("Z ↓", 4, 20);

    if (coordList.length === 0) return;

    coordList.forEach((c, i) => {
      if (planted.has(i)) return;
      const [px, py] = toCanvas(c.x, c.z, W, H);
      ctx.beginPath();
      ctx.arc(px, py, 8, 0, Math.PI * 2);
      ctx.strokeStyle = "#1e3a1e";
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#2a4a2a";
      ctx.font = "9px monospace";
      ctx.textAlign = "center";
      ctx.fillText(String(i), px, py - 12);
    });

    planted.forEach((i) => {
      if (i >= coordList.length) return;
      const c = coordList[i];
      const [px, py] = toCanvas(c.x, c.z, W, H);
      drawFlower(ctx, px, py, 50, flowerColors[i % flowerColors.length], 1.0);
    });

    if (cur >= 0 && cur < coordList.length) {
      const c = coordList[cur];
      const [px, py] = toCanvas(c.x, c.z, W, H);
      const color = flowerColors[cur % flowerColors.length];
      const pulse = Math.abs(Math.sin(frameRef.current * 0.1));

      ctx.beginPath();
      ctx.arc(px, py, 14 + pulse * 6, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(250, 82, 82, ${0.3 + pulse * 0.4})`;
      ctx.lineWidth = 2;
      ctx.stroke();

      drawSparkle(ctx, px, py, 10 + pulse * 3);
      drawFlower(ctx, px, py, 9, color, 0.7 + pulse * 0.3);

      ctx.fillStyle = "#FA5252";
      ctx.font = "bold 11px monospace";
      ctx.textAlign = "center";
      ctx.fillText(String(cur), px, py - 18);

      ctx.fillStyle = "rgba(13,17,23,0.9)";
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(10, H - 68, 220, 56, 8);
      else ctx.rect(10, H - 68, 220, 56);
      ctx.fill();
      ctx.strokeStyle = "#FA5252";
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = "#FA5252";
      ctx.font = "bold 12px monospace";
      ctx.textAlign = "left";
      ctx.fillText(`🌸 심는 중... idx: ${cur}`, 18, H - 48);
      ctx.fillStyle = "#c9d1d9";
      ctx.font = "11px monospace";
      ctx.fillText(`x:${c.x}  y:${c.y}  z:${c.z}`, 18, H - 28);
    }

    const [bx, by] = toCanvas((minX + maxX) / 2, (minZ + maxZ) / 2, W, H);
    ctx.beginPath();
    ctx.arc(bx, by, 10, 0, Math.PI * 2);
    ctx.fillStyle = "#339AF0";
    ctx.fill();
    ctx.strokeStyle = "#1971c2";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 9px monospace";
    ctx.textAlign = "center";
    ctx.fillText("R", bx, by + 3);
  }, [coordList, toCanvas, minX, maxX, minZ, maxZ, flowerColors]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => { canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight; };
    resize();
    window.addEventListener("resize", resize);
    const loop = () => { draw(); animFrameRef.current = requestAnimationFrame(loop); };
    loop();
    return () => { window.removeEventListener("resize", resize); cancelAnimationFrame(animFrameRef.current); };
  }, [draw]);

  useEffect(() => {
    const ws = new WebSocket(ROSBRIDGE_URL);
    rosbridgeRef.current = ws;
    ws.onopen = () => {
      setConnected(true);
      ws.send(JSON.stringify({ op: "subscribe", topic: "/dsr01/joint_states", type: "sensor_msgs/JointState" }));
    };
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.op === "publish" && msg.topic === "/dsr01/joint_states")
          setJointAngles((msg.msg?.position || []).map(r => (r * 180 / Math.PI).toFixed(1)));
      } catch (_) {}
    };
    ws.onerror = () => setConnected(false);
    ws.onclose = () => setConnected(false);
    return () => { if (ws.readyState === WebSocket.OPEN) ws.close(); };
  }, []);

  const startAnimation = () => {
    if (isAnimating || coordList.length === 0) return;
    plantedRef.current = new Set();
    setPlantedCount(0);
    setIsAnimating(true);
    animIdxRef.current = 0;

    const step = () => {
      const idx = animIdxRef.current;
      if (idx >= coordList.length) {
        // 마지막 꽃 심기
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

      const ws = rosbridgeRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        const c = coordList[idx];
        ws.send(JSON.stringify({ op: "publish", topic: "/dsr01/new_parameter", type: "std_msgs/Float64MultiArray", msg: { data: [c.x, c.y, c.z, c.rx, c.ry, c.rz] } }));
      }
      animIdxRef.current += 1;
      setTimeout(step, 800);
    };
    step();
  };

  const resetAnimation = () => {
    setIsAnimating(false);
    currentRef.current = -1;
    setCurrentIdx(-1);
    animIdxRef.current = 0;
    plantedRef.current = new Set();
    setPlantedCount(0);
  };

  return (
    <div style={s.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={s.modal}>

        {/* 헤더 */}
        <div style={s.header}>
          <div style={s.title}>🌸 꽃꽂이 시뮬레이션</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ ...s.badge, backgroundColor: connected ? '#1a3a1a' : '#2a1a1a', color: connected ? '#40C057' : '#FA5252' }}>
              {connected ? '● rosbridge 연결됨' : '● rosbridge 미연결'}
            </div>
            <button onClick={onClose} style={s.closeBtn}>✕</button>
          </div>
        </div>

        {/* 바디: 캔버스 + 우측 패널 */}
        <div style={s.body}>
          {/* 캔버스 */}
          <canvas ref={canvasRef} style={s.canvas} />

          {/* 우측 패널 */}
          <div style={s.panel}>

            {/* 버튼 먼저 (항상 보이도록) */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button onClick={startAnimation} disabled={isAnimating}
                style={{ ...s.btn, background: isAnimating ? '#1a2a3a' : 'linear-gradient(135deg, #2ECC71, #40C057)', color: isAnimating ? '#4a6a8a' : '#fff' }}>
                {isAnimating ? `🌸 심는 중... (${currentIdx + 1}/${coordList.length})` : '🌸 꽃 심기 시작'}
              </button>
              <button onClick={resetAnimation} style={{ ...s.btn, backgroundColor: '#2a2a3e', color: '#8b8ba0' }}>
                ↺ 초기화
              </button>
            </div>

            {/* 진행 상태 */}
            <div style={s.section}>
              <div style={s.sectionTitle}>진행 상태</div>
              <div style={{ backgroundColor: '#161625', borderRadius: '10px', padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '28px', fontWeight: '800', color: '#40C057', fontFamily: 'monospace' }}>
                  {plantedCount}<span style={{ fontSize: '13px', color: '#4a4a60' }}> / {coordList.length}</span>
                </div>
                <div style={{ height: '6px', backgroundColor: '#2a2a3e', borderRadius: '3px', marginTop: '8px' }}>
                  <div style={{ height: '100%', background: 'linear-gradient(90deg, #2ECC71, #40C057)', borderRadius: '3px', width: `${coordList.length > 0 ? (plantedCount / coordList.length) * 100 : 0}%`, transition: 'width 0.6s' }} />
                </div>
              </div>
            </div>

            {/* 조인트 상태 */}
            <div style={s.section}>
              <div style={s.sectionTitle}>조인트 상태 (deg)</div>
              {['J1','J2','J3','J4','J5','J6'].map((j, i) => (
                <div key={j} style={s.jointRow}>
                  <span style={s.jointLabel}>{j}</span>
                  <div style={s.jointBar}>
                    <div style={{ ...s.jointFill, width: `${Math.min(100, Math.abs(parseFloat(jointAngles[i] || 0)) / 180 * 100)}%` }} />
                  </div>
                  <span style={s.jointVal}>{jointAngles[i] ?? '—'}°</span>
                </div>
              ))}
            </div>

            {/* 좌표 목록 */}
            <div style={{ ...s.section, flex: 1, minHeight: 0 }}>
              <div style={s.sectionTitle}>좌표 목록 ({coordList.length}개)</div>
              <div style={s.coordList}>
                {coordList.map((c, i) => {
                  const isPlanted = plantedRef.current.has(i);
                  const isCurrent = i === currentIdx;
                  return (
                    <div key={i} style={{ ...s.coordItem, backgroundColor: isCurrent ? '#1a2a1a' : isPlanted ? '#0f1f0f' : '#161625', border: `1px solid ${isCurrent ? '#FA5252' : isPlanted ? '#2a5a2a' : '#2a2a3e'}` }}>
                      <span style={{ fontSize: '12px' }}>{isPlanted ? '🌸' : isCurrent ? '📍' : '○'}</span>
                      <span style={{ ...s.coordIdx, color: isCurrent ? '#FA5252' : isPlanted ? '#40C057' : '#4a4a60' }}>{i}</span>
                      <span style={s.coordVal}>[{c.x}, {c.z}]</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const s = {
  overlay:      { position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 },
  modal:        { width: '98vw', height: '94vh', maxWidth: '1400px', backgroundColor: '#0d1117', borderRadius: '20px', border: '1px solid #2a2a3e', display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: '0 40px 80px rgba(0,0,0,0.6)' },
  header:       { height: '52px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px', borderBottom: '1px solid #2a2a3e', flexShrink: 0 },
  title:        { fontSize: '16px', fontWeight: '700', color: '#e8e8f0', fontFamily: '"Noto Sans KR", sans-serif' },
  badge:        { padding: '4px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: '600', fontFamily: 'monospace' },
  closeBtn:     { width: '30px', height: '30px', borderRadius: '8px', border: 'none', backgroundColor: '#2a2a3e', color: '#8b8ba0', cursor: 'pointer', fontSize: '14px' },
  body:         { flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 },
  canvas:       { flex: 1, display: 'block', minWidth: 0 },
  panel:        { width: '240px', backgroundColor: '#161625', borderLeft: '1px solid #2a2a3e', padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px', overflowY: 'auto', flexShrink: 0 },
  section:      { display: 'flex', flexDirection: 'column', gap: '6px' },
  sectionTitle: { fontSize: '10px', fontWeight: '700', color: '#4a4a60', fontFamily: 'monospace', letterSpacing: '1px', textTransform: 'uppercase' },
  jointRow:     { display: 'flex', alignItems: 'center', gap: '6px' },
  jointLabel:   { fontSize: '11px', color: '#8b8ba0', fontFamily: 'monospace', minWidth: '18px' },
  jointBar:     { flex: 1, height: '4px', backgroundColor: '#2a2a3e', borderRadius: '2px', overflow: 'hidden' },
  jointFill:    { height: '100%', backgroundColor: '#339AF0', borderRadius: '2px', transition: 'width 0.3s' },
  jointVal:     { fontSize: '11px', color: '#c9d1d9', fontFamily: 'monospace', minWidth: '44px', textAlign: 'right' },
  coordList:    { display: 'flex', flexDirection: 'column', gap: '3px', overflowY: 'auto', flex: 1 },
  coordItem:    { display: 'flex', alignItems: 'center', gap: '6px', padding: '4px 8px', borderRadius: '6px', transition: 'all 0.3s' },
  coordIdx:     { fontSize: '11px', fontFamily: 'monospace', minWidth: '16px', fontWeight: '700' },
  coordVal:     { fontSize: '10px', color: '#6b6b80', fontFamily: 'monospace', flex: 1 },
  btn:          { padding: '10px', borderRadius: '10px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: '600', fontFamily: '"Noto Sans KR", sans-serif', transition: 'all 0.2s' },
};