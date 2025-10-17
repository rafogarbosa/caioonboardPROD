# === 00agenda.py ===
import os
import time
import json
import subprocess
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import socket
import psutil
import sys

CREDENTIALS_PATH = "/xcoutfy/credentials.json"
SHEET_NAME = "dbgravacoes"
AGENDA_TAB = "agenda"
AGENDA_PATH = "/xcoutfy/schedules/agenda_backup.json"
RECORDED_DIR = "/xcoutfy/recorded_videos"
UPLOADED_DIR = "/xcoutfy/uploaded_videos"
BROADCAST_DONE_DIR = "/xcoutfy/broadcastdone"
LOG_PATH = "/xcoutfy/logs/00agenda.log"
UPLOAD_SCRIPT = "/xcoutfy/02upload.py"
RECORD_SCRIPT = "/xcoutfy/01v4record.py"
CONTINUOUS_SCRIPT = "/xcoutfy/03gravcont.py"
STREAM_SCRIPT = "/xcoutfy/05streamyt.py"
BROADCAST_SCRIPT = "/xcoutfy/a07broadcast.py"

UPLOAD_PID_FILE = "/tmp/xcoutfy_upload_pid.txt"
RECORD_PID_FILE = "/tmp/xcoutfy_record_pid.txt"
CONTINUOUS_PID_FILE = "/tmp/xcoutfy_continuous_pid.txt"
STREAM_PID_FILE = "/tmp/xcoutfy_stream_pid.txt"
BROADCAST_PID_FILE = "/tmp/xcoutfy_broadcast_pid.txt"

CHECK_INTERVAL = int(os.getenv("AGENDA_REFRESH_INTERVAL", 30))
EXECUTION_TOLERANCE_SEC = 90

os.makedirs(BROADCAST_DONE_DIR, exist_ok=True)
os.makedirs("/xcoutfy/logs", exist_ok=True)

# ===========================
# Logging
# ===========================
class Logger(object):
    def __init__(self, logfile):
        self.terminal = sys.stdout
        self.log = open(logfile, "a", buffering=1)

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = Logger(LOG_PATH)
sys.stderr = sys.stdout

PRIORITY_ORDER = ["RECORDING", "FREE2UP", "CONTINUOUS", "STREAM", "UPLOAD"]
executed_slots = set()
pending_tasks = []  # fila de tarefas pendentes

# ===========================
# Agenda handling
# ===========================
def load_agenda_from_local():
    eqp_name = socket.gethostname().strip().lower()
    if not os.path.exists(AGENDA_PATH):
        return []
    try:
        with open(AGENDA_PATH, "r") as f:
            records = json.load(f)
        return [r for r in records if str(r.get("equipment", "")).strip().lower() == eqp_name]
    except Exception as e:
        print(f"⚠️ Erro ao carregar agenda local ({AGENDA_PATH}): {e}")
        return []

agenda_mem = load_agenda_from_local()


def fetch_latest_agenda():
    """Busca a planilha na nuvem e ignora cabeçalhos vazios, duplicados e linhas em branco."""
    global agenda_mem
    try:
        eqp_name = socket.gethostname().strip().lower()
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_PATH, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).worksheet(AGENDA_TAB)

        # Lê todas as linhas cruas
        all_rows = sheet.get_all_values()
        if not all_rows:
            print("⚠️ Planilha vazia ou inacessível.")
            return

        # Primeira linha = cabeçalho limpo
        #headers = [h.strip() for h in all_rows[0] if h.strip()]
        #data_rows = all_rows[1:]
        # Garante que todos os cabeçalhos existam, mesmo que estejam vazios
        headers = [h.strip() if h.strip() else f"col_{i}" for i, h in enumerate(all_rows[0])]
        data_rows = all_rows[1:]



        records = []
        for row in data_rows:
            # Preenche até o tamanho dos headers e ignora linhas completamente vazias
            if not any(cell.strip() for cell in row):
                continue
            record = dict(zip(headers, row))
            records.append(record)

        # Filtra apenas as linhas do equipamento atual
        filtered = [r for r in records if str(r.get("equipment", "")).strip().lower() == eqp_name]

        # Salva cópia local
        os.makedirs(os.path.dirname(AGENDA_PATH), exist_ok=True)
        with open(AGENDA_PATH, "w") as f:
            json.dump(filtered, f, ensure_ascii=False, indent=2)

        agenda_mem = filtered
        print(f"✅ Agenda atualizada da nuvem. {len(filtered)} tarefas carregadas para {eqp_name}.")
    except Exception as e:
        print(f"⚠️ Erro ao buscar agenda da nuvem: {e}")







