#!/usr/bin/env python3
# === 02upload.py (tolerância de janela + registro por cabeçalho) ===
import os
import subprocess
import time
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import shutil
import sys
import psutil
import hashlib
from contextlib import contextmanager
from a07broadcast import get_agenda, get_current_window

# =========================
# Constantes / Paths
# =========================
CREDENTIALS_PATH = "/xcoutfy/credentials.json"
SHEET_NAME = "dbgravacoes"
SHEET_REGISTERS = "registros"

VIDEO_DIRS = ["/xcoutfy/recorded_videos", "/xcoutfy/storage_videos"]
UPLOADED_DIR = "/xcoutfy/uploaded_videos"
RCLONE_REMOTE = "xcoutfyvideos:xcvideos"

UPLOAD_DELAY_SEC = 30  # mantém o buffer pra HDD/Drive
LOCK_FILE = "/tmp/xcoutfy_upload.lock"
PID_FILE = "/tmp/xcoutfy_upload.pid"
LOG_FILE = "/xcoutfy/logs/02upload.log"

# Tolerâncias de janela FREE2UP
GRACE_BEFORE_SEC = 90   # se faltar <= 90s pra janela abrir, espera e segue
GRACE_AFTER_SEC  = 300  # se a janela abriu há <= 5min, ainda aceita

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

sys.stdout = Logger(LOG_FILE)
sys.stderr = sys.stdout

# =========================
# Utilitários
# =========================
@contextmanager
def file_lock(lock_path):
    """Evita execuções paralelas."""
    if os.path.exists(lock_path):
        print(f"⚠️ Lock ativo ({lock_path}), encerrando.")
        return
    try:
        open(lock_path, "w").close()
        yield
    finally:
        if os.path.exists(lock_path):
            os.remove(lock_path)

def is_already_running(pid_file):
    """Verifica se já existe outro processo ativo."""
    if os.path.exists(pid_file):
        with open(pid_file, "r") as f:
            pid = int(f.read().strip())
        if psutil.pid_exists(pid):
            print(f"⚠️ Processo já em execução (PID {pid}), abortando nova instância.")
            return True
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))
    return False

def clear_pid(pid_file):
    if os.path.exists(pid_file):
        os.remove(pid_file)

def get_mp4_files():
    """Coleta vídeos MP4 de diretórios configurados."""
    all_files = []
    for d in VIDEO_DIRS:
        if not os.path.exists(d):
            continue
        for f in os.listdir(d):
            if f.endswith(".mp4"):
                all_files.append(os.path.join(d, f))
    return all_files

