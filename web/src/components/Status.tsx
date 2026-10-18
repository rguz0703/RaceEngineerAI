import type { ReactNode } from "react";
import type { AsyncState } from "../useAsync";

export function Status<T>({ state, children }: { state: AsyncState<T>; children: (data: T) => ReactNode }) {
  if (state.status === "loading") return <p className="muted">Cargando…</p>;
  if (state.status === "error") return <p className="error">{state.message}</p>;
  return <>{children(state.data)}</>;
}