# ===========================
# Process handling
# ===========================
def kill_idle_process(pidfile):
    if os.path.exists(pidfile):
        try:
            with open(pidfile, 'r') as f:
                pid = int(f.read().strip())
            p = psutil.Process(pid)
            print(f"⚠️ Detectado processo antigo em execução (PID {pid}). Tentando encerrar...")
            p.terminate()
            try:
                p.wait(timeout=3)
                print(f"✅ Processo {pid} encerrado com sucesso.")
            except psutil.TimeoutExpired:
                print(f"⚠️ Processo {pid} não respondeu, forçando kill...")
                p.kill()
        except Exception as e:
            print(f"⚠️ Erro ao encerrar processo antigo: {e}")
        finally:
            if os.path.exists(pidfile):
                os.remove(pidfile)
                print(f"🗑️ PID file {pidfile} removido.")

    subprocess.run(["pkill", "-9", "ffmpeg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("⏳ Aguardando 30 segundos para liberar a câmera...")
    time.sleep(30)

def run_and_block_until_done(script_path, pidfile, env=None, args=None):
    kill_idle_process(pidfile)
    print(f"🚦 Preparando para iniciar novo processo: {script_path}")
    cmd = [sys.executable, script_path]
    if args:
        cmd += args
    print(f"▶️ Executando comando: {' '.join(cmd)}")
    subprocess.run(cmd, env=env)
    print(f"🏁 Processo finalizado: {script_path}")

def launch_process_and_store_pid(script_path, pidfile, env=None, args=None):
    kill_idle_process(pidfile)
    cmd = [sys.executable, script_path]
    if args:
        cmd += args
    process = subprocess.Popen(cmd, env=env)
    with open(pidfile, 'w') as f:
        f.write(str(process.pid))
    print(f"🚀 {script_path} iniciado com PID {process.pid}")

def launch_upload_or_broadcast():
    if os.listdir(RECORDED_DIR):
        if not os.path.exists(UPLOAD_PID_FILE):
            launch_process_and_store_pid(UPLOAD_SCRIPT, UPLOAD_PID_FILE)
        return
    files = [f for f in os.listdir(UPLOADED_DIR) if f.endswith(".uploaded")]
    if files:
        if not os.path.exists(BROADCAST_PID_FILE):
            launch_process_and_store_pid(BROADCAST_SCRIPT, BROADCAST_PID_FILE)

# ===========================
# Schedule execution
# ===========================
def check_schedule():
    eqp_name = socket.gethostname()
    today = datetime.now().strftime("%A").lower()
    now = datetime.now()
    now_sec = now.hour * 3600 + now.minute * 60 + now.second

    agenda = agenda_mem
    relevant = [a for a in agenda if a.get("equipment") == eqp_name]

    for item in relevant:
        if item.get("day", "").lower() != today:
            continue
        try:
            start = int(item.get("hour", 0)) * 3600 + int(item.get("minute", 0)) * 60
            dur = int(item.get("duration", 0)) * 60
            if not (start - EXECUTION_TOLERANCE_SEC <= now_sec <= start + EXECUTION_TOLERANCE_SEC):
                continue
        except:
            continue

        t = item.get("type", "RECORDING").upper()
        if t not in PRIORITY_ORDER:
            continue

        task_id = f"{item.get('equipment')}_{item.get('day')}_{item.get('hour')}_{item.get('minute')}_{item.get('customer')}"
        if task_id not in executed_slots:
            executed_slots.add(task_id)
            pending_tasks.append((t, item))
            print(f"📌 Tarefa adicionada à fila: {t} para {item.get('customer')} às {item.get('hour')}:{item.get('minute')}")

def process_pending_tasks():
    if not pending_tasks:
        return

    selected_type, selected_item = pending_tasks.pop(0)
    env = os.environ.copy()
    env["CUSTOMER"] = selected_item.get("customer", "unknown")
    env["EQUIPMENT"] = selected_item.get("equipment", "unknown")

    if selected_type == "RECORDING":
        args = [
            "--duration", str(selected_item.get("duration", 5)),
            "--fps", str(selected_item.get("fps", 30)),
            "--left_crop_left", str(selected_item.get("left_crop_left", 0)),
            "--left_crop_right", str(selected_item.get("left_crop_right", 0)),
            "--right_crop_left", str(selected_item.get("right_crop_left", 0)),
            "--right_crop_right", str(selected_item.get("right_crop_right", 0)),
            "--crop_top", str(selected_item.get("crop_top", 0)),
            "--crop_bottom", str(selected_item.get("crop_bottom", 0))
        ]
        print(f"🔔 Executando RECORDING para {selected_item.get('customer')} ({selected_item.get('duration')}s)")
        run_and_block_until_done(RECORD_SCRIPT, RECORD_PID_FILE, env=env, args=args)

    elif selected_type == "FREE2UP":
        dur = int(selected_item.get("duration", 60)) * 60
        start_time = time.time()
        while time.time() - start_time < dur:
            launch_upload_or_broadcast()
            time.sleep(30)

    elif selected_type == "CONTINUOUS":
        args = [
            "--duration", str(selected_item.get("duration", 60)),
            "--fps", str(selected_item.get("fps", 30))
        ]
        run_and_block_until_done(CONTINUOUS_SCRIPT, CONTINUOUS_PID_FILE, env=env, args=args)

    elif selected_type == "STREAM":
        args = [
            "--duration", str(selected_item.get("duration", 300)),
            "--fps", str(selected_item.get("fps", 30))
        ]
        run_and_block_until_done(STREAM_SCRIPT, STREAM_PID_FILE, env=env, args=args)

    elif selected_type == "UPLOAD":
        run_and_block_until_done(UPLOAD_SCRIPT, UPLOAD_PID_FILE, env=env)

# ===========================
# Main loop
# ===========================
#if __name__ == "__main__":
#    last_fetch = 0
#    shown_upcoming = False
#
#    while True:
#        if time.time() - last_fetch >= CHECK_INTERVAL:
#            fetch_latest_agenda()
#            last_fetch = time.time()
#            shown_upcoming = False
#

if __name__ == "__main__":
    last_fetch = 0
    shown_upcoming = False
    FORCE_REFRESH_INTERVAL = 600  # força atualização da nuvem a cada 10 minutos

    while True:
        now_time = time.time()

        # Atualiza agenda periodicamente ou caso a anterior falhe
        if now_time - last_fetch >= CHECK_INTERVAL:
            try:
                fetch_latest_agenda()
                last_fetch = now_time
                print(f"🕒 Checkpoint {datetime.now().strftime('%H:%M:%S')} — Agenda verificada e atualizada.")
                shown_upcoming = False
            except Exception as e:
                print(f"⚠️ Erro durante atualização da agenda: {e}")

        # Força atualização completa da nuvem a cada 10 minutos, mesmo sem mudanças
        if now_time - last_fetch >= FORCE_REFRESH_INTERVAL:
            print(f"🔁 Forçando atualização completa da nuvem às {datetime.now().strftime('%H:%M:%S')}")
            fetch_latest_agenda()
            last_fetch = now_time
            shown_upcoming = False



        if not shown_upcoming:
            eqp_name = socket.gethostname()
            agenda = agenda_mem
            today = datetime.now().strftime("%A").lower()
            now_sec = datetime.now().hour * 3600 + datetime.now().minute * 60 + datetime.now().second

            types = {k: [] for k in PRIORITY_ORDER}
            for item in agenda:
                t = item.get("type", "RECORDING").upper()
                if t in PRIORITY_ORDER:
                    types[t].append(item)

            print(f"📖 Agenda completa ({len(agenda)} tarefas no total):")
            for tipo in PRIORITY_ORDER:
                items = types[tipo]
                print(f"\n🗂️ Tipo: {tipo} ({len(items)} tarefas)")
                for i in items:
                    print(f"  🔸 {i.get('equipment')} - {i.get('day')} {i.get('hour')}:{i.get('minute')} - {i.get('customer')}")

            relevant = [a for a in agenda if a.get("equipment") == eqp_name and a.get("day", "").lower() == today]
            future = []
            for a in relevant:
                try:
                    a_sec = int(a.get("hour", 0)) * 3600 + int(a.get("minute", 0)) * 60
                    if a_sec >= now_sec:
                        future.append((a_sec, a))
                except:
                    continue

            future.sort()
            if future:
                print(f"\n📅 Próximas tarefas para hoje ({eqp_name}):")
                for f in future[:3]:
                    a = f[1]
                    print(f"  ⏰ {a.get('type', '').lower()} às {a.get('hour')}:{a.get('minute')} para {a.get('customer')}")
            else:
                print("ℹ️ Nenhuma tarefa futura para hoje.")

            shown_upcoming = True

        check_schedule()
        process_pending_tasks()
        time.sleep(1)
