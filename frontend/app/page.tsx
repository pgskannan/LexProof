import { redirect } from "next/navigation"

// The root URL has no page of its own. Send visitors to the dashboard;
// AuthProvider forwards anyone who is not signed in to /login.
export default function RootPage() {
  redirect("/dashboard")
}
