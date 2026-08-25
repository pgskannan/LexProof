import type { Metadata } from 'next'
import './globals.css'
import { Toaster } from 'sonner'
import { AuthProvider } from '../components/AuthProvider'

export const metadata: Metadata = {
  title: 'LexProof | Verifiable Legal Intelligence',
  description: 'Analyze. Prove. Monitor.',
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
        <Toaster richColors position="bottom-right" />
      </body>
    </html>
  )
}