def file_hash(path):
    """Hash MD5 para evitar uploads duplicados."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def connect_sheets():
    """Autentica no Google Sheets com escopos completos (Sheets + Drive)."""
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client

# ---------- Janela FREE2UP com tolerância ----------
def _parse_today_dt(hour, minute):
    now = datetime.now()
    try:
        return now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
    except Exception:
        return None

def _find_upcoming_free2up(agenda):
    """Retorna (start_dt, end_dt) da próxima janela FREE2UP para este host, se achada."""
    host = os.uname()[1]
    best = None
    for item in (agenda or []):
        try:
            if str(item.get("type", "")).lower() != "free2up":
                continue
            # se houver filtro de equipamento/host, respeita
            eqp = str(item.get("equipment", "") or item.get("equipamento", "") or "")
            if eqp and eqp != host:
                continue
            hour = item.get("hour") or item.get("hora")
            minute = item.get("minute") or item.get("minuto")
            duration = item.get("duration") or item.get("duracao") or item.get("tempo") or 600
            start = _parse_today_dt(hour, minute)
            if not start:
                continue
            end = start + timedelta(seconds=int(duration))
            if not best or start < best[0]:
                best = (start, end)
        except Exception:
            continue
    return best  # (start_dt, end_dt) ou None

def ensure_free2up_window():
    """
    Garante que estamos numa janela FREE2UP, com tolerância:
      - Se faltar <= GRACE_BEFORE_SEC para iniciar, espera até abrir.
      - Se já abriu há <= GRACE_AFTER_SEC, segue mesmo assim.
    Retorna True se pode seguir; False caso contrário.
    """
    try:
        agenda, _ = get_agenda()
        # tenta janela “oficial” do helper
        window = get_current_window(agenda)
    except Exception as e:
        print(f"⚠️ Erro ao buscar agenda: {e}")
        agenda, window = None, None

    # Compatibilidade com tupla
    if isinstance(window, tuple):
        try:
            window = window[0] if len(window) > 0 else {}
        except Exception:
            window = {}

    now = datetime.now()

    # 1) Se já veio uma janela ativa e for FREE2UP, segue
    if isinstance(window, dict) and str(window.get("type", "")).lower() == "free2up":
        print("✅ Janela FREE2UP ativa (via get_current_window).")
        return True

    # 2) Descobrir próxima janela do dia e aplicar tolerâncias
    start_end = _find_upcoming_free2up(agenda or [])
    if not start_end:
        print("⏹️ Nenhuma janela FREE2UP encontrada para hoje. Encerrando.")
        return False

    start, end = start_end
    if now < start:
        delta = (start - now).total_seconds()
        if delta <= GRACE_BEFORE_SEC:
            print(f"⏳ Janela FREE2UP começa em {int(delta)}s. Aguardando abertura...")
            time.sleep(max(1, int(delta)))
            print("🟢 Janela aberta. Seguindo.")
            return True
        else:
            print(f"⏹️ Janela FREE2UP ainda demora ({int(delta)}s). Encerrando.")
            return False
    elif now > end:
        # passou, mas dá uma folga
        delta_end = (now - end).total_seconds()
        if delta_end <= GRACE_AFTER_SEC:
            print(f"🟡 Janela FREE2UP acabou há {int(delta_end)}s, mas dentro da tolerância. Seguindo.")
            return True
        else:
            print(f"⏹️ Janela FREE2UP encerrada há {int(delta_end)}s. Encerrando.")
            return False
    else:
        # dentro do intervalo
        print("✅ Dentro da janela FREE2UP.")
        return True

# ---------- Upload + Link ----------
def upload_to_drive(filepath):
    """Faz upload via rclone e retorna o link público."""
    filename = os.path.basename(filepath)
    remote_path = f"{RCLONE_REMOTE}/{filename}"
    print(f"☁️ Enviando {filename} para {remote_path} ...")

    result = subprocess.run(
        ["rclone", "copy", filepath, RCLONE_REMOTE, "--progress"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(result.stdout)

    # Gera link público
    try:
        link_proc = subprocess.run(
            ["rclone", "link", f"{remote_path}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        link = link_proc.stdout.strip()
    except Exception as e:
        print(f"⚠️ Falha ao gerar link: {e}")
        link = "N/A"
    return link

# ---------- Registro por cabeçalho ----------
def _parse_from_filename(filename):
    """
    Extrai cliente, equipamento, dia_semana, duracao do padrão:
    YYYY_MM_DD___HH_MM___<cliente>_<equipamento>_<Dia>_<duracao>.mp4
    """
    base = os.path.basename(filename)
    name = base[:-4] if base.lower().endswith(".mp4") else base
    parts = name.split("___")
    cliente = equipamento = dia_semana = duracao = ""
    if len(parts) >= 3:
        tail = parts[2]  # <cliente>_<equip>_<Dia>_<duracao>
        segs = tail.split("_")
        if len(segs) >= 4:
            cliente = segs[0]
            equipamento = segs[1]
            dia_semana = segs[2]
            duracao = segs[3]
    return cliente, equipamento, dia_semana, duracao






def register_on_sheet(sheet_client, filename, drive_link):
    """
    Lê a primeira linha (cabeçalho) e preenche por nome de coluna.
    Suporta diretamente os headers:
      timestamp, duration, customer, local, equipment, day,
      filename, drive_link, youtube_link, status, notes
    Mantém compatibilidade com sinônimos usados em versões antigas.
    """
    try:
        sheet = sheet_client.open(SHEET_NAME).worksheet(SHEET_REGISTERS)
        header = sheet.row_values(1)
        if not header:
            # Fallback simples se não houver cabeçalho
            sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                              filename, drive_link, os.uname()[1]])
            print(f"📊 Registro adicionado (fallback) para {filename}")
            return

        # ====== dados vindos do arquivo ======
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        customer, equipment, day_name, duration = _parse_from_filename(filename)
        host = os.uname()[1]
        status = "uploaded"
        youtube_link = ""   # ainda não temos aqui
        notes = ""          # opcional

        # ====== mapa por nomes de coluna ======
        # Mapeia tanto os nomes "oficiais" quanto sinônimos comuns
        candidates = {
            # timestamp
            "timestamp": now_str, "data_hora": now_str, "datahora": now_str, "data": now_str,

            # duration
            "duration": duration, "duracao": duration,

            # customer
            "customer": customer, "cliente": customer,

            # local (deixa vazio por enquanto; pode preencher com site/campo se tiver)
            "local": "",

            # equipment
            "equipment": equipment, "equipamento": equipment, "eqp": equipment,

            # day
            "day": day_name, "dia_semana": day_name, "weekday": day_name, "dia": day_name,

            # filename
            "filename": filename, "arquivo": filename, "file": filename,

            # drive_link
            "drive_link": drive_link, "link": drive_link, "url": drive_link,

            # youtube_link
            "youtube_link": youtube_link, "yt_link": youtube_link,

            # status
            "status": status,

            # notes
            "notes": notes, "observacoes": notes,

            # host/pc
            "host": host, "pc": host, "hostname": host,
        }

        # monta a linha respeitando a ordem real do cabeçalho
        row = []
        for col in header:
            key = col.strip().lower()
            row.append(candidates.get(key, ""))

        sheet.append_row(row)
        print(f"📊 Registro adicionado para {filename}")
    except Exception as e:
        print(f"⚠️ Falha ao registrar no Sheets: {e}")









# =========================
# Main
# =========================
def main():
    print("🌀 Iniciando 02upload.py...")
    if is_already_running(PID_FILE):
        return

    with file_lock(LOCK_FILE):
        # Janela com tolerância (espera se estiver prestes a abrir)
        if not ensure_free2up_window():
            print("⏹️ Nenhuma janela FREE2UP ativa (ou fora da tolerância). Encerrando.")
            clear_pid(PID_FILE)
            return

        print("✅ Janela FREE2UP confirmada. Iniciando uploads...")

        time.sleep(UPLOAD_DELAY_SEC)
        print(f"⏳ Aguardado {UPLOAD_DELAY_SEC}s antes de iniciar uploads...")

        files = get_mp4_files()
        if not files:
            print("📭 Nenhum vídeo para enviar.")
            clear_pid(PID_FILE)
            return

        print(f"🎞️ {len(files)} vídeo(s) encontrado(s). Conectando ao Sheets...")
        client = connect_sheets()

        uploaded_hashes = set()
        for f in files:
            h = file_hash(f)
            if h in uploaded_hashes:
                print(f"⚠️ Arquivo duplicado detectado: {f}")
                continue
            uploaded_hashes.add(h)

            link = upload_to_drive(f)
            register_on_sheet(client, os.path.basename(f), link)

            # Move o arquivo para uploaded_videos
            os.makedirs(UPLOADED_DIR, exist_ok=True)
            dest = os.path.join(
                UPLOADED_DIR, os.path.basename(f).replace(".mp4", ".uploaded")
            )
            try:
                shutil.move(f, dest)
                print(f"📦 Movido para {dest}")
            except Exception as e:
                print(f"⚠️ Falha ao mover arquivo: {e}")

        print("✅ Todos os uploads finalizados.")
        clear_pid(PID_FILE)

if __name__ == "__main__":
    main()
