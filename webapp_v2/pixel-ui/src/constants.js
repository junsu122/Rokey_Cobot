export const ROWS = 8;
export const COLS = 9;
export const NORM_W = 180;
export const NORM_H = 160;
export const OUTPUT_AREA_W = 200.0;
export const OUTPUT_AREA_H = 200.0;
export const OUTPUT_GAP = 2.0;
export const OUTPUT_BASE_X = 0.0;
export const OUTPUT_BASE_Z = 0.0;
export const PRICE_PER_FLOWER = 2000;
export const THRESHOLD = 210;

export const CELL_W = OUTPUT_AREA_W / COLS;
export const CELL_H = OUTPUT_AREA_H / ROWS;

export const FLOWER_COLORS = [
  "#E74C3C","#FF6B9D","#E67E22","#F1C40F",
  "#2ECC71","#3498DB","#9B59B6","#1ABC9C",
];

export const colors = {
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

export const typography = {
  title:   { fontSize: '40px', fontWeight: '800', letterSpacing: '-0.5px', fontFamily: '"Noto Sans KR", sans-serif' },
  content: { fontSize: '18px', fontWeight: '600', fontFamily: '"Noto Sans KR", sans-serif' },
  caption: { fontSize: '16px', fontWeight: '500', color: '#7F8C8D', fontFamily: '"Noto Sans KR", sans-serif' },
  button:  { fontSize: '25px', fontWeight: '800', letterSpacing: '0.5px', fontFamily: '"Noto Sans KR", sans-serif' },
};

export const styles = {
  outerContainer:  { height: '100vh', width: '100%', backgroundColor: '#F1F3F5', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', position: 'fixed', top: 0, left: 0, boxSizing: 'border-box' },
  appWrapper:      { width: '100vw', height: '90vh', maxWidth: '1600px', maxHeight: '1200px', backgroundColor: '#FFFFFF', borderRadius: '24px', boxShadow: '0 30px 60px rgba(0,0,0,0.1)', display: 'flex', flexDirection: 'column', overflow: 'hidden', border: '1px solid #E9ECEF', boxSizing: 'border-box' },
  header:          { height: '70px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 32px', borderBottom: '1px solid #F1F3F5', flexShrink: 0 },
  main:            { flex: 1, padding: '24px', display: 'flex', flexDirection: 'column', overflow: 'hidden', gap: '24px' },
  topSection:      { height: '30%', display: 'flex', gap: '24px' },
  viewerContainer: { flex: 1, display: 'flex', flexDirection: 'column' },
  viewerDisplay:   { flex: 1, backgroundColor: '#FAFAFF', border: '1px solid #F1F3F5', borderRadius: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  viewerImg:       { maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', borderRadius: '12px' },
  bottomSection:   { flex: 1, display: 'flex', gap: '24px', overflow: 'hidden' },
  editorContainer: { flex: 2.5, display: 'flex', flexDirection: 'column', backgroundColor: '#FFFFFF', borderRadius: '16px', padding: '20px 24px', boxSizing: 'border-box' },
  editorHeader:    { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' },
  canvasWrapper:   { flex: 1, backgroundColor: '#F1F3F5', borderRadius: '12px', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  canvas:          { width: '225px', height: '200px', backgroundColor: '#FFFFFF', border: '1px solid #E9ECEF' },
  pixelGrid:       { width: '100%', height: '100%', display: 'grid', gridTemplateColumns: 'repeat(9, 1fr)', gridTemplateRows: 'repeat(8, 1fr)' },
  pixel:           { border: '0.5px solid #F1F3F5', transition: 'background-color 0.1s' },
  utilityPanel:    { flex: 1, minWidth: '260px', backgroundColor: '#FAFAFF', borderRadius: '16px', padding: '24px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', boxSizing: 'border-box' },
  slider:          { width: '100%', height: '8px', cursor: 'pointer', borderRadius: '10px', appearance: 'none', backgroundColor: '#E9ECEF' },
  progressBarBg:   { height: '12px', backgroundColor: '#E9ECEF', borderRadius: '10px' },
  progressBarFill: { height: '100%', backgroundImage: 'linear-gradient(90deg, #E9C3E1 0%, #D3CDEE 100%)', borderRadius: '10px' },
  btn:             { height: '64px', color: '#FFFFFF', border: 'none', borderRadius: '16px', cursor: 'pointer', width: '100%', transition: 'background-color 0.2s', fontFamily: '"Noto Sans KR", sans-serif' },
};
