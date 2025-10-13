#!/usr/bin/env python3
# Atualiza /xcoutfy/schedules/agenda_backup.json a partir da planilha 'dbgravacoes' aba 'agenda'
import os, json, sys, datetime
import gspread
from google.oauth2.service_account import Credentials

SHEET_NAME = os.getenv("XC_SHEET_NAME", "dbgravacoes")
TAB_NAME   = os.getenv("XC_SHEET_TAB",  "agenda")
OUT_PATH   = os.getenv("XC_OUT_PATH",   "/xcoutfy/schedules/agenda_backup.json")

def get_credentials():
    # Usa GOOGLE_APPLICATION_CREDENTIALS se existir; senão tenta /xcoutfy/credentials.json
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/xcoutfy/credentials.json")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    return Credentials.from_service_account_file(cred_path, scopes=scopes)

def main():
    creds = get_credentials()
    gc = gspread.authorize(creds)
    ws = gc.open(SHEET_NAME).worksheet(TAB_NAME)
    rows = ws.get_all_records()  # lista de dicts

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "sheet": SHEET_NAME,
                "tab": TAB_NAME,
                "updated_at": datetime.datetime.now().isoformat(),
                "rows": rows,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"✅ agenda_backup atualizado: {OUT_PATH} | linhas: {len(rows)}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Falha no refresh: {e}", file=sys.stderr)
        sys.exit(1)
