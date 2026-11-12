import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { supabase } from "./supabaseClient";
import "./AuthGate.css";
import ActivityCalendarPage from "./ActivityCalendarPage";
import GroupAnalysisPage from "./GroupAnalysisPage";
import JobProgressPage from "./JobProgressPage";
import type { Task } from "./types";
import "./App.css";

type PageId = "activity-calendar" | "group-analysis" | "job-progress";
const PAGE_ITEMS: { id: PageId; label: string }[] = [
  { id: "activity-calendar", label: "Monitor risorse" },
  { id: "group-analysis", label: "Monitor gruppi" },
  { id: "job-progress", label: "Avanzamento commesse" },
];

function HubApp() {
  const [page, setPage] = useState<PageId>("activity-calendar");
  const tasks: Task[] = [];

  return (
    <>
      <nav className="activity-hub-nav" aria-label="Pagine principali">
        {PAGE_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={page === item.id ? "active" : ""}
            aria-current={page === item.id ? "page" : undefined}
            onClick={() => setPage(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      {page === "activity-calendar" ? (
        <ActivityCalendarPage />
      ) : page === "group-analysis" ? (
        <GroupAnalysisPage />
      ) : (
        <JobProgressPage
          tasks={tasks}
          onSwitchPage={() => setPage("activity-calendar")}
        />
      )}
    </>
  );
}



type GateState = "loading" | "signed-out" | "checking" | "ready" | "denied";

export default function App() {
  const [gate, setGate] = useState<GateState>("loading");
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!supabase) { setGate("denied"); setError("Configurazione autenticazione mancante."); return; }
    let alive = true;
    const verify = async (session: any) => {
      if (!session?.user) { if (alive) setGate("signed-out"); return; }
      if (alive) setGate("checking");
      const { data, error: accessError } = await supabase.from("activityhub_access").select("user_id").eq("user_id", session.user.id).maybeSingle();
      if (!alive) return;
      if (accessError || !data) {
        await supabase.auth.signOut();
        setGate("denied");
        setError(accessError ? "Non riesco a verificare l’abilitazione dell’account." : "Account non ancora abilitato. Contatta l’amministratore del sito.");
        return;
      }
      setError("");
      setGate("ready");
    };
    supabase.auth.getSession().then(({ data }) => verify(data.session));
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => { window.setTimeout(() => { void verify(session); }, 0); });
    return () => { alive = false; listener.subscription.unsubscribe(); };
  }, []);

  const signIn = async (event: FormEvent) => {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true); setError("");
    const { error: signInError } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    if (signInError) { setError("Email o password non validi."); setGate("signed-out"); }
    setBusy(false);
  };

  if (gate === "ready") return <><div className="auth-topbar"><span>Accesso effettuato</span><button className="auth-logout" onClick={() => void supabase?.auth.signOut()}>Esci</button></div><HubApp /></>;
  if (gate === "loading" || gate === "checking") return <div className="auth-screen"><div className="auth-card"><div className="auth-brand">Activity Hub</div><p>Verifica accesso…</p></div></div>;
  return <div className="auth-screen"><form className="auth-card" onSubmit={signIn}><div className="auth-brand">Serenissima Informatica</div><h1>Accedi ad Activity Hub</h1><p>Inserisci le credenziali personali abilitate dall’amministratore.</p>{error && <div className="auth-message" role="alert">{error}</div>}<div className="auth-field"><label htmlFor="activityhub-email">Email aziendale</label><input id="activityhub-email" type="email" autoComplete="username" required value={email} onChange={e=>setEmail(e.target.value)} /></div><div className="auth-field"><label htmlFor="activityhub-password">Password</label><input id="activityhub-password" type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)} /></div><button className="auth-submit" disabled={busy}>{busy ? "Accesso…" : "Accedi"}</button></form></div>;
}
