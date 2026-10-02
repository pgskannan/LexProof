import { SiteHeader } from "../../components/marketing/SiteHeader"

/** Public verification pages share the marketing site header (logo = back to home). */
export default function PublicVerifyLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SiteHeader />
      {children}
    </>
  )
}
