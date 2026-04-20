import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";
import { getStorage } from "firebase/storage";
import { getDatabase, ref, push, serverTimestamp } from "firebase/database";

const firebaseConfig = {
  apiKey: import.meta.env.REACT_APP_FIREBASE_API_KEY,
  authDomain: import.meta.env.REACT_APP_FIREBASE_AUTH_DOMAIN,
  databaseURL: import.meta.env.REACT_APP_DATABASE_URL,
  projectId: import.meta.env.REACT_APP_PROJ_ID,
  storageBucket: import.meta.env.REACT_APP_BUCKET,
  messagingSenderId: import.meta.env.REACT_APP_SENDER_ID,
  appId: import.meta.env.REACT_ID_APPID
};

const app = initializeApp(firebaseConfig);

export const auth = getAuth(app);
export const firestore = getFirestore(app);
export const storage = getStorage(app);
export const rtdb = getDatabase(app);

export const logActivity = async (action, details = {}) => {
  try {
    const logRef = ref(rtdb, 'activity_logs');
    await push(logRef, {
      action,
      ...details,
      timestamp: serverTimestamp(),
    });
    console.log(`Log Success: ${action}`);
  } catch (error) {
    console.error("Firebase Log Error:", error);
  }
};

export { firestore as db }; 
export default app;