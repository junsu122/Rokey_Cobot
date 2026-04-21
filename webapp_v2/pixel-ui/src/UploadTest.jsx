import { useState, useRef } from "react";
import { initializeApp } from "firebase/app";
import { getStorage, ref, uploadBytes } from "firebase/storage";
import { getFirestore, doc, onSnapshot } from "firebase/firestore";


// ── Firebase 설정 (Firebase 콘솔 → 프로젝트 설정 → 웹 앱 추가에서 복사) ──
const firebaseConfig = {
  apiKey: "AIzaSyBRkc41QAYFsRbWluMN1jOSAubOhydeeqk",
  authDomain: "drawing-flower.firebaseapp.com",
  projectId: "drawing-flower",
  storageBucket: "drawing-flower.firebasestorage.app",
  messagingSenderId: "637479342369",
  appId: "1:637479342369:web:1fd9f7a9d8f4dbe61fee60"
};

const app = initializeApp(firebaseConfig);
const storage = getStorage(app);
const db = getFirestore(app);

export default function UploadTest() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | uploading | processing | done | error
  const [coords, setCoords] = useState(null);
  const [docId, setDocId] = useState(null);
  const unsubRef = useRef(null);

  const handleFileChange = (e) => {
    const f = e.target.files[0];
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setStatus("idle");
    setCoords(null);
  };

  const handleUpload = async () => {
    if (!file) return;
    setStatus("uploading");
    setCoords(null);

    try {
      // Storage 업로드
      const storageRef = ref(storage, `images/${file.name}`);
      await uploadBytes(storageRef, file);
      setStatus("processing");

      // Firestore 문서 ID (run.py와 동일한 규칙)
      const id = `images_${file.name}`;
      setDocId(id);

      // Firestore 실시간 구독 → run.py가 저장하면 자동 수신
      if (unsubRef.current) unsubRef.current();
      unsubRef.current = onSnapshot(doc(db, "pixel_coords", id), (snap) => {
        if (snap.exists() && snap.data().status === "done") {
          setCoords(snap.data().coords);
          setStatus("done");
          unsubRef.current?.();
        }
      });
    } catch (err) {
      console.error(err);
      setStatus("error");
    }
  };

  const statusLabel = {
    idle: "",
    uploading: "⏫ Storage 업로드 중...",
    processing: "⚙️ 전처리 & 좌표 추출 대기 중...",
    done: "✅ 완료",
    error: "❌ 오류 발생",
  }[status];

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <h1 style={styles.title}>픽셀 좌표 추출 테스트</h1>
        <p style={styles.sub}>이미지를 업로드하면 전처리 후 Firestore에 좌표가 저장됩니다</p>

        {/* 파일 선택 */}
        <label style={styles.dropzone}>
          {preview ? (
            <img src={preview} alt="preview" style={styles.previewImg} />
          ) : (
            <span style={styles.dropText}>클릭하여 이미지 선택</span>
          )}
          <input type="file" accept="image/*" onChange={handleFileChange} style={{ display: "none" }} />
        </label>

        {/* 업로드 버튼 */}
        <button
          onClick={handleUpload}
          disabled={!file || status === "uploading" || status === "processing"}
          style={{
            ...styles.btn,
            opacity: !file || status === "uploading" || status === "processing" ? 0.4 : 1,
          }}
        >
          업로드 & 추출 시작
        </button>

        {/* 상태 */}
        {statusLabel && <p style={styles.statusText}>{statusLabel}</p>}

        {/* 좌표 결과 */}
        {coords && (
          <div style={styles.resultBox}>
            <p style={styles.resultTitle}>추출된 좌표 ({Object.keys(coords).length}개)</p>
            <pre style={styles.pre}>
              {"POS_COORDS = {\n"}
              {Object.entries(coords)
                .sort((a, b) => parseInt(a[0]) - parseInt(b[0]))
                .map(([k, v]) => `  ${k}: [${v.x}, ${v.y}, ${v.z}, ${v.rx}, ${v.ry}, ${v.rz}],`)
                .join("\n")}
              {"\n}"}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "#0f0f13",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "'IBM Plex Mono', monospace",
    padding: "24px",
  },
  card: {
    background: "#1a1a24",
    border: "1px solid #2e2e40",
    borderRadius: "16px",
    padding: "40px",
    width: "100%",
    maxWidth: "600px",
  },
  title: {
    color: "#e8e8f0",
    fontSize: "22px",
    fontWeight: 600,
    margin: "0 0 8px",
  },
  sub: {
    color: "#6b6b80",
    fontSize: "13px",
    margin: "0 0 28px",
  },
  dropzone: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    border: "1.5px dashed #3a3a50",
    borderRadius: "12px",
    height: "200px",
    cursor: "pointer",
    overflow: "hidden",
    marginBottom: "16px",
    background: "#13131c",
  },
  dropText: {
    color: "#4a4a60",
    fontSize: "14px",
  },
  previewImg: {
    maxWidth: "100%",
    maxHeight: "200px",
    objectFit: "contain",
  },
  btn: {
    width: "100%",
    padding: "14px",
    background: "#4f46e5",
    color: "#fff",
    border: "none",
    borderRadius: "10px",
    fontSize: "15px",
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: "inherit",
    transition: "opacity 0.2s",
  },
  statusText: {
    color: "#8b8ba0",
    fontSize: "13px",
    marginTop: "12px",
    textAlign: "center",
  },
  resultBox: {
    marginTop: "24px",
    background: "#0d0d14",
    border: "1px solid #2e2e40",
    borderRadius: "10px",
    padding: "20px",
  },
  resultTitle: {
    color: "#a0a0c0",
    fontSize: "13px",
    margin: "0 0 12px",
  },
  pre: {
    color: "#7dd3a8",
    fontSize: "12px",
    margin: 0,
    overflowX: "auto",
    lineHeight: 1.7,
  },
};
