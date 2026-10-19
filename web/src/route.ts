import { useEffect, useState } from "react";

// Hash routes keep the dashboard a set of static files the agent can serve as-is.
export type Route =
  | { page: "home" }
  | { page: "live" }
  | { page: "sessions" }
  | { page: "pick" }
  | { page: "session"; id: number }
  | { page: "compare"; session: number; lap: number; refSession?: number; refLap?: number };

export function parseRoute(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#\/?/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const params = new URLSearchParams(query);
  const num = (key: string) => {
    const value = params.get(key);
    return value === null || value === "" ? undefined : Number(value);
  };
  if (parts[0] === "live") return { page: "live" };
  if (parts[0] === "sessions" && parts[1]) return { page: "session", id: Number(parts[1]) };
  if (parts[0] === "sessions") return { page: "sessions" };
  if (parts[0] === "compare") {
    const session = num("session");
    const lap = num("lap");
    if (session !== undefined && lap !== undefined) {
      return { page: "compare", session, lap, refSession: num("ref_session"), refLap: num("ref_lap") };
    }
    return { page: "pick" };
  }
  return { page: "home" };
}

export function href(route: Route): string {
  switch (route.page) {
    case "home":
      return "#/";
    case "live":
      return "#/live";
    case "sessions":
      return "#/sessions";
    case "pick":
      return "#/compare";
    case "session":
      return `#/sessions/${route.id}`;
    case "compare": {
      const query = new URLSearchParams({ session: String(route.session), lap: String(route.lap) });
      if (route.refSession !== undefined) query.set("ref_session", String(route.refSession));
      if (route.refLap !== undefined) query.set("ref_lap", String(route.refLap));
      return `#/compare?${query.toString()}`;
    }
  }
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parseRoute(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
