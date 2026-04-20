import React, { useState, useEffect, useRef } from 'react';
import { RotateCcw, Zap, Eye, X as CloseIcon } from 'lucide-react';
// Firebase SDK 임포트
import { initializeApp } from 'firebase/app';
import { getDatabase, ref, set, serverTimestamp } from 'firebase/database';

// 1. Firebase 설정 (본인의 Firebase 콘솔 -> 프로젝트 설정에서 확인 가능)
const firebaseConfig = {
  databaseURL: "https://rokey-cobot-default-rtdb.asia-southeast1.firebasedatabase.app",
  // 필요한 경우 apiKey, projectId 등 다른 설정도 추가하세요.
};

const app = initializeApp(firebaseConfig);
const db = getDatabase(app);

const Editor = ({ data, onBack }) => {
  const [currentColor, setCurrentColor] = useState('#FF0000');
  const [grid, setGrid] = useState(data.initialGrid || Array(72).fill({ isOn: false, color: '' }));
  const [threshold, setThreshold] = useState(160);
  const [margin, setMargin] = useState(10);
  const canvasRef = useRef(null);

  const flowerSpecs = {
    '#FF0000': { name: '빨간 장미', price: 2500 },
    '#f7b1c1': { name: '핑크 장미', price: 2000 }
  };

  // --- 이미지 전처리 로직 (기존과 동일) ---
  const processImage = () => {
    if (!data.previewUrl || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    const img = new Image();
    img.crossOrigin = "Anonymous";
    img.src = data.previewUrl;
    img.onload = () => {
      canvas.width = img.width; canvas.height = img.height;
      ctx.drawImage(img, 0, 0);
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const pixels = imageData.data;
      let minX = canvas.width, minY = canvas.height, maxX = 0, maxY = 0;
      let hasForeground = false;
      for (let i = 0; i < pixels.length; i += 4) {
        const avg = (pixels[i] + pixels[i + 1] + pixels[i + 2]) / 3;
        if (avg < threshold) {
          const x = (i / 4) % canvas.width; const y = Math.floor((i / 4) / canvas.width);
          minX = Math.min(minX, x); maxX = Math.max(maxX, x);
          minY = Math.min(minY, y); maxY = Math.max(maxY, y);
          hasForeground = true;
        }
      }
      if (!hasForeground) return;
      const contentW = (maxX - minX) + (margin * 2);
      const contentH = (maxY - minY) + (margin * 2);
      const startX = minX - margin; const startY = minY - margin;
      const newGrid = [];
      for (let r = 0; r < 8; r++) {
        for (let c = 0; c < 9; c++) {
          const sampleX = startX + (c / 8) * contentW;
          const sampleY = startY + (r / 7) * contentH;
          let isFilled = false;
          if (sampleX >= 0 && sampleX < canvas.width && sampleY >= 0 && sampleY < canvas.height) {
            const pixelIdx = (Math.floor(sampleY) * canvas.width + Math.floor(sampleX)) * 4;
            isFilled = (pixels[pixelIdx] + pixels[pixelIdx + 1] + pixels[pixelIdx + 2]) / 3 < threshold;
          }
          newGrid.push({ isOn: isFilled, color: isFilled ? currentColor : '' });
        }
      }
      setGrid(newGrid);
    };
  };

  useEffect(() => { processImage(); }, [threshold, margin]);

  // --- [핵심] 리액트에서 Firebase로 직접 전송 ---
  const handleStartRobot = async () => {
    const area_w = 200.0, area_h = 200.0, cols = 9, rows = 8, gap = 2.0;
    const cell_w = area_w / cols;
    const cell_h = area_h / rows;
    const coords_dict = {};
    let idx = 0;

    // 준수님 알고리즘 적용하여 좌표 생성
    for (let r = rows - 1; r >= 0; r--) {
      for (let c = 0; c < cols; c++) {
        const gridIdx = r * cols + c;
        if (grid[gridIdx]?.isOn) {
          const real_x = 300 + (cell_w / 2) + c * (cell_w + gap);
          const real_z = (cell_h / 2) + (rows - 1 - r) * cell_h + 40;
          coords_dict[idx.toString()] = [
            parseFloat(real_x.toFixed(1)), 100.0, parseFloat(real_z.toFixed(1)), 0.0, 180.0, 0.0
          ];
          idx++;
        }
      }
    }

    try {
      // Firebase 직접 업로드
      const commandRef = ref(db, 'robot/commands');
      await set(commandRef, {
        coords: coords_dict,
        status: 'NEW_DATA_AVAILABLE',
        total_points: idx,
        updated_at: serverTimestamp() // Firebase 서버 시간
      });
      alert(`✅ 로봇 좌표 ${idx}개 전송 완료!`);
    } catch (error) {
      console.error("DB 전송 오류:", error);
      alert("전송 실패! Firebase 설정을 확인하세요.");
    }
  };

  // ... (이하 UI 및 handlePixelClick 로직은 이전과 동일)
  return (
    <div className="flex flex-col items-center justify-center w-screen h-screen bg-[#e0d5ce] p-6">
      <canvas ref={canvasRef} className="hidden" />
      <main className="w-full max-w-6xl bg-white rounded-3xl shadow-2xl overflow-hidden flex h-[750px]">
        {/* 왼쪽 그리드 */}
        <div className="flex-[1.2] bg-slate-950 flex flex-col items-center justify-center p-10 relative">
          <div className="w-[540px] h-[480px] bg-white rounded-xl grid grid-cols-9 grid-rows-8 gap-[1px] overflow-hidden border-[12px] border-slate-800">
            {grid.map((pixel, i) => (
              <button key={i} onClick={() => {
                const newGrid = [...grid];
                newGrid[i] = { isOn: !newGrid[i].isOn, color: !newGrid[i].isOn ? currentColor : '' };
                setGrid(newGrid);
              }} className="border border-slate-100/5 hover:border-indigo-400" 
                 style={{ backgroundColor: pixel.isOn ? pixel.color : 'transparent' }} />
            ))}
          </div>
        </div>
        {/* 오른쪽 패널 */}
        <div className="w-96 flex flex-col p-8 space-y-6">
          <h2 className="text-2xl font-black">ROBOT COMMAND</h2>
          <div className="space-y-4">
            <label className="text-xs font-bold text-slate-400">THRESHOLD: {threshold}</label>
            <input type="range" min="0" max="255" value={threshold} onChange={(e)=>setThreshold(parseInt(e.target.value))} className="w-full" />
            <label className="text-xs font-bold text-slate-400">MARGIN: {margin}px</label>
            <input type="range" min="-50" max="50" value={margin} onChange={(e)=>setMargin(parseInt(e.target.value))} className="w-full" />
          </div>
          <button onClick={handleStartRobot} className="w-full py-4 bg-indigo-600 text-white rounded-2xl font-bold flex items-center justify-center gap-2">
            <Zap size={18} /> 로봇 좌표 전송
          </button>
        </div>
      </main>
    </div>
  );
};

export default Editor;