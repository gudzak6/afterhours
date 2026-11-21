import { redirect } from "next/navigation";

export default async function CoachPage({
  searchParams,
}: {
  searchParams: Promise<{ activity?: string }>;
}) {
  const params = await searchParams;
  const activity = params.activity;
  redirect(activity ? `/agent?activity=${encodeURIComponent(activity)}` : "/agent");
}
