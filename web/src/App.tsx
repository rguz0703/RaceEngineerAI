import { CompareView } from "./views/CompareView";
import { SessionsView } from "./views/SessionsView";
import { SessionView } from "./views/SessionView";
import { href, useRoute } from "./route";
import { useRecording } from "./useRecording";

export function App() {
  const route = useRoute();
  const control = useRecording();
  const recording = control.recording;
  const live = recording && (recording.state === "recording" || recording.state === "stopping");
  return (
    <>
      <header className="topbar">
        <a className="brand" href={href({ page: "sessions" })}>
          <span className="brand-mark" aria-hidden="true" />
          RaceEngineerAI
        </a>
        {live && (
          <a className="rec-pill" href={href({ page: "sessions" })}>
            <span className="dot rec" aria-hidden="true" /> Grabando · vuelta {recording.lap}
          </a>
        )}
      </header>
      <main className="page">
        {route.page === "sessions" && <SessionsView control={control} />}
        {route.page === "session" && <SessionView id={route.id} />}
        {route.page === "compare" && <CompareView key={JSON.stringify(route)} {...route} />}
      </main>
    </>
  );
}
