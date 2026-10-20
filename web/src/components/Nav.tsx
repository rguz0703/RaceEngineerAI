import type { Recording } from "../api";
import { href, type Route } from "../route";

const ICONS = {
  home: "M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
  live: "M3 12h4l2-6 4 12 2-6h6",
  sessions: "M4 6h16M4 12h16M4 18h10",
  compare: "M4 18 9 9l4 5 3-4 4 8M4 6h4M16 6h4",
};

const TABS: { route: Route; label: string; icon: keyof typeof ICONS; pages: Route["page"][] }[] = [
  { route: { page: "home" }, label: "Inicio", icon: "home", pages: ["home"] },
  { route: { page: "live" }, label: "En vivo", icon: "live", pages: ["live"] },
  { route: { page: "sessions" }, label: "Sesiones", icon: "sessions", pages: ["sessions", "session", "lap"] },
  { route: { page: "pick" }, label: "Comparar", icon: "compare", pages: ["pick", "compare"] },
];

export function Nav({ route, recording }: { route: Route; recording: Recording | null }) {
  const live = recording && (recording.state === "recording" || recording.state === "stopping");
  return (
    <header className="topbar">
      <a className="brand" href={href({ page: "home" })}>
        <span className="brand-mark" aria-hidden="true" />
        Race<b>Engineer</b>
      </a>
      <nav className="tabs" aria-label="Principal">
        {TABS.map((tab) => (
          <a
            key={tab.label}
            className={`tab${tab.pages.includes(route.page) ? " active" : ""}`}
            href={href(tab.route)}
            aria-current={tab.pages.includes(route.page) ? "page" : undefined}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d={ICONS[tab.icon]} />
            </svg>
            {tab.label}
          </a>
        ))}
      </nav>
      {live && (
        <a className="rec-pill" href={href({ page: "live" })}>
          <span className="dot rec" aria-hidden="true" /> REC · V{recording.lap}
        </a>
      )}
    </header>
  );
}
