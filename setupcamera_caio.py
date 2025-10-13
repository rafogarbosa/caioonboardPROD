#!/usr/bin/env python3
# === setupcamera_caio (simplified direct stream) ===
import subprocess
import argparse
import os
import datetime
import gspread
from google.oauth2.service_account import Credentials

# ============================
# 🎠 PARÂMETROS PADRÃO
# ============================
USER_DURATION = 600
USER_QUALITY = '800k'
RESOLUTION = "1280x360"
FPS = 25
FRAME_HEIGHT = 360
LENS_WIDTH = 640

# 🎛️ Cortes padrão
LEFT_CROP_LEFT = 0
LEFT_CROP_RIGHT = 0
RIGHT_CROP_LEFT = 0
RIGHT_CROP_RIGHT = 0
CROP_TOP = 0
CROP_BOTTOM = 0

parser = argparse.ArgumentParser(description="Transmissão direta para YouTube com cortes personalizados")
parser.add_argument('--duration', type=int, default=USER_DURATION)
parser.add_argument('--stream_key', type=str, required=True)
parser.add_argument('--quality', type=str, default=USER_QUALITY)
parser.add_argument('--left_crop_left', type=int, default=LEFT_CROP_LEFT)
parser.add_argument('--left_crop_right', type=int, default=LEFT_CROP_RIGHT)
parser.add_argument('--right_crop_left', type=int, default=RIGHT_CROP_LEFT)
parser.add_argument('--right_crop_right', type=int, default=RIGHT_CROP_RIGHT)
parser.add_argument('--crop_top', type=int, default=CROP_TOP)
parser.add_argument('--crop_bottom', type=int, default=CROP_BOTTOM)
parser.add_argument('--fps', type=int, default=FPS)
args = parser.parse_args()

def detectar_camera_usb():
    for i in range(5):
        device = f"/dev/video{i}"
        if os.path.exists(device):
            print(f"🔍 Testando {device}...")
            try:
                test_cmd = [
                    "ffmpeg", "-f", "v4l2", "-input_format", "mjpeg",
                    "-video_size", RESOLUTION, "-framerate", str(args.fps),
                    "-t", "1", "-i", device, "-vframes", "1", "-f", "null", "-"
                ]
                subprocess.run(test_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                print(f"📷 Câmera funcional detectada: {device}")
                return device
            except subprocess.CalledProcessError:
                print(f"❌ {device} falhou ao capturar imagem.")
    print("❌ Nenhuma câmera USB funcional encontrada.")
    exit(1)

def iniciar_transmissao(device, stream_url):
    crop_top = args.crop_top
    crop_bottom = args.crop_bottom
    crop_height = FRAME_HEIGHT - crop_top - crop_bottom

    lcl = args.left_crop_left
    lcr = args.left_crop_right
    left_width = LENS_WIDTH - lcl - lcr
    left_x = lcl

    rcl = args.right_crop_left
    rcr = args.right_crop_right
    right_width = LENS_WIDTH - rcl - rcr
    right_x = 1280 + rcl

    if left_width <= 0 or right_width <= 0 or crop_height <= 0:
        print("❌ ERRO: Dimensões de corte inválidas. Ajuste os valores.")
        return

    filter_complex = (
        f"[0:v]split=2[left][right];"
        f"[left]crop={left_width}:{crop_height}:{left_x}:{crop_top}[left_crop];"
        f"[right]crop={right_width}:{crop_height}:{right_x}:{crop_top}[right_crop];"
        f"[left_crop][right_crop]hstack=inputs=2[out]"
    )

    ffmpeg_cmd = [
        "ffmpeg",
        "-thread_queue_size", "4096",
        "-f", "v4l2", "-framerate", str(args.fps), "-video_size", RESOLUTION,
        "-input_format", "mjpeg", "-i", device,
        "-thread_queue_size", "4096", "-f", "alsa", "-i", "default",
        "-filter_complex", filter_complex, "-map", "[out]", "-map", "1:a",
        "-vcodec", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-pix_fmt", "yuv420p", "-r", str(args.fps),
        "-b:v", args.quality, "-maxrate", args.quality, "-bufsize", "6000k",
        "-g", str(args.fps * 2),
        "-acodec", "aac", "-ar", "44100", "-b:a", "128k",
        "-t", str(args.duration),
        "-f", "flv", stream_url
    ]

    print("\n🌟 Iniciando transmissão ao vivo para o YouTube")
    print(f"   🕛 Duração: {args.duration} segundos")
    print(f"   🎙️ Dispositivo de áudio: default")
    print(f"   🔌 Resolução: {RESOLUTION} @ {args.fps}fps")
    print(f"   👀 Cortes: L({lcl}:{left_width}) R({right_x}:{right_width}) Top/Bottom({crop_top}/{crop_bottom})")
    print(f"   ✉️ Enviando para: {stream_url}\n")

    subprocess.run(ffmpeg_cmd)

def registrar_link_youtube():
    try:
        youtube_channel_id = os.getenv("YOUTUBE_CHANNEL_ID", "")
        if not youtube_channel_id:
            print("⚠️ Canal do YouTube não definido.")
            return

        credentials_path = "/xcoutfy/credentials.json"
        spreadsheet_name = "dbgravacoes"
        worksheet_name = "registros"

        credentials = Credentials.from_service_account_file(credentials_path)
        client = gspread.authorize(credentials)
        sheet = client.open(spreadsheet_name).worksheet(worksheet_name)

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        youtube_url = f"https://www.youtube.com/channel/{youtube_channel_id}/live"
        sheet.append_row([now, youtube_url, "stream", os.getenv("CUSTOMER", ""), os.getenv("EQUIPMENT", "")])
        print(f"📝 Link registrado na planilha: {youtube_url}")
    except Exception as e:
        print(f"⚠️ Erro ao registrar link no Google Sheets: {e}")

def main():
    device = detectar_camera_usb()
    stream_url = f"rtmp://a.rtmp.youtube.com/live2/{args.stream_key}"
    iniciar_transmissao(device, stream_url)
    print("✅ Transmissão encerrada.")
    registrar_link_youtube()

if __name__ == "__main__":
    main()
