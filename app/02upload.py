#!/usr/bin/env python3
# === 02upload.py (versão corrigida para parsing de metadados) ===
import os
import subprocess
import time
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import shutil
import sys
from a07broadcast import get_agenda, get_current_window

# =========================
# Logging
# =========================
class Logger(object):
    def __init__(self, logfile):
        self.terminal = sys.stdout
        os.makedirs(os.path.dirname(logfile), exist_ok=True)
        self.log = open(logfile, "a", buffering=1, encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = Logger("/xcoutfy/logs/02upload.log")
sys.stderr = sys.stdout

# =========================
# Config
# =========================
CREDENTIALS_PATH = "/xcoutfy/credentials.json"
SHEET_NAME = "dbgravacoes"
SHEET_REGISTERS = "registros"
VIDEO_DIRS = ["/xcoutfy/recorded_videos", "/xcoutfy/storage_videos"]
UPLOADED_DIR = "/xcoutfy/uploaded_videos"
RCLONE_REMOTE = "xcoutfyvideos:xcvideos"
UPLOAD_DELAY_SEC = 30
CHECK_INTERVAL = 30

# =========================
# Helpers
# =========================
def connect_to_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
    client = gspread.authorize(creds)
    return client


def extract_metadata_from_filename(filename: str):
    """
    Extrai informações do nome do arquivo no formato:
    YYYY_MM_DD___HH_MM___customer_equipment_day_duration.mp4
    Exemplo: 2025_10_08___10_13___customer_xcpc16_Quarta_5.0min.mp4
    """
    try:
        name = os.path.basename(filename).replace(".mp4", "")

        # Divide em blocos separados por '___'
        parts = name.split("___")
        if len(parts) < 3:
            return "unknown_customer", "unknown_eqp", "unknown_day", "unknown_duration"

        meta_part = parts[2]  # terceira parte contém os metadados
        meta_parts = meta_part.split("_")

        customer = meta_parts[0] if len(meta_parts) > 0 else "unknown_customer"
        equipment = meta_parts[1] if len(meta_parts) > 1 else "unknown_eqp"
        day = meta_parts[2] if len(meta_parts) > 2 else "unknown_day"
        duration = meta_parts[3] if len(meta_parts) > 3 else "unknown_duration"

        return customer, equipment, day, duration

    except Exception as e:
        print(f"⚠️ Erro ao extrair metadados: {e}")
        return "unknown_customer", "unknown_eqp", "unknown_day", "unknown_duration"


def append_row_safe(sheet, values):
    for attempt in range(1, 4):
        try:
            sheet.append_row(values)
            print(f"✅ Registro inserido na planilha (tentativa {attempt}).")
            return True
        except Exception as e:
            print(f"⚠️ Falha ao registrar na planilha (tentativa {attempt}): {e}")
            time.sleep(3)
    print("🚨 Falhou ao registrar na planilha após 3 tentativas.")
    return False


def upload_video(filepath, filename, register_sheet):
    if not os.path.exists(filepath):
        print(f"⚠️ Arquivo {filename} não encontrado. Pulando.")
        return

    # Extrai metadados do nome do arquivo
    customer, equipment, day, duration = extract_metadata_from_filename(filename)
    local = equipment  # por enquanto o local é igual ao equipamento

    # Cria timestamp completo
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    destination_remote = f"{RCLONE_REMOTE}/{filename}"
    print(f"🚀 Enviando {filename} ao Google Drive...")
    upload_result = subprocess.run(["rclone", "copy", filepath, RCLONE_REMOTE, "-v"])

    if upload_result.returncode != 0:
        print(f"❌ Falha no upload de {filename}")
        return

    # Verifica se o arquivo aparece no Drive
    for _ in range(10):
        check = subprocess.run(
            ["rclone", "lsf", RCLONE_REMOTE],
            capture_output=True,
            text=True,
        )
        if filename in check.stdout:
            break
        time.sleep(1)

    # Gera link público
    try:
        link_result = subprocess.run(
            ["rclone", "link", destination_remote],
            capture_output=True,
            text=True,
            check=True,
        )
        public_link = link_result.stdout.strip()
        print(f"🔗 Link público: {public_link}")
    except subprocess.CalledProcessError:
        public_link = f"https://drive.google.com/drive/u/0/search?q={filename}"
        print("⚠️ Falha ao gerar link público com rclone.")

    # Registro na planilha
    values = [
        timestamp,
        duration,
        customer,
        local,
        equipment,
        day,
        filename,
        public_link,
        "",  # youtube_link
        "uploaded",  # status
        "",  # notes
    ]
    append_row_safe(register_sheet, values)

    # Move o arquivo local para uploaded_videos
    os.makedirs(UPLOADED_DIR, exist_ok=True)
    final_path = os.path.join(UPLOADED_DIR, filename + ".uploaded")
    try:
        shutil.move(filepath, final_path)
        print(f"📁 Arquivo movido para {final_path}")
    except FileNotFoundError:
        print(f"⚠️ Arquivo {filename} já havia sido movido ou excluído.")


# =========================
# Main
# =========================
def main():
    print("🌀 Iniciando 02upload.py...")
    os.makedirs(UPLOADED_DIR, exist_ok=True)

    # Conecta ao Sheets
    try:
        sheets = connect_to_sheets()
        register_sheet = sheets.open(SHEET_NAME).worksheet(SHEET_REGISTERS)
        print(f"✅ Conectado à planilha '{SHEET_NAME}', aba '{SHEET_REGISTERS}'.")
    except Exception as e:
        print(f"❌ Falha ao conectar à planilha: {e}")
        return

    # Janela FREE2UP
    agenda, _ = get_agenda()
    free2up_info, end_window = get_current_window(agenda)

    if not free2up_info:
        print("⏹️ Nenhuma janela FREE2UP ativa. Encerrando.")
        return

    while True:
        if end_window and datetime.now() > end_window:
            print("⏹️ Janela FREE2UP encerrada. Saindo do upload.")
            break

        now = time.time()
        uploads_pending = False

        for folder in VIDEO_DIRS:
            if not os.path.exists(folder):
                continue
            files = [
                f
                for f in os.listdir(folder)
                if f.endswith(".mp4")
                and not os.path.exists(os.path.join(UPLOADED_DIR, f + ".uploaded"))
                and now - os.path.getmtime(os.path.join(folder, f)) > UPLOAD_DELAY_SEC
            ]
            if files:
                print(f"🎮 {len(files)} vídeo(s) encontrados em {folder}.")
                uploads_pending = True
            for name in files:
                filepath = os.path.join(folder, name)
                upload_video(filepath, name, register_sheet)

        if not uploads_pending:
            print("✅ Nenhum vídeo pendente. Encerrando.")
            break

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
