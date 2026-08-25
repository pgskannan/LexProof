import { initializeApp } from "firebase/app"
import { getAuth } from "firebase/auth"

const projectId = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID

if (projectId && projectId !== "lexproof-afc7c") {
  throw new Error("NEXT_PUBLIC_FIREBASE_PROJECT_ID must be lexproof-afc7c")
}

export const firebaseApp = initializeApp({
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY || "AIzaSyDemoBuildOnlyKey00000000000000000",
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || "lexproof-afc7c.firebaseapp.com",
  projectId: projectId || "lexproof-afc7c",
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET || "lexproof-afc7c.firebasestorage.app",
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || "missing-messaging-sender-id",
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID || "1:missing: web:missing",
})

export const firebaseAuth = getAuth(firebaseApp)