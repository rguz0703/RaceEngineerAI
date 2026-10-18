import { CompareView } from "./views/CompareView";
import { SessionsView } from "./views/SessionsView";
import { SessionView } from "./views/SessionView";
import { href, useRoute } from "./route";

export function App() {
  const route = useRoute();
  return (
    <>
      <header className="topbar">
        <a className="brand" href={href({ page: "sessions" })}>
          <span className="brand-mark" aria-hidden="true" />
          RaceEngineerAI
        </a>
      </header>
      <main className="page">
        {route.page === "sessions" && <SessionsView />}
        {route.page === "session" && <SessionView id={route.id} />}
        {route.page === "compare" && <CompareView key={JSON.stringify(route)} {...route} />}
      </main>
    </>
  );
}
