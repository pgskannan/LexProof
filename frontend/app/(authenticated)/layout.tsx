import { AuthProvider } from "../../components/AuthProvider"
import { Navigation } from "../../components/Navigation"
import { OrgProvider } from "../../components/OrgProvider"

export default function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <OrgProvider>
        <div className="flex">
          <Navigation />
          <main className="ml-64 flex-1 min-h-screen bg-gray-50">
            {children}
          </main>
        </div>
      </OrgProvider>
    </AuthProvider>
  )
}
