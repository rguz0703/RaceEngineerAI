import { useEffect, useRef, useState } from "react";
import { Nav } from "./components/Nav";
import { useRoute } from "./route";
import { useRecording } from "./useRecording";
import { CompareView } from "./views/CompareView";
import { HomeView } from "./views/HomeView";
import { LapView } from "./views/LapView";
import { LiveView } from "./views/LiveView";
import { PickView } from "./views/PickView";
import { SessionsView } from "./views/SessionsView";
import { SessionView } from "./views/SessionView";

export function App() {
  const route = useRoute();
  const control = useRecording();

  // Lists refresh whenever a recording finishes.
  const [version, setVersion] = useState(0);
  const lastSession = control.recording?.last_session_id ?? null;
  const seen = useRef(lastSession);
  useEffect(() => {
    if (lastSession !== seen.current) {
      seen.current = lastSession;
      setVersion((v) => v + 1);
    }
  }, [lastSession]);

  return (
    <>
      <Nav route={route} recording={control.recording} />
      <main className="page">
        {route.page === "home" && <HomeView control={control} version={version} />}
        {route.page === "live" && <LiveView control={control} />}
        {route.page === "sessions" && <SessionsView version={version} />}
        {route.page === "session" && <SessionView id={route.id} />}
        {route.page === "pick" && <PickView />}
        {route.page === "lap" && <LapView key={`${route.session}/${route.lap}`} session={route.session} lap={route.lap} />}
        {route.page === "compare" && <CompareView key={JSON.stringify(route)} {...route} />}
      </main>
    </>
  );
}
