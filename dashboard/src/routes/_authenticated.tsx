import { Sidebar } from "@/components/sidebar";
import { useAuth } from "@/context/auth-context";
import { currentUserOptions } from "@/api/queries";
import { useQuery } from "@tanstack/react-query";
import { Outlet, createFileRoute, redirect } from "@tanstack/react-router";
import { useEffect } from "react";

export const Route = createFileRoute("/_authenticated")({
  beforeLoad: () => {
    const token = localStorage.getItem("aml_token");
    if (!token) {
      throw redirect({ to: "/login" });
    }
  },
  component: AuthenticatedLayout,
});

function AuthenticatedLayout() {
  const { setUser } = useAuth();
  const { data: user } = useQuery(currentUserOptions());

  useEffect(() => {
    if (user) setUser(user);
  }, [user, setUser]);

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-7xl p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
