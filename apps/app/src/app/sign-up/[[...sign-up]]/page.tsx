import { redirect } from "next/navigation";

// Sign-up is not active yet. Send visitors to the sign-in page where
// they can access the demo account while auth is being configured.
export default function SignUpPage() {
  redirect("/sign-in");
}
