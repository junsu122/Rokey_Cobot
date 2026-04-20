import React, { useState, useCallback } from 'react';
import { Camera, Send, X, Circle, Square, Triangle } from 'lucide-react';
import Cropper from 'react-easy-crop'; 
import Editor from './Editor';

const RobotFloristApp = () => {
  const [image, setImage] = useState(null);
  const [selectedShape, setSelectedShape] = useState(null); 
  const [status, setStatus] = useState('idle');
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [pixelData, setPixelData] = useState(null);

  // 크롭 관련 상태
  const [tempImage, setTempImage] = useState(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState(null);

  // 파일 선택 핸들러
  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const url = URL.createObjectURL(file);
      setImage(url);
      setSelectedShape(null);
    }
  };

  const generate8x8Grid = (ctx) => {
    const grid = Array(8 * 8).fill({ isOn: false, color: '' });
    const cellSize = 200 / 8;

    for (let row = 0; row < 8; row++) {
      for (let col = 0; col < 8; col++) {
        const x = col * cellSize + cellSize / 2;
        const y = row * cellSize + cellSize / 2;
        const pixel = ctx.getImageData(x, y, 1, 1).data;
        
        const brightness = (pixel[0] + pixel[1] + pixel[2]) / 3;
        if (pixel[3] > 128 && brightness < 210) { 
          grid[row * 8 + col] = { isOn: true, color: '#FF0000' };
        }
      }
    }
    return grid;
  };

  const onCropComplete = useCallback((_, pixels) => {
    setCroppedAreaPixels(pixels);
  }, []);

  const handleOrderClick = () => {
    if (image) {
      setTempImage(image);
    } else if (selectedShape) {
      const shapeGrid = Array(8 * 8).fill({ isOn: false, color: '' });
      for (let i = 0; i < 64; i++) {
        const r = Math.floor(i / 8);
        const c = i % 8;
        if (selectedShape === 'circle') {
          const dist = Math.sqrt(Math.pow(r - 3.5, 2) + Math.pow(c - 3.5, 2));
          if (dist > 2.2 && dist < 3.6) shapeGrid[i] = { isOn: true, color: '#FF0000' };
        } else if (selectedShape === 'square') {
          if (r === 1 || r === 6 || c === 1 || c === 6) shapeGrid[i] = { isOn: true, color: '#FF0000' };
        } else if (selectedShape === 'triangle') {
          if (r + c === 7 || r === c || (r === 6 && c > 0 && c < 7)) shapeGrid[i] = { isOn: true, color: '#FF0000' };
        }
      }
      setPixelData({ previewUrl: null, initialGrid: shapeGrid, isShape: true });
      setIsEditorOpen(true);
    }
  };

  const handleCropSave = async () => {
    setStatus('uploading');
    const img = new Image();
    img.src = tempImage;
    img.onload = () => {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      canvas.width = 200; canvas.height = 200;
      ctx.drawImage(img, croppedAreaPixels.x, croppedAreaPixels.y, croppedAreaPixels.width, croppedAreaPixels.height, 0, 0, 200, 200);

      const analyzedGrid = generate8x8Grid(ctx);
      setPixelData({ 
        previewUrl: canvas.toDataURL(),
        initialGrid: analyzedGrid,
        isShape: false
      });
      setTempImage(null);
      setIsEditorOpen(true);
      setStatus('idle');
    };
  };

  if (isEditorOpen && pixelData) {
    return <Editor data={pixelData} onBack={() => { setIsEditorOpen(false); setStatus('idle'); }} />;
  }

  return (
    <div className="flex flex-col items-center justify-center w-screen h-screen bg-[#e0d5ce]">
      {tempImage && (
        <div className="fixed inset-0 z-50 bg-black/90 flex flex-col items-center justify-center p-4 backdrop-blur-sm">
          <div className="w-full max-w-xl bg-slate-900 rounded-3xl overflow-hidden shadow-2xl">
            <div className="p-6 border-b border-white/10 flex justify-between items-center text-white font-bold">이미지 영역 선택 (200x200) <button onClick={() => setTempImage(null)}><X /></button></div>
            <div className="relative h-[400px] w-full bg-black">
              <Cropper image={tempImage} crop={crop} zoom={zoom} aspect={1} onCropChange={setCrop} onCropComplete={onCropComplete} onZoomChange={setZoom} />
            </div>
            <div className="p-6 flex gap-4">
              <button onClick={() => setTempImage(null)} className="flex-1 py-4 bg-white/10 text-white rounded-2xl">취소</button>
              <button onClick={handleCropSave} className="flex-[2] py-4 bg-indigo-600 text-white rounded-2xl font-black shadow-lg shadow-indigo-500/20">에디터 이동</button>
            </div>
          </div>
        </div>
      )}

      <header className="mb-10 text-center">
        <h1 className="text-3xl font-bold text-[#1e293b]">Drawing Flower</h1>
        <p className="text-[#64748b]">로봇 꽃꽂이 주문 시스템</p>
      </header>

      <main className="w-full max-w-3xl bg-white rounded-3xl shadow-2xl p-8 border border-slate-100 flex items-center gap-2">
        <div className="relative flex-1 h-64 border-2 border-dashed border-slate-300 rounded-2xl flex flex-col items-center justify-center overflow-hidden bg-slate-50">
          {image ? (
            <>
              <img src={image} alt="Preview" className="w-full h-full object-cover opacity-80" />
              <button onClick={() => setImage(null)} className="absolute top-3 right-3 p-2 bg-white/80 rounded-full shadow-md text-slate-600 hover:text-red-500 z-10"><X size={20} /></button>
            </>
          ) : (
            <>
              <Camera size={48} className="text-slate-400 mb-2" />
              <p className="text-slate-400 font-medium">사진 업로드</p>
              <input type="file" className="absolute inset-0 opacity-0 cursor-pointer" onChange={handleImageChange} accept="image/*" />
            </>
          )}
        </div>
        <div className="px-6 flex flex-col items-center text-black font-black text-[20pt]">OR</div>
        <div className="w-72 flex flex-col justify-between h-64">
          <div>
            <h2 className="text-lg font-semibold text-slate-700 mb-4">도형 선택</h2>
            <div className="grid grid-cols-3 gap-2">
              {['circle', 'square', 'triangle'].map((id) => (
                <button key={id} onClick={() => { setSelectedShape(id); setImage(null); }} className={`p-3 h-16 rounded-xl border-2 flex items-center justify-center transition-all ${selectedShape === id ? 'border-indigo-600 bg-indigo-50 text-indigo-600' : 'border-slate-200 text-slate-400'}`}>
                  {id === 'circle' && <Circle size={28} />} {id === 'square' && <Square size={28} />} {id === 'triangle' && <Triangle size={28} />}
                </button>
              ))}
            </div>
          </div>
          <button onClick={handleOrderClick} disabled={!image && !selectedShape} className={`w-full py-4 rounded-xl font-bold flex items-center justify-center gap-2 shadow-lg transition-all ${image || selectedShape ? 'bg-[#4f46e5] text-white hover:bg-[#4338ca]' : 'bg-slate-200 text-slate-400 cursor-not-allowed'}`}>
            {status === 'uploading' ? '데이터 분석 중...' : <><Send size={18} /> 주문하기</>}
          </button>
        </div>
      </main>
      <footer className="mt-10 text-slate-400 text-sm font-mono tracking-tighter">M0609 COBOT SYSTEM :: READY</footer>
    </div>
  );
};

export default RobotFloristApp;