# === 01v4record.py ===
import subprocess
import os
import datetime
import argparse
import psutil
import sys
import time

# === DEFAULT CONFIG ===
DEFAULT_DURATION = 5
DEFAULT_BITRATE = '5M'
DEFAULT_RESOLUTION = "2560x720"
DEFAULT_FPS = 30
FRAME_HEIGHT = 720
LENS_WIDTH = 1280
OUTPUT_DIR = "/xcoutfy/recorded_videos"

DEFAULT_LEFT_CROP_LEFT = 0
DEFAULT_LEFT_CROP_RIGHT = 300
DEFAULT_RIGHT_CROP_LEFT = 300
DEFAULT_RIGHT_CROP_RIGHT = 0
DEFAULT_CROP_TOP = 0
DEFAULT_CROP_BOTTOM = 0

# === ARGUMENT PARSER ===
parser = argparse.ArgumentParser(description="Video recorder with cropping. Upload handled separately.")
parser.add_argument('--duration', type=int, default=DEFAULT_DURATION)
parser.add_argument('--bitrate', type=str, default=DEFAULT_BITRATE)
parser.add_argument('--resolution', type=str, default=DEFAULT_RESOLUTION)
parser.add_argument('--fps', type=int, default=DEFAULT_FPS)
parser.add_argument('--left_crop_left', type=int, default=DEFAULT_LEFT_CROP_LEFT)
parser.add_argument('--left_crop_right', type=int, default=DEFAULT_LEFT_CROP_RIGHT)
parser.add_argument('--right_crop_left', type=int, default=DEFAULT_RIGHT_CROP_LEFT)
parser.add_argument('--right_crop_right', type=int, default=DEFAULT_RIGHT_CROP_RIGHT)
parser.add_argument('--crop_top', type=int, default=DEFAULT_CROP_TOP)
parser.add_argument('--crop_bottom', type=int, default=DEFAULT_CROP_BOTTOM)
args = parser.parse_args()

os.makedirs(OUTPUT_DIR, exist_ok=True)

RECORD_PID_FILE = "/tmp/xcoutfy_record_pid.txt"

DIAS_SEMANA = {
    "monday": "Segunda",
    "tuesday": "Terca",
    "wednesday": "Quarta",
    "thursday": "Quinta",
    "friday": "Sexta",
    "saturday": "Sabado",
    "sunday": "Domingo"
}

def clear_old_record_pid():
    if os.path.exists(RECORD_PID_FILE):
        try:
            with open(RECORD_PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            if psutil.pid_exists(old_pid):
                print(f"⚠️ Finalizando gravação anterior (PID {old_pid})")
                p = psutil.Process(old_pid)
                p.terminate()
                try:
                    p.wait(timeout=5)
                except psutil.TimeoutExpired:
                    p.kill()
            else:
                print(f"⚠️ PID {old_pid} não está ativo, removendo registro")
        except Exception as e:
            print(f"⚠️ Não foi possível finalizar processo anterior: {e}")
        finally:
            os.remove(RECORD_PID_FILE)

    # ✅ Extra: força kill de qualquer ffmpeg que sobrou
    subprocess.run(["pkill", "-9", "ffmpeg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)  # respiro pro kernel soltar a câmera


def detect_usb_camera():
    # ✅ Prioriza testar video1 antes do video2
    preferred_order = [1, 2, 0, 3, 4]
    for i in preferred_order:
        device = f"/dev/video{i}"
        if os.path.exists(device):
            print(f"🔍 Testing {device}...")
            try:
                test_cmd = [
                    "ffmpeg", "-f", "v4l2", "-input_format", "mjpeg",
                    "-video_size", args.resolution, "-framerate", str(args.fps),
                    "-t", "1", "-i", device, "-vframes", "1", "-f", "null", "-"
                ]
                subprocess.run(test_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                print(f"📷 Functional USB camera detected: {device}")
                return device
            except subprocess.CalledProcessError:
                print(f"❌ {device} failed to capture.")
    print("❌ No working USB camera found.")
    exit(1)


def main():
    clear_old_record_pid()

    customer = os.environ.get("CUSTOMER", "unknown_client")
    equipment = os.environ.get("EQUIPMENT", "unknown_eqp")

    day_env = os.environ.get("DAY", "").lower()
    if day_env in DIAS_SEMANA:
        day = DIAS_SEMANA[day_env]
    else:
        day = DIAS_SEMANA[datetime.datetime.now().strftime("%A").lower()]

    duration_secs = args.duration
    duration_min = duration_secs / 60

    now = datetime.datetime.now()
    filename = (
        f"{now.strftime('%Y_%m_%d___%H_%M')}___"
        f"{customer}_{equipment}_{day}_{duration_min:.1f}min.mp4"
    )
    output_path = os.path.join(OUTPUT_DIR, filename)

    print(f"🎬 v4record iniciado | CUSTOMER={customer} | EQUIPMENT={equipment} | DAY={day} | args={args}")

    device = detect_usb_camera()

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

    print("🔍 Calculating final cropping dimensions:")
    print(f"  🗾 Left lens  -> width: {left_width}px, x offset: {left_x}")
    print(f"  🔳 Right lens -> width: {right_width}px, x offset: {right_x}")
    print(f"  ↕️ Height after crop: {crop_height}px (from 720px)")

    if left_width <= 0 or right_width <= 0 or crop_height <= 0:
        print("❌ ERROR: Invalid crop dimensions. Please adjust the values.")
        return

    filter_complex = (
        f"[0:v]split=2[left][right];"
        f"[left]crop={left_width}:{crop_height}:{left_x}:{crop_top}[left_crop];"
        f"[right]crop={right_width}:{crop_height}:{right_x}:{crop_top}[right_crop];"
        f"[left_crop][right_crop]hstack=inputs=2[out]"
    )

    ffmpeg_cmd = [
        "ffmpeg",
        # entrada vídeo
        "-thread_queue_size", "1024", "-f", "v4l2",
        "-framerate", str(args.fps), "-video_size", args.resolution, "-input_format", "mjpeg",
        "-i", device,

        # entrada áudio (buffer maior)
        "-thread_queue_size", "8192", "-f", "alsa",
        "-channels", "1", "-sample_fmt", "s16", "-ar", "44100",
        "-i", "hw:3,0",

        # duração
        "-t", str(duration_secs),

        # filtros de vídeo + áudio
        "-filter_complex", filter_complex,
        "-filter:a", "volume=5.0,aresample=async=1:min_hard_comp=0.100:first_pts=0",

        # mapear vídeo processado + áudio
        "-map", "[out]", "-map", "1:a",

        # sincronização e buffers extras
        "-use_wallclock_as_timestamps", "1",
        "-fflags", "+genpts",
        "-max_interleave_delta", "100M",

        # codecs
        "-c:v", "mpeg4", "-b:v", args.bitrate,
        "-c:a", "aac", "-b:a", "128k",

        "-y", output_path
    ]

    print(f"🎥 Recording for {duration_secs}s to: {output_path}")
    with open(RECORD_PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

    process = subprocess.Popen(ffmpeg_cmd, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    try:
        process.wait(timeout=duration_secs + 5)
    except subprocess.TimeoutExpired:
        print("⚠️ FFmpeg não finalizou no tempo esperado, forçando encerramento...")
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()

    if not os.path.exists(output_path):
        print("❌ Recording failed. File was not created.")
        return

    print("✅ Recording completed.")
    print(f"FILENAME::{filename}")
    print(f"✅ Gravação concluída para {customer} ({equipment})")

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Exceção inesperada durante execução: {e}")
