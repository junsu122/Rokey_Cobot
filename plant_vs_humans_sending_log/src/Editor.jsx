import React, { useState, useEffect } from 'react';
import { RotateCcw, Zap, Eye, X as CloseIcon } from 'lucide-react';

const Editor = ({ data, onBack }) => {
  const [currentColor, setCurrentColor] = useState('#FF0000');
  const [grid, setGrid] = useState(data.initialGrid || Array(8 * 8).fill({ isOn: false, color: '' }));
  const [isPreviewOpen, setIsPreviewOpen] = useState(false); // 미리보기 모달 상태

  const flowerSpecs = {
    '#FF0000': { name: '빨간 장미', price: 2500 },
    '#f7b1c1': { name: '핑크 장미', price: 2000 }
  };

  const handlePixelClick = (index) => {
    setGrid(prev => {
      const newGrid = [...prev];
      const pixel = newGrid[index];
      if (pixel.isOn && pixel.color === currentColor) {
        newGrid[index] = { isOn: false, color: '' };
      } else {
        newGrid[index] = { isOn: true, color: currentColor };
      }
      return newGrid;
    });
  };

  const redCount = grid.filter(p => p.isOn && p.color === '#FF0000').length;
  const pinkCount = grid.filter(p => p.isOn && p.color === '#f7b1c1').length;
  const customCount = grid.filter(p => p.isOn && !['#FF0000', '#f7b1c1'].includes(p.color)).length;
  const totalFlowers = grid.filter(p => p.isOn).length;
  const totalPrice = (redCount * 2500) + (pinkCount * 2000) + (customCount * 2200);

  return (
    <div className="flex flex-col items-center justify-center w-screen h-screen bg-[#e0d5ce] p-6">
      
      {/* --- 완성품 미리보기 모달 --- */}
      {isPreviewOpen && (
        <div className="fixed inset-0 z-[100] bg-black/80 backdrop-blur-md flex items-center justify-center p-6">
          <div className="bg-white w-full max-w-2xl rounded-3xl overflow-hidden shadow-2xl flex flex-col">
            <div className="p-6 border-b flex justify-between items-center bg-slate-50">
              <h3 className="font-bold text-slate-800 flex items-center gap-2">
                <Eye size={20} className="text-indigo-600" /> 로봇 꽃꽂이 시뮬레이션
              </h3>
              <button onClick={() => setIsPreviewOpen(false)} className="p-2 hover:bg-slate-200 rounded-full transition-colors">
                <CloseIcon size={24} />
              </button>
            </div>
            
            <div className="flex-1 p-10 flex flex-col items-center justify-center bg-gradient-to-b from-slate-50 to-slate-200">
              {/* 실제 꽃꽂이 느낌의 렌더링 영역 */}
              <div className="relative w-80 h-80 bg-white rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.1)] p-4 grid grid-cols-8 grid-rows-8 gap-1 border-b-8 border-slate-300">
                {grid.map((pixel, i) => (
                  <div key={i} className="flex items-center justify-center">
                    {pixel.isOn && (
                      <div 
                        className="w-full h-full rounded-full shadow-lg transform scale-110"
                        style={{ 
                          background: `radial-gradient(circle at 30% 30%, ${pixel.color}, #000)`,
                          boxShadow: `0 4px 6px -1px rgba(0,0,0,0.2), inset 0 2px 4px rgba(255,255,255,0.3)`
                        }}
                      />
                    )}
                  </div>
                ))}
              </div>
              <p className="mt-10 text-slate-500 text-sm font-medium">로봇 M0609가 위의 미리보기 이미지처럼 꽃을 배치할 예정입니다.</p>
            </div>
            
            <div className="p-6 bg-white border-t flex justify-center">
              <button 
                onClick={() => setIsPreviewOpen(false)}
                className="px-8 py-3 bg-indigo-600 text-white rounded-xl font-bold hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-200"
              >
                에디터로 돌아가기
              </button>
            </div>
          </div>
        </div>
      )}

      <main className="w-full max-w-5xl bg-white rounded-3xl shadow-2xl overflow-hidden flex h-[700px] border border-slate-100">
        
        {/* 왼쪽: 그리드 작업실 */}
        <div className="flex-1 bg-slate-950 flex flex-col items-center justify-center p-10 relative">
          {/* 상단 액션 바 */}
          <div className="absolute top-6 right-6 flex gap-2">
            <button 
              onClick={() => setIsPreviewOpen(true)}
              className="px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-all flex items-center gap-2 text-xs font-bold shadow-lg"
            >
              <Eye size={16} /> 미리보기
            </button>
            <button 
              onClick={() => setGrid(Array(64).fill({ isOn: false, color: '' }))} 
              className="p-2 rounded-lg bg-white/5 text-slate-500 hover:text-white transition-all"
            >
              <RotateCcw size={18} />
            </button>
          </div>

          <div className="w-[480px] h-[480px] bg-white border-[12px] border-slate-800 rounded-xl relative grid grid-cols-8 grid-rows-8 gap-[1px] overflow-hidden"
               style={{ backgroundImage: data.previewUrl ? `url(${data.previewUrl})` : 'none', backgroundSize: 'cover', imageRendering: 'pixelated' }}>
            {data.previewUrl && <div className="absolute inset-0 bg-white/70 z-0"></div>}
            {grid.map((pixel, i) => (
              <button key={i} onClick={() => handlePixelClick(i)}
                      className="relative z-10 border border-slate-100/20 hover:border-indigo-400 transition-all"
                      style={{ backgroundColor: pixel.isOn ? pixel.color : 'transparent' }} />
            ))}
          </div>
          <p className="mt-6 text-indigo-400 text-xs font-mono tracking-widest uppercase opacity-60">M0609 Path Editor :: V1.2</p>
        </div>

        {/* 오른쪽 설정 패널 */}
        <div className="w-80 h-full flex flex-col border-l border-slate-100 bg-white">
          <div className="flex-1 overflow-y-auto p-8 space-y-8 custom-scrollbar">
            <h2 className="text-2xl font-bold text-slate-900 tracking-tight">꽃 구성 편집</h2>
            
            {/* 장미 품종 선택 */}
            <div className="space-y-3">
              <p className="text-sm text-slate-600 font-bold">장미 품종 (Brush)</p>
              {Object.keys(flowerSpecs).map(color => (
                <button 
                  key={color} 
                  onClick={() => setCurrentColor(color)}
                  className={`w-full flex items-center justify-between p-3 rounded-xl border-2 transition-all ${currentColor === color ? 'border-indigo-600 bg-indigo-50' : 'border-slate-100 bg-white hover:border-slate-200'}`}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-6 h-6 rounded-full shadow-inner border border-black/5" style={{ backgroundColor: color }} />
                    <span className="text-sm font-bold text-slate-700">{flowerSpecs[color].name}</span>
                  </div>
                  <span className="text-[10px] font-mono text-slate-400">{flowerSpecs[color].price}원</span>
                </button>
              ))}
              <input type="color" value={currentColor} onChange={(e) => setCurrentColor(e.target.value)} className="w-full h-10 rounded-lg cursor-pointer border border-slate-200 bg-white p-1" />
            </div>

            {/* 수량 정보 */}
            <div className="pt-6 border-t border-slate-100 space-y-4">
              <p className="text-sm text-slate-600 font-bold">수량 합계</p>
              <div className="space-y-2 text-sm text-slate-500">
                <div className="flex justify-between"><span>빨간 장미</span><span className="font-bold text-slate-800">{redCount}송이</span></div>
                <div className="flex justify-between"><span>핑크 장미</span><span className="font-bold text-slate-800">{pinkCount}송이</span></div>
                {customCount > 0 && <div className="flex justify-between text-indigo-500 font-medium"><span>커스텀 컬러</span><span>{customCount}송이</span></div>}
              </div>
              <div className="bg-slate-900 p-4 rounded-2xl text-center text-white shadow-inner">
                <p className="text-[10px] text-slate-400 uppercase tracking-widest mb-1">Total Flowers</p>
                <p className="text-2xl font-black">{totalFlowers} <span className="text-sm font-normal text-slate-500">/ 64</span></p>
              </div>
            </div>

            {/* 최종 가격 */}
            <div className="pt-6 border-t border-slate-100 flex flex-col items-end">
              <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Estimated Total</p>
              <p className="text-3xl font-black text-indigo-600 tracking-tighter">₩ {totalPrice.toLocaleString()}</p>
            </div>
          </div>

          <div className="p-8 border-t border-slate-100 bg-white shadow-[0_-4px_20px_rgba(0,0,0,0.02)]">
            <button className="w-full py-4 bg-slate-950 text-white rounded-2xl font-bold hover:bg-black transition-all shadow-xl active:scale-95 flex items-center justify-center gap-2">
              <Zap size={18} className="text-indigo-400" /> 로봇 전송 시작
            </button>
            <button onClick={onBack} className="w-full mt-4 text-slate-400 text-xs underline text-center hover:text-slate-600 transition-colors">
              돌아가기
            </button>
          </div>
        </div>
      </main>

      <style dangerouslySetInnerHTML={{ __html: `
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #e2e8f0; border-radius: 10px; }
        @keyframes pulse-soft { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
      ` }} />
    </div>
  );
};

export default Editor;