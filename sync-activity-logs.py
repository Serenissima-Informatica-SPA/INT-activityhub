#!/usr/bin/env python3
"""Download daily activity Parquet and prepare the static Pages data file."""
import json
import os
import unicodedata
from io import BytesIO
from pathlib import Path
from time import sleep

import pandas as pd
from azure.core.exceptions import ResourceModifiedError
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

# Keep this normalization-aware whitelist aligned with src/teamMembers.ts.
TEAM_MEMBERS = {
    "lotta giorgia", "favero matteo", "stocco alberto", "vita anna",
    "mason mauro", "padovan matteo", "micheletto nicola",
    "albanese lorenzo", "brigo matteo", "brotto fabio", "cecchin chiara",
    "cestaro luca", "dian enrico", "luise alessandro", "marino daniele",
    "verzotto maria", "rampazzo lisa", "sarto michele", "omodei cesare",
    "agostini nicolo", "corato cinzia", "lovo ilaria", "messina angela",
    "modolo meri", "toncelli michele", "villani riccardo", "vivoda fabio",
    "aquilino graziano", "maso giuliano", "pandolfo piero", "prando gloria",
    "rossi michela", "stramazzo andrea", "turcato luca", "zanetti paolo",
    "coletta alberto", "martignago vanni", "nardo fabio", "rosina federico",
    "russo michelangelo", "salerno silvio", "vecchio fabrizio salvatore",
    "remonato enrico",
}

FIELD_CANDIDATES = {
    "date": ["data", "giorno", "postingdate", "workdate", "activitydate", "date"],
    "person": ["persona", "risorsa", "nome", "nominativo", "dipendente", "utente", "resource", "resourcename", "employeename", "person", "member", "componente"],
    "hours": ["oreloggate", "ore", "durata", "oreconsuntivate", "hours", "loggedhours", "quantity", "workinghours", "time"],
    "confirmed_hours": ["oreconfermate", "confirmedhours"],
    "unconfirmed_hours": ["orenonconfermate", "unconfirmedhours"],
    "registrations": ["numeroregistrazioni", "registrations", "registrationcount"],
    "confirmed_registrations": ["registrazioniconfermate", "confirmedregistrations"],
    "logged_minutes": ["minutiloggati", "loggedminutes"],
    "confirmed_minutes": ["minuticonfermati", "confirmedminutes"],
    "unconfirmed_minutes": ["minutinonconfermati", "unconfirmedminutes"],
    "job_code": ["commessa", "codicecommessa", "commessacodice", "numerocommessa", "jobno", "jobnumber", "jobcode", "job"],
    "task_code": ["jobtaskno", "codicetask", "task"],
    "plan_code": ["rigacommessa", "jobplanno", "numerorigacommessa"],
    "job_name": ["descrizionecommessa", "nomecommessa", "commessadescrizione", "descrizioneriga", "jobname", "jobdescription", "description"],
    "activity_name": ["descrizionetask", "descrizioneattivita", "nomeattivita", "activitydescription", "activityname", "taskdescription", "task"],
}


def normalize(value):
    decomposed = unicodedata.normalize("NFD", str(value).casefold())
    return "".join(char for char in decomposed if char.isalnum() and not unicodedata.combining(char))


