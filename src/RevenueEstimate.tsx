import { useMemo } from "react";
import { TEAM_MEMBERS, type TeamGroup } from "./teamMembers";
import "./RevenueEstimate.css";

type Row = Record<string, unknown>;
type RevenueLine = {
  customer: string;
  code: string;
  job: string;
  activity: string;
  logged: number;
  confirmed: number;
  billable: number;
  unitPrice: number;
  revenue: number;
  match: string;
  source: string;
  kind: string;
  toBill: boolean | null;
  state: string;
  crmActivityId: string;
  forecast: boolean;
  category: string;
};

function norm(value: unknown) {
  return String(value ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "");
}
function number(value: unknown) {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  const parsed = Number(String(value ?? "").trim().replace(",", ".").replace(/[^\d.-]/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}
function hours(value: unknown) {
  const raw = String(value ?? "").trim();
  const duration = raw.match(/^(\d+):([0-5]\d)(?::([0-5]\d))?$/);
  return duration ? Number(duration[1]) + Number(duration[2]) / 60 + Number(duration[3] || 0) / 3600 : number(value);
}
const fmt = (value: number) => value.toLocaleString("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
const eur = (value: number) => value.toLocaleString("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 2 });
const CANCELED_STATES = new Set(["cancellata", "canceled", "cancelled", "annullata"]);
function isCanceledRow(row: Row) {
  return CANCELED_STATES.has(norm(row["Stato Attivita"]));
}

export default function RevenueEstimate({ records, revenueRecords = [], person, group, groupMembers, monthPrefix, todayKey }: {
  records: Row[];
  revenueRecords?: Row[];
  person: string;
  group?: TeamGroup;
  groupMembers?: string[];
  monthPrefix: string;
  todayKey: string;
}) {
  const inferredGroup = (Object.entries(TEAM_MEMBERS).find(([, members]) =>
    members.some((member) => norm(member) === norm(person))
  )?.[0] || "BI") as TeamGroup;
  const resolvedGroup = group && TEAM_MEMBERS[group] ? group : inferredGroup;
  const resolvedGroupMembers = Array.isArray(groupMembers) && groupMembers.length > 0
    ? groupMembers
    : TEAM_MEMBERS[resolvedGroup];
  // Recupera la tariffa NAV dal dettaglio economico anche quando il riepilogo
  // giornaliero non ha ereditato il prezzo dalla riga CRM/NAV.
  const pricesByJobKey = new Map<string, Set<number>>();
  const pricesByJob = new Map<string, Set<number>>();
  revenueRecords.forEach((row) => {
    const price = number(row["Prezzo unitario NAV"]);
    if (price <= 0) return;
    const job = norm(row["Codice commessa"]);
    const exactKey = [job, norm(row["Codice task"]), norm(row["Numero riga commessa"])].join("|");
    if (job) {
      if (!pricesByJob.has(job)) pricesByJob.set(job, new Set());
      pricesByJob.get(job)!.add(price);
    }
    if (job && exactKey !== "||") {
      if (!pricesByJobKey.has(exactKey)) pricesByJobKey.set(exactKey, new Set());
      pricesByJobKey.get(exactKey)!.add(price);
    }
  });
  const confirmedNavPrice = (row: Row) => {
    const ownPrice = Math.max(number(row["Prezzo unitario NAV"]), 0);
    if (ownPrice > 0) return ownPrice;
    const job = norm(row["Codice commessa"]);
    const exactKey = [job, norm(row["Codice task"]), norm(row["Numero riga commessa"])].join("|");
    const exactPrices = pricesByJobKey.get(exactKey);
    if (exactPrices?.size === 1) return [...exactPrices][0];
    const jobPrices = pricesByJob.get(job);
    return jobPrices?.size === 1 ? [...jobPrices][0] : 0;
  };
  // L'effettivo usa il riepilogo giornaliero: ore confermate ZDT × tariffa NAV.
  // Il dettaglio CRM resta la fonte delle attività pianificate future.
  const confirmedActuals = records.flatMap((row) => {
    const day = String(row.Data ?? "").slice(0, 10);
    const confirmed = Math.max(hours(row["Ore Confermate"]), 0);
    const billableConfirmed = Math.max(hours(row["Ore valorizzate confermate"] ?? row["Ore Confermate"]), 0);
    const price = confirmedNavPrice(row);
    if (!day || day > todayKey || confirmed <= 0 || isCanceledRow(row)) return [];
    const revenue = number(row["Stima fatturato confermato"]) || billableConfirmed * price;
    return [{
      ...row,
      "Ore Loggate": confirmed,
      "Prezzo unitario NAV": price,
      "Ore valorizzate": billableConfirmed,
      "Ore valorizzate confermate": billableConfirmed,
      "Categoria valorizzazione": "Effettivo",
      "Stima fatturato": revenue,
      "Stima fatturato confermato": revenue,
      "Fonte ore stima": "Quota confermata · Enable Invoice o ZDT × tariffa NAV",
      "Esito valorizzazione": price > 0 ? "Valorizzata" : String(row["Esito valorizzazione"] ?? "Tariffa NAV non disponibile"),
      "ToBill CRM": null
    }];
  });
  // Il previsto segue le ore presenti nel calendario ZDT; CRM serve solo
  // a recuperare la tariffa NAV quando il riepilogo giornaliero non la include.
  const plannedZdtRecords = records.flatMap((row) => {
    const day = String(row.Data ?? "").slice(0, 10);
    const plannedHours = Math.max(hours(row["Ore valorizzate"] ?? row["Ore Loggate"] ?? row.Ore), 0);
    const price = confirmedNavPrice(row);
    if (!day || day <= todayKey || plannedHours <= 0 || isCanceledRow(row)) return [];
    const revenue = plannedHours * price;
    return [{
      ...row,
      "Prezzo unitario NAV": price,
      "Ore valorizzate": plannedHours,
      "Ore valorizzate confermate": 0,
      "Categoria valorizzazione": "Pianificato",
      "Stima fatturato": revenue,
      "Stima fatturato confermato": 0,
      "Fonte ore stima": "Pianificate · Enable Invoice o ZDT × tariffa NAV",
      "Esito valorizzazione": price > 0 ? "Valorizzata" : String(row["Esito valorizzazione"] ?? "Tariffa NAV non disponibile"),
      "ToBill CRM": null
    }];
  });
  const unconfirmedZdtRecords = records.flatMap((row) => {
    const day = String(row.Data ?? "").slice(0, 10);
    const unconfirmedLogged = Math.max(hours(row["Ore Non Confermate"]), 0);
    const price = confirmedNavPrice(row);
    const billableUnconfirmed = Math.max(hours(row["Ore valorizzate da confermare"] ?? unconfirmedLogged), 0);
    if (!day || day > todayKey || unconfirmedLogged <= 0 || billableUnconfirmed <= 0 || isCanceledRow(row)) return [];
    const revenue = number(row["Stima fatturato da confermare"]) || billableUnconfirmed * price;
    return [{
      ...row,
      "Ore Loggate": unconfirmedLogged,
      "Ore Confermate": 0,
      "Prezzo unitario NAV": price,
      "Ore valorizzate": billableUnconfirmed,
      "Ore valorizzate confermate": 0,
      "Categoria valorizzazione": "Da confermare",
      "Stima fatturato": revenue,
      "Stima fatturato confermato": 0,
      "Fonte ore stima": "Non confermate · Enable Invoice o ZDT × tariffa NAV",
      "Esito valorizzazione": price > 0 ? "Valorizzata" : String(row["Esito valorizzazione"] ?? "Tariffa NAV non disponibile"),
      "ToBill CRM": null
    }];
  });
  const financialRecords = [...confirmedActuals, ...unconfirmedZdtRecords, ...plannedZdtRecords];
  const lines = useMemo(() => {
    const grouped = new Map<string, RevenueLine>();
    financialRecords.forEach((row) => {
      if (norm(row.Componente) !== norm(person)) return;
      const day = String(row.Data ?? "").slice(0, 10);
      if (!day.startsWith(monthPrefix) || isCanceledRow(row)) return;
      const code = String(row["Codice commessa"] ?? "").trim();
      const job = String(row["Nome commessa"] ?? "").trim();
      const activity = String(row["Dettaglio attività"] ?? "").trim();
      const customer = String(row.Cliente ?? "").trim() || "Cliente non disponibile";
      const match = String(row["Esito valorizzazione"] ?? "Dati di valorizzazione non disponibili");
      const source = String(row["Fonte ore stima"] ?? "—");
      const kind = String(row["Tipo attività"] ?? "").toUpperCase();
      const rawToBill = row["ToBill CRM"];
      const toBill = typeof rawToBill === "boolean" ? rawToBill : rawToBill == null || rawToBill === "" ? null : ["true", "1", "si", "yes", "y"].includes(norm(rawToBill));
      const state = String(row["Stato Attivita"] ?? "").trim();
      const crmActivityId = String(row["CRM Activity ID"] ?? "").trim();
      const logged = hours(row["Ore Loggate"] ?? row.Ore);
      const category = String(row["Categoria valorizzazione"] ?? "Effettivo");
      const forecast = category !== "Effettivo";
      const key = [customer, code, job, activity, match, source, String(toBill), state, crmActivityId, category].join("|");
      const current = grouped.get(key) || {
        customer, code, job, activity, logged: 0, confirmed: 0, billable: 0,
        unitPrice: number(row["Prezzo unitario NAV"]),
        revenue: 0, match, source, kind, toBill, state, crmActivityId, forecast, category
      };
      current.logged += logged;
      current.confirmed += hours(row["Ore Confermate"]);
      current.billable += hours(row["Ore valorizzate"]);
      current.revenue += number(row["Stima fatturato"]);
      grouped.set(key, current);
    });
    return [...grouped.values()].sort((a, b) => b.revenue - a.revenue || a.customer.localeCompare(b.customer, "it"));
  }, [financialRecords, person, monthPrefix, todayKey]);

  const economicTotals = useMemo(() => {
    const year = monthPrefix.slice(0, 4);
    const members = new Set(resolvedGroupMembers.map(norm));
    const empty = () => ({ effective: 0, planned: 0 });
    const personYear = empty();
    const groupMonth = empty();
    const groupYear = empty();
    financialRecords.forEach((row) => {
      const day = String(row.Data ?? "").slice(0, 10);
      if (!day || day.slice(0, 4) !== year) return;
      const isPerson = norm(row.Componente) === norm(person);
      const isGroup = members.has(norm(row.Componente));
      if (!isPerson && !isGroup) return;

      const billableHours = hours(row["Ore valorizzate"]);
      const price = number(row["Prezzo unitario NAV"]);
      const revenue = number(row["Stima fatturato"]) || billableHours * price;
      if (isCanceledRow(row)) return;
      const bucket = row["Categoria valorizzazione"] !== "Effettivo"
        ? { effective: 0, planned: revenue }
        : { effective: revenue, planned: 0 };
      const add = (target: typeof personYear) => {
        target.effective += bucket.effective;
        target.planned += bucket.planned;
      };
      if (isPerson) add(personYear);
      if (isGroup) {
        add(groupYear);
        if (day.startsWith(monthPrefix)) add(groupMonth);
      }
    });
    return { year, personYear, groupMonth, groupYear };
  }, [financialRecords, person, resolvedGroup, resolvedGroupMembers, monthPrefix, todayKey]);

  const actualLines = lines.filter((line) => !line.forecast);
  const totals = lines.reduce((sum, line) => ({
    logged: sum.logged + line.logged,
    billable: sum.billable + (line.forecast ? 0 : line.billable),
    revenue: sum.revenue + (line.forecast ? 0 : line.revenue)
  }), { logged: 0, billable: 0, revenue: 0 });
  const unresolved = lines.filter((line) => line.match !== "Valorizzata");
  const clients = useMemo(() => {
    const values = new Map<string, { revenue: number; logged: number; lines: number }>();
    actualLines.filter((line) => line.match === "Valorizzata" && line.kind !== "COIG").forEach((line) => {
      const current = values.get(line.customer) || { revenue: 0, logged: 0, lines: 0 };
      current.revenue += line.revenue;
      current.logged += line.logged;
      current.lines++;
      values.set(line.customer, current);
    });
    return [...values.entries()].map(([name, value]) => ({ name, ...value })).sort((a, b) => b.revenue - a.revenue);
  }, [actualLines]);
  const maxClientRevenue = clients[0]?.revenue || 0;
  const plannedClients = useMemo(() => {
    const values = new Map<string, { hours: number; revenue: number; lines: number }>();
    financialRecords.forEach((row) => {
      if (norm(row.Componente) !== norm(person)) return;
      const day = String(row.Data ?? "").slice(0, 10);
      if (!day.startsWith(monthPrefix) || row["Categoria valorizzazione"] === "Effettivo" || isCanceledRow(row)) return;
      const billableHours = Math.max(hours(row["Ore valorizzate"]), 0);
      if (billableHours <= 0) return;
      const customer = String(row.Cliente ?? "").trim() || "Cliente non disponibile";
      const revenue = Math.max(number(row["Stima fatturato"]) || billableHours * number(row["Prezzo unitario NAV"]), 0);
      const current = values.get(customer) || { hours: 0, revenue: 0, lines: 0 };
      current.hours += billableHours;
      current.revenue += revenue;
      current.lines += 1;
      values.set(customer, current);
    });
    return [...values.entries()]
      .map(([name, value]) => ({ name, ...value }))
      .sort((a, b) => b.revenue - a.revenue || b.hours - a.hours || a.name.localeCompare(b.name, "it"));
  }, [financialRecords, person, monthPrefix, todayKey]);
  const maxPlannedRevenue = plannedClients[0]?.revenue || 0;
  const plannedRevenue = plannedClients.reduce((sum, client) => sum + client.revenue, 0);
  const valuedCount = lines.filter((line) => line.match === "Valorizzata").length;

  return (
    <section className="revenue-panel" aria-label="Stima del fatturato">
      <header className="revenue-header">
        <div><p className="revenue-eyebrow">CRM · NAV</p><h2>Stima del fatturato</h2><p>{person} · {monthPrefix} · attività registrate fino a oggi</p></div>
        <span>{valuedCount} voci valorizzate{unresolved.length ? ` · ${unresolved.length} da verificare` : ""}</span>
      </header>
      <div className="revenue-kpis">
        <article><span>Fatturato effettivo</span><strong>{eur(totals.revenue)}</strong><small>Ore fatturabili delle attività fino a oggi</small></article>
        <article><span>Fatturato previsto</span><strong>{eur(plannedRevenue)}</strong><small>Ore non confermate fino a oggi e pianificate da domani</small></article>
        <article><span>Ore valorizzate</span><strong>{fmt(totals.billable)} h</strong><small>Ore fatturabili per singola attività CRM</small></article>
        <article><span>Ore loggate collegate</span><strong>{fmt(totals.logged)} h</strong><small>{lines.length} voci attività nel mese</small></article>
        <article><span>Da verificare</span><strong className={unresolved.length ? "revenue-warning" : ""}>{unresolved.length}</strong><small>Commesse senza abbinamento o prezzo univoco</small></article>
      </div>
      <section className="revenue-totalizers" aria-label="Totalizzatori economici">
        <div className="revenue-totalizers-title"><h3>Totalizzatori economici</h3><span>Fatturabile effettivo fino a oggi e pianificato da domani · {economicTotals.year}</span></div>
        <div className="revenue-totalizers-grid">
          {([
            ["Persona · anno", economicTotals.personYear, `${person} · ${economicTotals.year}`],
            [`Gruppo ${resolvedGroup} · mese`, economicTotals.groupMonth, monthPrefix],
            [`Gruppo ${resolvedGroup} · anno`, economicTotals.groupYear, economicTotals.year],
          ] as const).map(([label, value, period]) => (
            <article key={label}>
              <span>{label}</span><strong>{eur(value.effective + value.planned)}</strong><small>{period}</small>
              <div className="revenue-totalizer-breakdown">
                <span>Effettivo fino a oggi <b>{eur(value.effective)}</b></span>
                <span>Pianificato da domani <b>{eur(value.planned)}</b></span>
              </div>
            </article>
          ))}
        </div>
      </section>
      <div className="revenue-body">
        <section className="revenue-clients">
          <div className="revenue-section-heading"><div><h3>Effettivo per cliente</h3><p>Importo maturato con attività fino a oggi</p></div><span>{clients.length} clienti</span></div>
          {clients.length === 0 ? <p className="revenue-empty">Nessun importo stimato per il periodo.</p> :
            <ol>{clients.slice(0, 8).map((client) => <li key={client.name}>
              <div><span title={client.name}>{client.name}</span><strong>{eur(client.revenue)} <small>{totals.revenue ? (client.revenue / totals.revenue * 100).toLocaleString("it-IT", { maximumFractionDigits: 0 }) : 0}%</small></strong></div>
              <i><b style={{ width: `${maxClientRevenue ? client.revenue / maxClientRevenue * 100 : 0}%` }} /></i>
            </li>)}</ol>}
          <div className="revenue-planned-clients">
            <div className="revenue-section-heading"><div><h3>Pianificato per cliente</h3><p>Ore ZDT non confermate e pianificate, valorizzate con tariffa NAV · {monthPrefix}</p></div><span>{plannedClients.length} clienti</span></div>
            {plannedClients.length === 0 ? <p className="revenue-empty">Nessuna attività pianificata fatturabile nel periodo.</p> :
              <ol>{plannedClients.slice(0, 8).map((client) => <li key={client.name}>
                <div><span title={client.name}>{client.name}</span><strong>{eur(client.revenue)}</strong></div>
                <small>{fmt(client.hours)} h fatturabili · {client.lines} voci</small>
                <i><b style={{ width: `${maxPlannedRevenue ? client.revenue / maxPlannedRevenue * 100 : 0}%` }} /></i>
              </li>)}</ol>}
          </div>
        </section>
        <section className="revenue-detail">
          <div className="revenue-section-heading"><div><h3>Dettaglio commesse</h3><p>Valorizzazione delle ore per commessa e attività</p></div><span>{lines.length} voci</span></div>
          {lines.length === 0 ? <p className="revenue-empty">Non risultano attività registrate nel periodo selezionato.</p> :
            <div className="revenue-table-wrap"><table>
              <thead><tr><th>Esito</th><th>Cliente</th><th>Commessa / attività</th><th>Tipo</th><th>Stato ZDT</th><th>ID CRM</th><th>Ore loggate</th><th>Ore confermate</th><th>ToBill CRM</th><th>Ore valorizzate</th><th>Tariffa NAV</th><th>Stima</th></tr></thead>
              <tbody>{lines.map((line, index) => <tr key={`${line.customer}|${line.code}|${line.activity}|${index}`} className={line.match === "Valorizzata" ? "" : "revenue-unresolved"}>
                <td><span className={line.match === "Valorizzata" ? "revenue-badge" : "revenue-badge unresolved"}>{line.match}</span>{line.source !== "—" && <small className="revenue-source">{line.source}</small>}</td>
                <td>{line.customer}</td><td><strong>{line.code || "—"}</strong><small>{[line.job, line.activity].filter(Boolean).join(" · ")}</small></td>
                <td><span className={line.forecast ? "revenue-badge forecast" : "revenue-badge"}>{line.category}</span></td><td>{line.state || "—"}</td><td>{line.crmActivityId || "—"}</td><td>{fmt(line.logged)} h</td><td>{fmt(line.confirmed)} h</td><td>{line.toBill === null ? "—" : line.toBill ? "Sì" : "No"}</td><td>{fmt(line.billable)} h</td><td>{line.match === "Valorizzata" ? eur(line.unitPrice) : "—"}</td><td><strong>{line.match === "Valorizzata" ? eur(line.revenue) : "—"}</strong></td>
              </tr>)}</tbody>
            </table></div>}
        </section>
      </div>
      <footer className="revenue-footnote">Le attività e le ore seguono il calendario ZDT. Le ore confermate sono effettive; le ore loggate ma non confermate e le ore pianificate sono previste. Il valore usa le ore Enable Invoice quando disponibili, altrimenti tutte le ore ZDT, moltiplicate per la tariffa NAV. La stima non è un importo fatturato.</footer>
    </section>
  );
}
