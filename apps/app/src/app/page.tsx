import Link from "next/link";
import { redirect } from "next/navigation";

// Once Clerk is configured, replace this with:
//   import { auth } from "@clerk/nextjs/server";
//   const { userId, sessionClaims } = await auth();
//   const username = sessionClaims?.username as string | undefined;
//   if (userId && username) redirect(`/${username}`);

export default function Home() {
  // Redirect to sign-in — once Clerk is active, auth() above resolves username
  // and users land directly at /<username> instead of this splash page.
  redirect("/sign-in");
}