def text_value(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


# Alias di anagrafica: le righe ZDT possono invertire nome/cognome o omettere il secondo nome.
PERSON_ALIASES = {
    "federicorosina": "Rosina Federico",
    "rosinafederico": "Rosina Federico",
    "vecchiofabrizio": "Vecchio Fabrizio Salvatore",
    "vecchiofabriziosalvatore": "Vecchio Fabrizio Salvatore",
}


def canonical_person(value):
    raw = str(value or "").strip()
    return PERSON_ALIASES.get(normalize(raw), raw)


def normalize_person(value):
    return normalize(canonical_person(value))


def normalize_code(value):
    text = text_value(value)
    if not text:
        return ""
    try:
        numeric_value = float(text.replace(",", "."))
        if numeric_value.is_integer():
            text = str(int(numeric_value))
    except (TypeError, ValueError):
        pass
    return normalize(text)


def find_zdt_field(columns, kind):
    """Prefer ZDT task/plan identifiers over similarly named CRM fields."""
    aliases = {
        "task_code": ("task", "codicetask", "jobtaskno", "taskno", "tasknumber", "zdttask", "taskzdt"),
        "plan_code": ("rigacommessa", "numerorigacommessa", "jobplanno", "planno", "zdtrigacommessa", "rigacommessazdt", "planline"),
    }[kind]
    non_crm = [(column, normalize(column)) for column in columns if "crm" not in normalize(column)]
    for alias in aliases:
        exact = [column for column, normalized in non_crm if normalized == alias]
        if exact:
            return exact[0]
    for alias in aliases:
        match = next((column for column, normalized in non_crm if alias in normalized), None)
        if match:
            return match
    return find_field(columns, kind)


def numeric(value):
    try:
        parsed = pd.to_numeric(value, errors="coerce")
        return None if pd.isna(parsed) else float(parsed)
    except (TypeError, ValueError):
        return None


def as_bool(value):
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    return normalize(value) in {"1", "true", "si", "yes", "y"}


def find_field(columns, kind):
    candidates = FIELD_CANDIDATES[kind]
    for candidate in candidates:
        for column in columns:
            if normalize(column) == candidate:
                return column
    for column in columns:
        if any(candidate in normalize(column) for candidate in candidates):
            return column
    return None


def download_blob_with_retry(blob_client, label, attempts=4):
    """Retry a download if Azure replaces a blob while its chunks are being read."""
    for attempt in range(1, attempts + 1):
        content = BytesIO()
        try:
            blob_client.download_blob().readinto(content)
            content.seek(0)
            return content
        except ResourceModifiedError:
            if attempt == attempts:
                raise
            delay = attempt * 2
            print(f"Blob aggiornato durante il download di {label}; nuovo tentativo tra {delay}s ({attempt + 1}/{attempts})")
            sleep(delay)


def main():
    load_dotenv()
    account = os.getenv("AZURE_ACTIVITY_STORAGE_ACCOUNT") or os.getenv("AZURE_STORAGE_ACCOUNT")
    key = os.getenv("AZURE_ACTIVITY_STORAGE_KEY") or os.getenv("AZURE_STORAGE_KEY")
    container = os.getenv("AZURE_ACTIVITY_STORAGE_CONTAINER", "parquet-files")
    blob = os.getenv("AZURE_ACTIVITY_STORAGE_BLOB", "SQLSERVER1_ZeroDownTimeDB_AttivitaGiornaliere.parquet")
    if not account or not key:
        raise ValueError("Missing AZURE_STORAGE_ACCOUNT or AZURE_STORAGE_KEY")

    connection = f"DefaultEndpointsProtocol=https;AccountName={account};AccountKey={key};EndpointSuffix=core.windows.net"
    client = BlobServiceClient.from_connection_string(connection).get_blob_client(container=container, blob=blob)
    content = download_blob_with_retry(client, f"{container}/{blob}")
    frame = pd.read_parquet(content)
    print(f"Colonne origine parquet: {', '.join(str(column) for column in frame.columns)}")

    # Il dettaglio contiene una riga per attività ZDT e le ore fatturabili già
    # calcolate dalla sorgente CRM: usarle per data/commessa evita ripartizioni
    # stimate da aggregati mensili.
    detail_blob = os.getenv(
        "AZURE_ACTIVITY_DETAIL_BLOB",
        "SQLSERVER1_ZeroDownTimeDB_ControlloLogCRM_DettaglioAttivita.parquet",
    )
    detail_container = os.getenv("AZURE_ACTIVITY_DETAIL_CONTAINER", container)
    detail_client = BlobServiceClient.from_connection_string(connection).get_blob_client(
        container=detail_container, blob=detail_blob
    )
    detail_content = download_blob_with_retry(detail_client, f"{detail_container}/{detail_blob}")
    detail_frame = pd.read_parquet(detail_content)
    print(f"Colonne dettaglio CRM: {', '.join(str(column) for column in detail_frame.columns)}")


    date_field = find_field(frame.columns, "date")
    person_field = find_field(frame.columns, "person")
    fields = {kind: find_field(frame.columns, kind) for kind in FIELD_CANDIDATES if kind not in ("date", "person")}
    # Quando i feed espongono sia chiavi CRM sia chiavi della riga ZDT,
    # non lasciare che la ricerca parziale scelga prima il campo CRM.
    fields["task_code"] = find_zdt_field(frame.columns, "task_code")
    fields["plan_code"] = find_zdt_field(frame.columns, "plan_code")
    if not date_field or not person_field or not fields["hours"] or not fields["confirmed_hours"]:
        raise ValueError(f"Colonne necessarie non individuate; campi trovati: {list(frame.columns)}")

    source_people = frame[person_field].dropna().astype(str).str.strip().unique()
    for term in ("rosin", "vecchio"):
        matches = sorted({value for value in source_people if term in normalize(value)})
        print(f"Nomi sorgente {term}: {matches}")

    daily = frame[[date_field, person_field]].copy()
    detail_fields = {
        "Codice commessa": fields.get("job_code"),
        "Codice task": fields.get("task_code"),
        "Numero riga commessa": fields.get("plan_code"),
        "Nome commessa": fields.get("job_name"),
        "Dettaglio attività": fields.get("activity_name"),
    }
    for output_name, source in detail_fields.items():
        daily[output_name] = frame[source].fillna("").astype(str).str.strip() if source else ""

    code = daily["Codice commessa"].str.upper()
    name = daily["Nome commessa"].str.upper()
    activity = daily["Dettaglio attività"].str.upper()
    daily["Tipo attività"] = "Non COIG"
    daily.loc[code.str.startswith("COIG") | name.str.startswith("COIG") | activity.str.startswith("COIG"), "Tipo attività"] = "COIG"

    customer_by_job = {}
    jobs_path = Path("public/jobs.json")
    if jobs_path.exists():
        for job in json.loads(jobs_path.read_text(encoding="utf-8")):
            job_code = normalize(job.get("JobNo", ""))
            customer = str(job.get("Customer Name") or "").strip()
            if job_code and customer:
                customer_by_job[job_code] = customer
    daily["Cliente"] = daily["Codice commessa"].map(lambda value: customer_by_job.get(normalize(value), ""))

    output_fields = {
        "hours": "Ore Loggate",
        "confirmed_hours": "Ore Confermate",
        "unconfirmed_hours": "Ore Non Confermate",
        "registrations": "Numero Registrazioni",
        "confirmed_registrations": "Registrazioni Confermate",
        "logged_minutes": "Minuti Loggati",
        "confirmed_minutes": "Minuti Confermati",
        "unconfirmed_minutes": "Minuti Non Confermati",
    }
    for kind, output_name in output_fields.items():
        source = fields.get(kind)
        daily[output_name] = pd.to_numeric(frame[source], errors="coerce").fillna(0) if source else 0

    if not fields["unconfirmed_hours"]:
        daily["Ore Non Confermate"] = (daily["Ore Loggate"] - daily["Ore Confermate"]).clip(lower=0)
    if not fields["confirmed_registrations"] and fields["registrations"]:
        daily["Registrazioni Confermate"] = 0
    if not fields["unconfirmed_minutes"] and fields["logged_minutes"] and fields["confirmed_minutes"]:
        daily["Minuti Non Confermati"] = (daily["Minuti Loggati"] - daily["Minuti Confermati"]).clip(lower=0)

    daily = daily.dropna(subset=[date_field, person_field])
    daily[person_field] = daily[person_field].map(canonical_person)
    allowed_people = {normalize(name) for name in TEAM_MEMBERS}
    daily = daily[daily[person_field].map(normalize).isin(allowed_people)]
    person_counts = daily[person_field].value_counts()
    for target in ("Rosina Federico", "Vecchio Fabrizio Salvatore"):
        print(f"Righe ZDT per {target}: {int(person_counts.get(target, 0))}")
    sum_columns = list(output_fields.values())
    detail_columns = [*detail_fields.keys(), "Cliente", "Tipo attività"]
    group_columns = [date_field, person_field, *detail_columns]
    daily = daily.groupby(group_columns, as_index=False, dropna=True)[sum_columns].sum()
    # Collega ogni riga ZDT al dettaglio CRM/NAV tramite commessa, task e riga.
    jobs_path = Path("public/jobs.json")
    jobs = json.loads(jobs_path.read_text(encoding="utf-8")) if jobs_path.exists() else []
    jobs_by_key = {}
    jobs_by_detail_id = {}
    jobs_by_job_task = {}
    jobs_by_job_plan = {}
    jobs_by_job = {}
    for job in jobs:
        job_code = normalize_code(job.get("JobNo"))
        task_code = normalize_code(job.get("JobTaskNo"))
        plan_code = normalize_code(job.get("JobPlanNo"))
        key = (job_code, task_code, plan_code)
        detail_id = normalize_code(job.get("job_jobdetailid"))
        if detail_id:
            jobs_by_detail_id.setdefault(detail_id, []).append(job)
        if job_code:
            jobs_by_job.setdefault(job_code, []).append(job)
        if job_code and task_code:
            jobs_by_job_task.setdefault((job_code, task_code), []).append(job)
        if job_code and plan_code:
            jobs_by_job_plan.setdefault((job_code, plan_code), []).append(job)
        if all(key):
            jobs_by_key.setdefault(key, []).append(job)

    def resolve_job(row):
        job_code = normalize_code(row.get("Codice commessa"))
        task_code = normalize_code(row.get("Codice task"))
        plan_code = normalize_code(row.get("Numero riga commessa"))
        key = (job_code, task_code, plan_code)
        crm_detail_id = normalize_code(row.get("CRM Job Detail ID"))
        # La chiave ZDT completa è più specifica dell'ID CRM: lo stesso ID CRM
        # può essere collegato a più righe NAV e produrre falsi casi non univoci.
        candidates = jobs_by_key.get(key, []) if all(key) else []
        match_level = "commessa + task + riga"
        if not candidates:
            candidates = jobs_by_detail_id.get(crm_detail_id, []) if crm_detail_id else []
            match_level = "CRM Job Detail ID"
        if not candidates and job_code and task_code:
            candidates = jobs_by_job_task.get((job_code, task_code), [])
            match_level = "commessa + task"
        if not candidates and job_code and plan_code:
            candidates = jobs_by_job_plan.get((job_code, plan_code), [])
            match_level = "commessa + riga"
        if not candidates and job_code:
            candidates = jobs_by_job.get(job_code, [])
            match_level = "commessa"
            zdt_descriptions = {
                normalize(text_value(row.get(field)))
                for field in ("Nome commessa", "Dettaglio attività", "Descrizione Riga", "Descrizione Task")
                if normalize(text_value(row.get(field)))
            }
            nav_description_fields = ("Plan Description", "Detail Description")
            def nav_descriptions(item):
                return {
                    normalize(text_value(item.get(field)))
                    for field in nav_description_fields
                    if normalize(text_value(item.get(field)))
                }
            exact_description_matches = [
                item for item in candidates
                if zdt_descriptions & nav_descriptions(item)
            ]
            if exact_description_matches:
                candidates = exact_description_matches
                match_level = "commessa + descrizione esatta ZDT/NAV"
            else:
                description_matches = [
                    item for item in candidates
                    if any(
                        len(zdt_desc) >= 8 and len(nav_desc) >= 8
                        and (zdt_desc in nav_desc or nav_desc in zdt_desc)
                        for zdt_desc in zdt_descriptions
                        for nav_desc in nav_descriptions(item)
                    )
                ]
                if description_matches:
                    candidates = description_matches
                    match_level = "commessa + descrizione parziale ZDT/NAV"
        if not candidates:
            return None, "Commessa/task/riga non abbinati", "Nessuna riga NAV corrispondente alle chiavi ZDT/CRM"

        def candidate_text(item):
            task = text_value(item.get("JobTaskNo")) or "—"
            plan = text_value(item.get("JobPlanNo")) or "—"
            description = text_value(item.get("Plan Description")) or text_value(item.get("Detail Description")) or "descrizione assente"
            price = numeric(item.get("Unit Price"))
            price_text = f"{price:.2f} €" if price is not None else "tariffa assente"
            return f"task {task} · riga {plan} · {description[:48]} · {price_text}/h"

        candidate_list = "; ".join(candidate_text(item) for item in candidates[:8])
        if len(candidates) > 8:
            candidate_list += f"; altre {len(candidates) - 8} righe"
        diagnostic = f"Abbinamento per {match_level}: {len(candidates)} righe candidate ({candidate_list})"
        prices = {numeric(item.get("Unit Price")) for item in candidates}
        if None in prices or len(prices) != 1:
            reasons = []
            if None in prices:
                reasons.append("almeno una riga non ha tariffa")
            if len({price for price in prices if price is not None}) > 1:
                reasons.append("le righe hanno tariffe diverse")
            reason = " e ".join(reasons) or "tariffa non determinabile"
            return None, "Tariffa NAV non univoca", f"{diagnostic}. Motivo: {reason}."
        price = next(iter(prices))
        if price is None:
            return None, "Prezzo NAV non disponibile", f"{diagnostic}. Motivo: tariffa assente."
        logged = sum(numeric(item.get("Ore Loggate")) or 0 for item in candidates)
        invoice_hours = sum(numeric(item.get("Ore Enable Invoicing")) or 0 for item in candidates)
        enabled = any(as_bool(item.get("Enable Invoicing")) for item in candidates)
        return {"price": price, "crm_logged": logged, "invoice_hours": invoice_hours, "enabled": enabled}, "Valorizzata", diagnostic

    daily["Prezzo unitario NAV"] = 0.0
    daily["Ore valorizzate"] = 0.0
    daily["Stima fatturato"] = 0.0
    daily["Fonte ore stima"] = ""
    daily["Esito valorizzazione"] = ""
    daily["Dettaglio tariffa NAV"] = ""

    detail_date = find_field(detail_frame.columns, "date")
    detail_person = find_field(detail_frame.columns, "person")
    detail_job = find_field(detail_frame.columns, "job_code")
    detail_task = find_zdt_field(detail_frame.columns, "task_code")
    detail_plan = find_zdt_field(detail_frame.columns, "plan_code")
    detail_billable = next(
        (column for column in detail_frame.columns if normalize(column) in {"orefatturabili", "billablehours"}),
        None,
    )
    detail_invoice_hours = next(
        (column for column in detail_frame.columns if normalize(column) in {"invoicequantityore", "invoicehours"}),
        None,
    )
    detail_invoice_minutes = next(
        (column for column in detail_frame.columns if normalize(column) in {"invoicequantity", "invoiceminutes"}),
        None,
    )
    detail_to_bill = next(
        (column for column in detail_frame.columns if normalize(column) in {"tobill", "enableinvoice"}),
        None,
    )
    detail_confirmed = next(
        (column for column in detail_frame.columns if normalize(column) in {"zdtconfirmed", "confirmed"}),
        None,
    )
    has_detail_confirmations = bool(
        detail_confirmed and detail_frame[detail_confirmed].map(as_bool).any()
    )

    required_detail = {
        "data": detail_date, "componente": detail_person, "commessa": detail_job,
        "task": detail_task, "riga": detail_plan,
    }
    missing_detail = [name for name, column in required_detail.items() if column is None]
    if missing_detail:
        raise ValueError(
            f"Colonne chiave mancanti nel dettaglio CRM: {missing_detail}; "
            f"colonne presenti: {list(detail_frame.columns)}"
        )
    if detail_billable is None and detail_invoice_hours is None and detail_invoice_minutes is None:
        raise ValueError("Il dettaglio CRM non contiene Ore Fatturabili né InvoiceQuantity")

    def detail_day(value):
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
        return parsed.strftime("%Y-%m-%d") if pd.notna(parsed) else ""

    # Le ore loggate arrivano dal riepilogo giornaliero, che è la fonte valida
    # per il calendario. Il dettaglio ZDT fornisce lo stato di conferma attività.
    detail_zdt_minutes = next(
        (column for column in detail_frame.columns if normalize(column) == "minutizdt"),
        None,
    )
    detail_zdt_state = next(
        (column for column in detail_frame.columns if normalize(column) == "statoattivita"),
        None,
    )
    detail_zdt_color = next(
        (column for column in detail_frame.columns if normalize(column) == "colorestatozdt"),
        None,
    )
    detail_crm_job = next((column for column in detail_frame.columns if normalize(column) == "crmcommessa"), None)
    detail_crm_task = next((column for column in detail_frame.columns if normalize(column) == "crmtask"), None)
    detail_crm_plan = next((column for column in detail_frame.columns if normalize(column) == "crmrigacommessa"), None)
    detail_crm_activity_id = next((column for column in detail_frame.columns if normalize(column) == "crmactivityid"), None)
    detail_crm_job_detail_id = next((column for column in detail_frame.columns if normalize(column) == "crmjobdetailid"), None)
    detail_nav_unit_price = next((column for column in detail_frame.columns if normalize(column) == "navunitprice"), None)
    detail_nav_match_count = next((column for column in detail_frame.columns if normalize(column) == "navmatchcount"), None)
    detail_nav_match_status = next((column for column in detail_frame.columns if normalize(column) == "navmatchstatus"), None)
    detail_nav_plan_description = next((column for column in detail_frame.columns if normalize(column) == "navplandescription"), None)
    detail_desc_task = next((column for column in detail_frame.columns if normalize(column) == "descrizionetask"), None)
    detail_desc_plan = next((column for column in detail_frame.columns if normalize(column) == "descrizioneriga"), None)
    detail_desc_job = next((column for column in detail_frame.columns if normalize(column) == "descrizionecommessa"), None)
    if not detail_zdt_state and not detail_zdt_color and not detail_confirmed:
        raise ValueError("Il dettaglio ZDT non contiene stato, colore o flag di conferma")

    def detail_is_confirmed(row):
        state = normalize(text_value(row.get(detail_zdt_state))) if detail_zdt_state else ""
        color = normalize(text_value(row.get(detail_zdt_color)).lower()) if detail_zdt_color else ""
        if state:
            return state in {"completata", "completed"}
        if color:
            return any(token in color for token in ("green", "lime", "00ff00"))
        return as_bool(row.get(detail_confirmed))

    # Allinea i due feed usando il livello comune: giorno, persona e commessa/task/riga.
    # Le descrizioni possono differire; non vanno usate come chiavi di join.
    detail_status_by_activity = {}
    for _, detail in detail_frame.iterrows():
        key = (
            detail_day(detail.get(detail_date)),
            normalize_person(detail.get(detail_person, "")),
            normalize_code(detail.get(detail_job)),
            normalize_code(detail.get(detail_task)),
            normalize_code(detail.get(detail_plan)),
        )
        if not all(key):
            continue
        minutes = max(numeric(detail.get(detail_zdt_minutes)) or 0.0, 0.0) if detail_zdt_minutes else 0.0
        is_confirmed = detail_is_confirmed(detail)
        totals = detail_status_by_activity.setdefault(key, [0.0, 0.0, 0, 0])
        totals[0] += minutes
        totals[1] += minutes if is_confirmed else 0.0
        totals[2] += 1
        totals[3] += 1 if is_confirmed else 0

    calendar_rows_by_activity = {}
    for index, row in daily.iterrows():
        key = (
            detail_day(row.get(date_field)),
            normalize_person(row.get(person_field, "")),
            normalize_code(row.get("Codice commessa")),
            normalize_code(row.get("Codice task")),
            normalize_code(row.get("Numero riga commessa")),
        )
        if all(key):
            calendar_rows_by_activity.setdefault(key, []).append(index)

    detail_matched_calendar_rows = 0
    detail_matched_activities = 0
    for key, indexes in calendar_rows_by_activity.items():
        totals = detail_status_by_activity.get(key)
        if totals is None:
            continue
        total_minutes, confirmed_minutes, total_count, confirmed_count = totals
        confirmation_share = (
            confirmed_minutes / total_minutes
            if total_minutes > 0
            else (confirmed_count / total_count if total_count else 0.0)
        )
        confirmation_share = min(max(confirmation_share, 0.0), 1.0)
        for index in indexes:
            # Preserve the daily Parquet's logged duration; only correct confirmation.
            logged = max(numeric(daily.at[index, "Ore Loggate"]) or 0.0, 0.0)
            confirmed = logged * confirmation_share
            daily.at[index, "Ore Confermate"] = confirmed
            daily.at[index, "Ore Non Confermate"] = max(logged - confirmed, 0.0)
            detail_matched_calendar_rows += 1
        detail_matched_activities += 1

    if daily.empty or detail_matched_calendar_rows == 0:
        raise ValueError("Nessuna riga del calendario abbinata allo stato del dettaglio ZDT")
    print(
        f"Conferme calendario riallineate al dettaglio ZDT: "
        f"{detail_matched_calendar_rows}/{len(daily)} righe; "
        f"attività abbinate: {detail_matched_activities}/{len(calendar_rows_by_activity)}"
    )

    def detail_hours(row):
        # ToBill è vincolante prima delle quantità CRM.
        raw_to_bill = row.get(detail_to_bill) if detail_to_bill else None
        if detail_to_bill and raw_to_bill is not None and not pd.isna(raw_to_bill) and not as_bool(raw_to_bill):
            return 0.0
        if detail_billable:
            value = numeric(row.get(detail_billable))
            if value is not None:
                return max(value, 0)
        if detail_invoice_hours:
            value = numeric(row.get(detail_invoice_hours))
            if value is not None:
                return max(value, 0)
        if detail_invoice_minutes:
            value = numeric(row.get(detail_invoice_minutes))
            if value is not None:
                return max(value / 60, 0)
        return 0.0

    def detail_has_invoice_quantity(row):
        for column in (detail_billable, detail_invoice_hours, detail_invoice_minutes):
            if column and numeric(row.get(column)) is not None:
                return True
        return False

    billable_by_activity = {}
    confirmed_billable_by_activity = {}
    revenue_groups = {}
    allowed_people = {normalize(name) for name in TEAM_MEMBERS}
    valuation_today_key = pd.Timestamp.now(tz="Europe/Rome").date().isoformat()
    for _, detail in detail_frame.iterrows():
        day = detail_day(detail.get(detail_date))
        person_raw = canonical_person(text_value(detail.get(detail_person)))
        person_key = normalize_person(person_raw)
        base_job = text_value(detail.get(detail_job))
        base_task = text_value(detail.get(detail_task))
        base_plan = text_value(detail.get(detail_plan))
        # Per la tariffa NAV usiamo come chiave primaria i codici dell'attività ZDT.
        # I riferimenti CRM sono un fallback: possono descrivere un'associazione CRM diversa
        # dalla riga di pianificazione NAV a cui l'attività ZDT è stata assegnata.
        job_code = base_job or (text_value(detail.get(detail_crm_job)) if detail_crm_job else "")
        task_code = base_task or (text_value(detail.get(detail_crm_task)) if detail_crm_task else "")
        plan_code = base_plan or (text_value(detail.get(detail_crm_plan)) if detail_crm_plan else "")
        base_key = (day, person_key, normalize_code(base_job), normalize_code(base_task), normalize_code(base_plan))
        state_label = text_value(detail.get(detail_zdt_state)) if detail_zdt_state else ""
        state_key = normalize(state_label)
        is_confirmed = detail_is_confirmed(detail)
        raw_to_bill = detail.get(detail_to_bill) if detail_to_bill else None
        to_bill_flag = as_bool(raw_to_bill) if detail_to_bill and raw_to_bill is not None and not pd.isna(raw_to_bill) else None
        logged_minutes = max(numeric(detail.get(detail_zdt_minutes)) or 0.0, 0.0) if detail_zdt_minutes else 0.0
        canceled = state_key in {"cancellata", "cancelled", "canceled", "annullata"}
        has_invoice_quantity = detail_has_invoice_quantity(detail)
        if canceled:
            billable_hours = 0.0
            billable_source = "Attività ZDT cancellata"
        elif to_bill_flag is True and has_invoice_quantity:
            billable_hours = detail_hours(detail)
            billable_source = "Ore Enable Invoice CRM"
        else:
            billable_hours = logged_minutes / 60.0
            billable_source = "Ore ZDT"
        if all(base_key):
            billable_by_activity[base_key] = billable_by_activity.get(base_key, 0.0) + billable_hours
            if is_confirmed:
                confirmed_billable_by_activity[base_key] = confirmed_billable_by_activity.get(base_key, 0.0) + billable_hours

        if day and person_key in allowed_people:
            job_description = text_value(detail.get(detail_desc_plan)) if detail_desc_plan else ""
            if not job_description and detail_desc_job:
                job_description = text_value(detail.get(detail_desc_job))
            activity_description = text_value(detail.get(detail_desc_task)) if detail_desc_task else ""
            if not activity_description:
                activity_description = text_value(detail.get("Attivita")) or text_value(detail.get("Descrizione Attivita"))
            customer = customer_by_job.get(normalize(job_code), "") or customer_by_job.get(normalize(base_job), "")
            crm_activity_id = text_value(detail.get(detail_crm_activity_id)) if detail_crm_activity_id else ""
            crm_job_detail_id = text_value(detail.get(detail_crm_job_detail_id)) if detail_crm_job_detail_id else ""
            calendar_plan_key = (
                day, person_key, normalize_code(base_job), normalize(job_description),
            )
            calendar_key = (*calendar_plan_key, normalize(activity_description))
            nav_price = numeric(detail.get(detail_nav_unit_price)) if detail_nav_unit_price else None
            nav_match_count = numeric(detail.get(detail_nav_match_count)) if detail_nav_match_count else None
            nav_match_status = text_value(detail.get(detail_nav_match_status)) if detail_nav_match_status else ""
            nav_plan_description = text_value(detail.get(detail_nav_plan_description)) if detail_nav_plan_description else ""
            activity_key = (
                day, person_key, normalize_code(job_code), normalize_code(task_code), normalize_code(plan_code),
                normalize(job_description), normalize(activity_description), state_key, to_bill_flag, crm_activity_id, crm_job_detail_id,
                nav_price, nav_match_count, nav_match_status, nav_plan_description, billable_source,
            )
            item = revenue_groups.setdefault(activity_key, {
                "date": day, "person": person_raw, "job_code": job_code, "task_code": task_code,
                "plan_code": plan_code, "job_name": job_description, "activity": activity_description,
                "nav_price": nav_price, "nav_match_count": nav_match_count,
                "nav_match_status": nav_match_status, "nav_plan_description": nav_plan_description,
                "state": state_label, "to_bill": to_bill_flag, "crm_activity_id": crm_activity_id, "crm_job_detail_id": crm_job_detail_id, "customer": customer,
                "logged": 0.0, "billable": 0.0, "confirmed_billable": 0.0, "confirmed_logged": 0.0,
                "billable_source": billable_source, "calendar_key": calendar_key,
                "calendar_plan_key": calendar_plan_key,
            })
            item["logged"] += logged_minutes / 60.0
            item["billable"] += billable_hours
            if is_confirmed:
                item["confirmed_billable"] += billable_hours
                item["confirmed_logged"] += logged_minutes / 60.0

    if detail_zdt_state:
        state_counts = detail_frame[detail_zdt_state].fillna("(vuoto)").astype(str).value_counts().head(12).to_dict()
        print(f"Distribuzione aggregata degli stati ZDT: {state_counts}")
    revenue_records = []
    nav_matches_by_zdt_activity = {}
    nav_matches_by_job_task_plan = {}
    nav_matches_by_calendar_activity = {}
    nav_matches_by_calendar_plan = {}
    for item in revenue_groups.values():
        nav_row = {
            "Codice commessa": item["job_code"], "Codice task": item["task_code"],
            "Numero riga commessa": item["plan_code"],
            "CRM Job Detail ID": item["crm_job_detail_id"],
            "Nome commessa": item["job_name"], "Dettaglio attività": item["activity"],
        }
        upstream_price = item["nav_price"]
        upstream_match_count = item["nav_match_count"]
        if upstream_match_count == 1 and upstream_price is not None:
            match = {"price": upstream_price}
            status = "Valorizzata"
            nav_diagnostic = (
                "Tariffa associata dal dettaglio ZDT · match NAV univoco"
                + (f" · {item['nav_plan_description']}" if item["nav_plan_description"] else "")
            )
        else:
            match, status, nav_diagnostic = resolve_job(nav_row)
        zdt_activity_key = (
            item["date"], normalize_person(item["person"]), normalize_code(item["job_code"]),
            normalize_code(item["task_code"]), normalize_code(item["plan_code"]),
        )
        if all(zdt_activity_key):
            nav_matches_by_zdt_activity.setdefault(zdt_activity_key, []).append((match, status, nav_diagnostic))
        job_task_plan_key = (
            normalize_code(item["job_code"]),
            normalize_code(item["task_code"]),
            normalize_code(item["plan_code"]),
        )
        if all(job_task_plan_key):
            nav_matches_by_job_task_plan.setdefault(job_task_plan_key, []).append((match, status, nav_diagnostic))
        if all(item["calendar_plan_key"]):
            nav_matches_by_calendar_plan.setdefault(item["calendar_plan_key"], []).append((match, status, nav_diagnostic))
            if item["calendar_key"][-1]:
                nav_matches_by_calendar_activity.setdefault(item["calendar_key"], []).append((match, status, nav_diagnostic))
        price = match["price"] if match else 0.0
        code = item["job_code"]
        kind = "COIG" if code.upper().startswith("COIG") or item["job_name"].upper().startswith("COIG") or item["activity"].upper().startswith("COIG") else "Non COIG"
        revenue_records.append({
            "Data": item["date"], "Componente": item["person"], "Codice commessa": code,
            "Codice task": item["task_code"], "Numero riga commessa": item["plan_code"],
            "Nome commessa": item["job_name"], "Dettaglio attività": item["activity"],
            "Stato Attivita": item["state"], "ToBill CRM": item["to_bill"], "CRM Activity ID": item["crm_activity_id"],
            "CRM Job Detail ID": item["crm_job_detail_id"],
            "Cliente": item["customer"], "Tipo attività": kind,
            "Ore Loggate": item["logged"], "Ore Confermate": item["confirmed_logged"],
            "Ore valorizzate": item["billable"], "Ore valorizzate confermate": item["confirmed_billable"],
            "Ore valorizzate da confermare": max(item["billable"] - item["confirmed_billable"], 0.0),
            "Prezzo unitario NAV": price, "Stima fatturato": item["billable"] * price,
            "Stima fatturato confermato": item["confirmed_billable"] * price,
            "Stima fatturato da confermare": max(item["billable"] - item["confirmed_billable"], 0.0) * price,
            "Fonte ore stima": item["billable_source"], "Esito valorizzazione": status,
            "Dettaglio tariffa NAV": nav_diagnostic,
        })

    status_counts = {}
    for revenue_row in revenue_records:
        outcome = revenue_row["Esito valorizzazione"]
        status_counts[outcome] = status_counts.get(outcome, 0) + 1
    print(f"Dettagli CRM valorizzati con tariffa NAV: {status_counts.get('Valorizzata', 0)}/{len(revenue_records)}")
    print(f"Esiti NAV aggregati: {status_counts}")

    daily["Prezzo unitario NAV"] = 0.0
    daily["Ore valorizzate"] = 0.0
    daily["Ore valorizzate confermate"] = 0.0
    daily["Ore valorizzate da confermare"] = 0.0
    daily["Stima fatturato"] = 0.0
    daily["Stima fatturato confermato"] = 0.0
    daily["Stima fatturato da confermare"] = 0.0
    daily["Fonte ore stima"] = "Ore Fatturabili CRM per attività"
    daily["Esito valorizzazione"] = ""

    matched_detail_rows = 0
    nav_calendar_matches = 0
    for index, row in daily.iterrows():
        detail_key = (
            detail_day(row.get(date_field)),
            normalize_person(row.get(person_field, "")),
            normalize_code(row.get("Codice commessa")),
            normalize_code(row.get("Codice task")),
            normalize_code(row.get("Numero riga commessa")),
        )
        calendar_plan_key = (
            detail_day(row.get(date_field)),
            normalize_person(row.get(person_field, "")),
            normalize_code(row.get("Codice commessa")),
            normalize(text_value(row.get("Nome commessa"))),
        )
        calendar_key = (*calendar_plan_key, normalize(text_value(row.get("Dettaglio attività"))))
        matched_nav = nav_matches_by_zdt_activity.get(detail_key, [])
        if not matched_nav:
            # La tariffa NAV è legata alla riga commessa, non alla singola data/persona.
            # Il feed economico può quindi trasferirla al calendario tramite la chiave ZDT.
            zdt_job_task_plan_key = (detail_key[2], detail_key[3], detail_key[4])
            matched_nav = nav_matches_by_job_task_plan.get(zdt_job_task_plan_key, [])
        if not matched_nav:
            matched_nav = nav_matches_by_calendar_activity.get(calendar_key, [])
        if not matched_nav:
            matched_nav = nav_matches_by_calendar_plan.get(calendar_plan_key, [])
        if matched_nav:
            nav_calendar_matches += 1
            matched_prices = {entry[0]["price"] for entry in matched_nav if entry[0]}
            if all(entry[1] == "Valorizzata" for entry in matched_nav) and len(matched_prices) == 1:
                price = next(iter(matched_prices))
                match, status = {"price": price}, "Valorizzata"
                nav_diagnostic = "Associata tramite CRM Job Detail ID ZDT e descrizioni condivise con il calendario"
            else:
                match, status = None, "Tariffa NAV non univoca"
                nav_diagnostic = "Righe ZDT collegate a più righe NAV: " + " | ".join(entry[2] for entry in matched_nav)
        else:
            match, status, nav_diagnostic = resolve_job(row)
        daily.at[index, "Esito valorizzazione"] = status
        daily.at[index, "Dettaglio tariffa NAV"] = nav_diagnostic
        if match:
            daily.at[index, "Prezzo unitario NAV"] = match["price"]
        if detail_key not in billable_by_activity:
            # Senza riga CRM/Enable Invoice valorizziamo la stessa durata ZDT del calendario.
            billable_hours = max(numeric(row.get("Ore Loggate")) or 0.0, 0.0)
            confirmed_hours = min(billable_hours, max(numeric(row.get("Ore Confermate")) or 0.0, 0.0))
            daily.at[index, "Ore valorizzate"] = billable_hours
            daily.at[index, "Ore valorizzate confermate"] = confirmed_hours
            daily.at[index, "Ore valorizzate da confermare"] = max(billable_hours - confirmed_hours, 0.0)
            daily.at[index, "Fonte ore stima"] = "Ore ZDT · Enable Invoice assente"
            if match:
                daily.at[index, "Prezzo unitario NAV"] = match["price"]
                daily.at[index, "Stima fatturato"] = billable_hours * match["price"]
                daily.at[index, "Stima fatturato confermato"] = confirmed_hours * match["price"]
                daily.at[index, "Stima fatturato da confermare"] = max(billable_hours - confirmed_hours, 0.0) * match["price"]
                daily.at[index, "Esito valorizzazione"] = "Valorizzata"
            else:
                daily.at[index, "Esito valorizzazione"] = status
            matched_detail_rows += 1
            continue
        billable_hours = billable_by_activity[detail_key]
        matched_detail_rows += 1
        confirmed_hours = min(confirmed_billable_by_activity.get(detail_key, 0.0), billable_hours)
        if not has_detail_confirmations:
            logged_hours = max(numeric(row.get("Ore Loggate")) or 0.0, 0.0)
            confirmed_logged_hours = max(numeric(row.get("Ore Confermate")) or 0.0, 0.0)
            confirmed_share = min(confirmed_logged_hours / logged_hours, 1.0) if logged_hours else 0.0
            confirmed_hours = billable_hours * confirmed_share
        daily.at[index, "Ore valorizzate"] = billable_hours
        daily.at[index, "Ore valorizzate confermate"] = confirmed_hours
        daily.at[index, "Ore valorizzate da confermare"] = max(billable_hours - confirmed_hours, 0.0)
        if match:
            daily.at[index, "Prezzo unitario NAV"] = match["price"]
            daily.at[index, "Stima fatturato"] = billable_hours * match["price"]
            daily.at[index, "Stima fatturato confermato"] = confirmed_hours * match["price"]
            daily.at[index, "Stima fatturato da confermare"] = (billable_hours - confirmed_hours) * match["price"]
        else:
            daily.at[index, "Esito valorizzazione"] = status

    if len(daily) and matched_detail_rows == 0:
        raise ValueError("Nessuna riga giornaliera abbinata al nuovo dettaglio CRM; verificare le chiavi")

    print(f"Righe calendario con tariffa ricavata dal dettaglio ZDT/CRM: {nav_calendar_matches}/{len(daily)}")
    print(f"Righe giornaliere abbinate al dettaglio CRM: {matched_detail_rows}/{len(daily)}")

    daily = daily.rename(columns={date_field: "Data", person_field: "Componente"})
    records = daily.astype(object).where(pd.notna(daily), None).to_dict(orient="records")
    target = Path("public/activity-logs.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(records, ensure_ascii=False, default=str, allow_nan=False), encoding="utf-8")
    revenue_target = Path("public/activity-revenue.json")
    revenue_target.write_text(json.dumps(revenue_records, ensure_ascii=False, default=str, allow_nan=False), encoding="utf-8")
    print(f"Creati {len(revenue_records)} dettagli CRM/NAV per la valorizzazione economica.")
    print(f"Raggruppati {len(records)} totali per i {len(TEAM_MEMBERS)} componenti selezionati: data={date_field}, componente={person_field}, commessa={fields['job_code'] or 'non disponibile'}, descrizione commessa={fields['job_name'] or 'non disponibile'}, attività={fields['activity_name'] or 'non disponibile'}")
    print(f"Dimensione export consuntivazioni: {target.stat().st_size / (1024 * 1024):.1f} MB")
    print(f"Sincronizzati i totali da {account}/{container}/{blob} in {target}")


if __name__ == "__main__":
    main()
