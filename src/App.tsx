import { useEffect, useRef, useState } from "react";
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

function HubApp({ scope }: { scope: AccessScope }) {
  const [page, setPage] = useState<PageId>("activity-calendar");
  const tasks: Task[] = [];
  const visiblePages = scope === "DEV"
    ? PAGE_ITEMS.filter((item) => item.id === "activity-calendar" || item.id === "group-analysis")
    : PAGE_ITEMS;

  return (
    <>
      <nav className="activity-hub-nav" aria-label="Pagine principali">
        {visiblePages.map((item) => (
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
        <ActivityCalendarPage lockedGroup={scope === "DEV" ? "DEV" : undefined} />
      ) : page === "group-analysis" ? (
        <GroupAnalysisPage lockedGroup={scope === "DEV" ? "DEV" : undefined} />
      ) : scope === "all" ? (
        <JobProgressPage
          tasks={tasks}
          onSwitchPage={() => setPage("activity-calendar")}
        />
      ) : null}
    </>
  );
}

type GateState = "loading" | "signed-out" | "checking" | "set-password" | "ready" | "denied";
type AccessScope = "all" | "DEV";

function isPasswordSetupLink() {
  const hash = new URLSearchParams(window.location.hash.slice(1));
  const type = hash.get("type");
  return new URLSearchParams(window.location.search).get("mode") === "set-password"
    || type === "invite"
    || type === "recovery";
}

function clearAuthLinkParameters() {
  window.history.replaceState({}, document.title, window.location.pathname);
}

export default function App() {
  const initialPasswordFlow = isPasswordSetupLink();
  const [gate, setGate] = useState<GateState>("loading");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const passwordFlowRef = useRef(initialPasswordFlow);
  const [busy, setBusy] = useState(false);
  const [accessScope, setAccessScope] = useState<AccessScope>("all");

  const markPasswordFlow = (active: boolean) => {
    passwordFlowRef.current = active;
  };

  useEffect(() => {
    if (!supabase) {
      setGate("denied");
      setError("Configurazione autenticazione mancante.");
      return;
    }

    let alive = true;
    const verify = async (session: any, forcePasswordSetup = false) => {
      if (!session?.user) {
        if (alive) {
          setAccessScope("all");
          if (forcePasswordSetup) {
            markPasswordFlow(false);
            clearAuthLinkParameters();
            setError("Il link non è valido o è scaduto. Richiedi un nuovo link di invito o recupero password.");
          }
          setGate("signed-out");
        }
        return;
      }

      if (forcePasswordSetup || passwordFlowRef.current) {
        if (alive) setGate("set-password");
        return;
      }

      if (alive) setGate("checking");
      const { data, error: accessError } = await supabase
        .from("activityhub_access")
        .select("user_id,access_scope")
        .eq("user_id", session.user.id)
        .maybeSingle();

      if (!alive) return;
      if (accessError || !data) {
        await supabase.auth.signOut();
        setAccessScope("all");
        setGate("denied");
        setError(accessError
          ? "Non riesco a verificare l’abilitazione dell’account."
          : "Account non ancora abilitato. Contatta l’amministratore del sito.");
        return;
      }

      const scope = data.access_scope === "DEV" ? "DEV" : "all";
      setAccessScope(scope);
      setError("");
      setGate("ready");
    };

    const initialFlow = initialPasswordFlow;
    supabase.auth.getSession().then(({ data }) => {
      void verify(data.session, initialFlow);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((event, session) => {
      const forcePasswordSetup = event === "PASSWORD_RECOVERY" || isPasswordSetupLink();
      if (forcePasswordSetup) markPasswordFlow(true);
      window.setTimeout(() => {
        void verify(session, forcePasswordSetup);
      }, 0);
    });

    return () => {
      alive = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  const signIn = async (event: FormEvent) => {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setError("");
    setNotice("");
    const { error: signInError } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });
    if (signInError) {
      setError("Email o password non validi.");
      setGate("signed-out");
    }
    setBusy(false);
  };

  const requestPasswordLink = async () => {
    if (!supabase) return;
    if (!email.trim()) {
      setError("Inserisci prima la tua email aziendale.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    const redirectTo = `${window.location.origin}${window.location.pathname}?mode=set-password`;
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo });
    if (resetError) {
      setError("Non riesco a inviare il link. Riprova o contatta l’amministratore.");
    } else {
      setNotice("Se l’account esiste, riceverai un’email con il link per impostare una nuova password.");
    }
    setBusy(false);
  };

  const savePassword = async (event: FormEvent) => {
    event.preventDefault();
    if (!supabase) return;
    if (password.length < 8) {
      setError("La password deve contenere almeno 8 caratteri.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Le due password non coincidono.");
      return;
    }

    setBusy(true);
    setError("");
    const { error: updateError } = await supabase.auth.updateUser({ password });
    if (updateError) {
      setError("Non riesco a impostare la password. Il link potrebbe essere scaduto: richiedine uno nuovo.");
      setBusy(false);
      return;
    }

    setNotice("Password impostata. Ora puoi accedere con email e password, anche da una finestra in incognito.");
    setPassword("");
    setConfirmPassword("");
    clearAuthLinkParameters();
    await supabase.auth.signOut();
    markPasswordFlow(false);
    setGate("signed-out");
    setBusy(false);
  };

  if (gate === "ready") {
    return <><div className="auth-topbar"><span>Accesso effettuato</span><button className="auth-logout" onClick={() => void supabase?.auth.signOut()}>Esci</button></div><HubApp scope={accessScope} /></>;
  }

  if (gate === "loading" || gate === "checking") {
    return <div className="auth-screen"><div className="auth-card"><div className="auth-brand">Activity Hub</div><p>Verifica accesso…</p></div></div>;
  }

  if (gate === "set-password") {
    return (
      <div className="auth-screen">
        <form className="auth-card" onSubmit={savePassword}>
          <div className="auth-brand">Serenissima Informatica</div>
          <h1>Imposta la password</h1>
          <p>Scegli una password personale. Dopo potrai accedere con la tua email anche da un altro browser o in incognito.</p>
          {error && <div className="auth-message" role="alert">{error}</div>}
          <div className="auth-field">
            <label htmlFor="activityhub-new-password">Nuova password</label>
            <input id="activityhub-new-password" type="password" autoComplete="new-password" minLength={8} required value={password} onChange={e => setPassword(e.target.value)} />
          </div>
          <div className="auth-field">
            <label htmlFor="activityhub-confirm-password">Conferma password</label>
            <input id="activityhub-confirm-password" type="password" autoComplete="new-password" minLength={8} required value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} />
          </div>
          <button className="auth-submit" disabled={busy}>{busy ? "Salvataggio…" : "Salva password"}</button>
        </form>
      </div>
    );
  }

  return (
    <div className="auth-screen">
      <form className="auth-card" onSubmit={signIn}>
        <div className="auth-brand">Serenissima Informatica</div>
        <h1>Accedi ad Activity Hub</h1>
        <p>Inserisci le credenziali personali abilitate dall’amministratore.</p>
        {error && <div className="auth-message" role="alert">{error}</div>}
        {notice && <div className="auth-notice" role="status">{notice}</div>}
        <div className="auth-field">
          <label htmlFor="activityhub-email">Email aziendale</label>
          <input id="activityhub-email" type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} />
        </div>
        <div className="auth-field">
          <label htmlFor="activityhub-password">Password</label>
          <input id="activityhub-password" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} />
        </div>
        <button className="auth-submit" disabled={busy}>{busy ? "Accesso…" : "Accedi"}</button>
        <button className="auth-link" type="button" disabled={busy} onClick={() => void requestPasswordLink()}>
          Password dimenticata o da impostare?
        </button>
      </form>
    </div>
  );
}
