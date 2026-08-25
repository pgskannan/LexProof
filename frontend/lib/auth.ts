import { GoogleAuthProvider, signInWithPopup, signOut, User } from "firebase/auth"
import { firebaseAuth } from "./firebase"

const provider = new GoogleAuthProvider()

export const auth = firebaseAuth
export const login = () => signInWithPopup(auth, provider)
export const logout = () => signOut(auth)
export type CurrentUser = User