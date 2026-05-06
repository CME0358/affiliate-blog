import { cookies } from "next/headers";
import AiscanLP from "@/components/AiscanLP";
import AiscanLP_B from "@/components/AiscanLP_B";

export default async function Home() {
  const cookieStore = await cookies();
  const variant = cookieStore.get("geo_ab_variant")?.value ?? "A";

  return variant === "B" ? <AiscanLP_B /> : <AiscanLP />;
}
