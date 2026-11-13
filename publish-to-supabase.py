#!/usr/bin/env python3
"""Compress exports and upload them to the private Activity Hub Supabase bucket."""
import gzip
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

FILES = {
    "activity-logs.json": "activity-logs.json.gz",
    "jobs.json": "jobs.json.gz",
    "resources.json": "resources.json.gz",
    "DEV/activity-logs.json": "DEV/activity-logs.json.gz",
}
DEV_MEMBERS = {
    "Albanese Lorenzo", "Brigo Matteo", "Brotto Fabio", "Cecchin Chiara",
    "Cestaro Luca", "Dian Enrico", "Luise Alessandro", "Marino Daniele",
    "Verzotto Maria", "Rampazzo Lisa", "Sarto Michele", "Omodei Cesare",
}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def normalize_name(value):
    import unicodedata
    normalized = unicodedata.normalize("NFD", str(value or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower().replace(" ", "").replace("'", "")


def create_dev_activity_export():
    source = Path("public") / "activity-logs.json"
    rows = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"{source} non contiene una lista valida.")
    allowed = {normalize_name(name) for name in DEV_MEMBERS}
    dev_rows = [
        row for row in rows
        if normalize_name(row.get("Componente", "")) in allowed
    ]
    if not dev_rows:
        raise ValueError("Export DEV vuoto: nessun componente DEV corrisponde ai dati, upload interrotto.")
    target = Path("public") / "DEV" / "activity-logs.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dev_rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Creato export DEV: {len(dev_rows)} righe su {len(rows)} totali.")


def main():
    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base_url or not service_key:
        raise RuntimeError("Impostare i secrets SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY.")

    for source_name, target_name in FILES.items():
        source = Path("public") / source_name
        if not source.is_file():
            raise FileNotFoundError(f"Export richiesto mancante: {source}")
        raw = source.read_bytes()
        decoded = json.loads(raw)
        if not isinstance(decoded, list) or not decoded:
            raise ValueError(f"{source} è vuoto o non contiene una lista valida.")
        compressed = gzip.compress(raw, compresslevel=6)
        if len(compressed) > MAX_UPLOAD_BYTES:
            raise ValueError(f"{target_name} supera il limite di upload di 50 MiB.")
        url = f"{base_url}/storage/v1/object/activityhub-data/{target_name}"
        request = Request(
            url,
            data=compressed,
            method="POST",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/gzip",
                "x-upsert": "true",
            },
        )
        try:
            with urlopen(request, timeout=180) as response:
                if response.status not in (200, 201):
                    raise RuntimeError(f"Upload {target_name}: HTTP {response.status}")
                print(f"Caricato {target_name}: {len(compressed) / 1024 / 1024:.1f} MiB compressi.")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Upload {target_name} fallito (HTTP {exc.code}): {detail}") from exc


if __name__ == "__main__":
    main()
