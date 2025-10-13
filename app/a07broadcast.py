# === a07broadcast.py ===
import os
import time
import subprocess
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import shutil
import logging

# === CONFIGURATION ===
CREDENTIALS_PATH = "/xcoutfy/credentials.json"
SHEET_NAME = "dbgravacoes"
SHEET_REGISTROS = "registros"
AGENDA_TAB = "agenda"
UPLOADED_DIR = "/xcoutfy/uploaded_videos"
DONE_DIR = "/xcoutfy/broadcastdone"
LOG_FILE = "/xcoutfy/logs/a07broadcast.log"
WAIT_AFTER_STREAM_SEC = 120  # Tempo (em segundos) para esperar entre transmissões

# === LOGGING ===
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

def get_agenda():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scope)
    client = gspread.authorize(creds)
    agenda = client.open(SHEET_NAME).worksheet(AGENDA_TAB).get_all_records()
    registros = client.open(SHEET_NAME).worksheet(SHEET_REGISTROS)
    return agenda, registros

def get_current_window(agenda):
    now = datetime.now()
    today = now.strftime('%A').lower()
    for r in agenda:
        if str(r.get("type", "")).strip().lower() != "free2up":
            continue
        if str(r.get("day", "")).strip().lower() not in [today, "everyday"]:
            continue
        try:
            sh = int(r.get("hour", 0))
            sm = int(r.get("minute", 0))
            dur = int(r.get("duration", 0))
            start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
            end = start + timedelta(seconds=dur)
            if start <= now <= end:
                return r, end
        except:
            continue
    return None, None

def get_oldest_uploaded():
    files = sorted([f for f in os.listdir(UPLOADED_DIR) if f.endswith(".uploaded")])
    return files[0] if files else None

def stream_video(video_path, rtmp_key):
    ffmpeg_cmd = [
        "ffmpeg", "-re", "-i", video_path,
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-shortest", "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "128k",
        "-f", "flv", f"rtmp://a.rtmp.youtube.com/live2/{rtmp_key}"
    ]
    return subprocess.run(ffmpeg_cmd).returncode == 0

def move_to_done(video_file):
    if not os.path.exists(DONE_DIR):
        os.makedirs(DONE_DIR)
    src = os.path.join(UPLOADED_DIR, video_file)
    dst = os.path.join(DONE_DIR, video_file.replace(".uploaded", ".broadcasted"))
    shutil.move(src, dst)

def register_link(registros_sheet, video_file, yt_link):
    registros = registros_sheet.get_all_records()
    for idx, row in enumerate(registros, start=2):
        if row.get("filename") == video_file.replace(".uploaded", ""):
            headers = registros_sheet.row_values(1)
            if "youtube_link" in headers:
                col_index = headers.index("youtube_link") + 1
                registros_sheet.update_cell(idx, col_index, yt_link)
            break

def main():
    agenda, registros_sheet = get_agenda()
    free2up_info, end_window = get_current_window(agenda)
    if not free2up_info:
        logging.info("Nenhuma janela FREE2UP ativa.")
        print("ℹ️ Nenhuma janela FREE2UP ativa no momento.")
        return

    while True:
        oldest = get_oldest_uploaded()
        if not oldest:
            logging.info("Nenhum vídeo restante para transmitir.")
            print("✅ Todos os vídeos foram transmitidos.")
            break

        video_path = os.path.join(UPLOADED_DIR, oldest)
        try:
            video_duration = int(float(subprocess.check_output([
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path
            ]).decode().strip()))
        except Exception as e:
            logging.error(f"Erro ao obter duração de {oldest}: {e}")
            print(f"❌ Erro ao obter duração de {oldest}: {e}")
            break

        if (end_window - datetime.now()).total_seconds() < video_duration:
            logging.info(f"Tempo restante insuficiente para vídeo de {video_duration}s")
            print(f"⏳ Tempo restante insuficiente para vídeo de {video_duration}s")
            break

        rtmp_key = free2up_info.get("rtmp_key")
        visibility = free2up_info.get("visibility", "unlisted").strip().lower()

        logging.info(f"Iniciando broadcast de {oldest} para RTMP {rtmp_key} com visibilidade {visibility}")
        print(f"🚀 Transmitindo {oldest} para o YouTube...")
        success = stream_video(video_path, rtmp_key)

        if success:
            yt_link = f"https://youtube.com/channel/{free2up_info.get('youtube_channel_id')}"
            move_to_done(oldest)
            register_link(registros_sheet, oldest, yt_link)
            logging.info(f"Broadcast concluído com sucesso: {yt_link}")
            print(f"✅ Broadcast concluído: {yt_link}")
            logging.info(f"⏱ Aguardando {WAIT_AFTER_STREAM_SEC} segundos antes da próxima transmissão.")
            print(f"⏱ Aguardando {WAIT_AFTER_STREAM_SEC} segundos antes da próxima transmissão...")
            time.sleep(WAIT_AFTER_STREAM_SEC)

        else:
            logging.error(f"Erro ao transmitir o vídeo: {oldest}")
            print(f"❌ Falha na transmissão do vídeo: {oldest}")
            break

if __name__ == "__main__":
    try:
        main()
        logging.info("✅ Finalizado: todos os vídeos transmitidos ou não há tempo suficiente na janela atual.")
        print("✅ a07broadcast.py finalizado: nada mais a transmitir.")
    except Exception as e:
        logging.error(f"❌ Erro inesperado: {e}")
        print(f"❌ Erro inesperado durante execução: {e}")
