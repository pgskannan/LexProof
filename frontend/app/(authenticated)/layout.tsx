import { AuthProvider } from "../../components/AuthProvider"

export default function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}