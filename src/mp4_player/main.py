#!/usr/bin/env python3
"""カレントディレクトリのMP4ファイルを順次再生するプレーヤー"""

import glob
import os
import platform
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


WINDOW_NAME = "MP4 Player"
WINDOW_WIDTH = 960
WINDOW_HEIGHT = 640
BAR_HEIGHT = 100
VIDEO_HEIGHT = WINDOW_HEIGHT - BAR_HEIGHT

# 色定義 (BGR)
COLOR_BG = (30, 30, 30)
COLOR_BAR_BG = (40, 40, 40)
COLOR_TEXT = (255, 255, 255)
COLOR_TEXT_DIM = (150, 150, 150)
COLOR_SEEK_BG = (80, 80, 80)
COLOR_SEEK_FG = (247, 195, 79)
COLOR_HIGHLIGHT = (247, 195, 79)
COLOR_BTN_BG = (60, 60, 60)
COLOR_BTN_HOVER = (80, 80, 80)

# ボタン定義: (label, x_center_offset_from_center, width)
BUTTON_DEFS: list[tuple[str, int, int]] = [
    ("prev", -150, 50),    # ⏮
    ("stop", -80, 50),     # ⏹
    ("play", 0, 60),       # ▶ / ⏸
    ("next", 80, 50),      # ⏭
    ("repeat", 150, 50),   # 🔁
]


def _find_font() -> Optional[str]:
    """日本語対応フォントのパスを探す"""
    if platform.system() == "Darwin":
        candidates = [
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "C:\\Windows\\Fonts\\msgothic.ttc",
            "C:\\Windows\\Fonts\\meiryo.ttc",
        ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _put_text(
    img: np.ndarray,
    text: str,
    pos: tuple[int, int],
    font: Optional[ImageFont.FreeTypeFont],
    size: int,
    color: tuple[int, int, int],
) -> None:
    """Pillowを使ってOpenCV画像に日本語テキストを描画する"""
    if font is None:
        # フォールバック: cv2.putText (日本語は文字化けする)
        cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX,
                    size / 30, color[::-1], 1, cv2.LINE_AA)
        return

    # BGR -> RGB
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(pil_img)
    # OpenCVのBGR色をRGBに変換
    rgb_color = (color[2], color[1], color[0])
    draw.text(pos, text, font=font, fill=rgb_color)
    # RGB -> BGR に戻して元の配列に書き戻す
    result = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    np.copyto(img, result)


def _find_ffmpeg() -> Optional[str]:
    """ffmpegのパスを探す"""
    # PATHから探す
    path = shutil.which("ffmpeg")
    if path:
        return path
    # macOSでよくある場所
    for candidate in ["/Applications/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


class AudioPlayer:
    """ffmpeg + afplay を使った音声再生"""

    def __init__(self) -> None:
        self.ffmpeg_path: Optional[str] = _find_ffmpeg()
        self.afplay_process: Optional[subprocess.Popen[bytes]] = None
        self.temp_dir: str = tempfile.mkdtemp(prefix="mp4_player_")
        self.current_audio_file: Optional[str] = None

    def extract_audio(self, video_path: str) -> Optional[str]:
        """動画から音声をAACファイルに抽出"""
        if self.ffmpeg_path is None:
            return None

        audio_file = os.path.join(self.temp_dir, "audio.m4a")
        # 前の音声ファイルを削除
        if os.path.exists(audio_file):
            os.remove(audio_file)

        try:
            subprocess.run(
                [self.ffmpeg_path, "-i", video_path, "-vn", "-acodec", "copy",
                 "-y", audio_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

        if os.path.exists(audio_file) and os.path.getsize(audio_file) > 0:
            self.current_audio_file = audio_file
            return audio_file
        return None

    def play(self, offset_seconds: float = 0.0) -> None:
        """音声を指定位置から再生"""
        self.stop()

        if self.current_audio_file is None:
            return

        try:
            cmd = ["afplay", self.current_audio_file]
            if offset_seconds > 0:
                cmd.extend(["-t", str(offset_seconds)])
                # afplayの-tは再生時間なのでseekには使えない
                # 代わりにffmpegで指定位置から再抽出する
                self._play_from_offset(offset_seconds)
                return
            self.afplay_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    def _play_from_offset(self, offset_seconds: float) -> None:
        """指定位置から音声を再生（ffmpegでトリミングしてafplayで再生）"""
        if self.ffmpeg_path is None or self.current_audio_file is None:
            return

        trimmed_file = os.path.join(self.temp_dir, "audio_trimmed.m4a")
        try:
            subprocess.run(
                [self.ffmpeg_path, "-ss", str(offset_seconds),
                 "-i", self.current_audio_file, "-acodec", "copy",
                 "-y", trimmed_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return

        if os.path.exists(trimmed_file) and os.path.getsize(trimmed_file) > 0:
            try:
                self.afplay_process = subprocess.Popen(
                    ["afplay", trimmed_file],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                pass

    def stop(self) -> None:
        """音声再生を停止"""
        if self.afplay_process is not None:
            try:
                self.afplay_process.send_signal(signal.SIGTERM)
                self.afplay_process.wait(timeout=2)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    self.afplay_process.kill()
                except ProcessLookupError:
                    pass
            self.afplay_process = None

    def pause(self) -> None:
        """音声を一時停止（SIGSTOPで停止）"""
        if self.afplay_process is not None and self.afplay_process.poll() is None:
            try:
                self.afplay_process.send_signal(signal.SIGSTOP)
            except ProcessLookupError:
                pass

    def resume(self) -> None:
        """音声を再開（SIGCONTで再開）"""
        if self.afplay_process is not None and self.afplay_process.poll() is None:
            try:
                self.afplay_process.send_signal(signal.SIGCONT)
            except ProcessLookupError:
                pass

    def is_available(self) -> bool:
        """音声再生が利用可能かどうか"""
        return self.ffmpeg_path is not None and shutil.which("afplay") is not None

    def cleanup(self) -> None:
        """一時ファイルを削除"""
        self.stop()
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except OSError:
            pass


class Mp4Player:
    """MP4動画プレーヤー (OpenCV + afplay音声)"""

    def __init__(self) -> None:
        self.cap: Optional[cv2.VideoCapture] = None
        self.mp4_files: list[str] = self._scan_mp4_files()
        self.current_index: int = 0
        self.is_playing: bool = False
        self.total_frames: int = 0
        self.current_frame: int = 0
        self.fps: float = 30.0
        self.last_frame: Optional[np.ndarray] = None
        self.play_start_time: float = 0.0
        self.play_start_frame: int = 0
        self.repeat: bool = False
        self.audio: AudioPlayer = AudioPlayer()

        # フォント
        font_path = _find_font()
        if font_path:
            self.font_large: Optional[ImageFont.FreeTypeFont] = ImageFont.truetype(font_path, 16)
            self.font_medium: Optional[ImageFont.FreeTypeFont] = ImageFont.truetype(font_path, 14)
            self.font_small: Optional[ImageFont.FreeTypeFont] = ImageFont.truetype(font_path, 11)
        else:
            self.font_large = None
            self.font_medium = None
            self.font_small = None

        # ウィンドウサイズ
        self.width: int = WINDOW_WIDTH
        self.height: int = WINDOW_HEIGHT

    @staticmethod
    def _scan_mp4_files() -> list[str]:
        """カレントディレクトリのMP4ファイルをソートして取得"""
        return sorted(glob.glob("*.mp4"), key=str.lower)

    def _load_video(self, index: int) -> None:
        """指定インデックスの動画をロード"""
        if not self.mp4_files:
            return

        self.audio.stop()

        if self.cap is not None:
            self.cap.release()

        self.current_index = index
        filepath = self.mp4_files[index]
        self.cap = cv2.VideoCapture(filepath)

        if not self.cap.isOpened():
            self.cap = None
            return

        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.current_frame = 0
        self.is_playing = True
        self.last_frame = None

        # 音声を抽出して再生開始（ブロッキング処理）
        self.audio.extract_audio(filepath)
        self.audio.play()
        # 音声開始後にタイマーを設定（同期精度向上）
        self.play_start_time = time.monotonic()
        self.play_start_frame = 0

    def _read_frame(self) -> Optional[np.ndarray]:
        """フレームを1つ読み込む"""
        if self.cap is None or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        if not ret:
            return None

        self.current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        self.last_frame = frame
        return frame

    def _render_video_area(self, canvas: np.ndarray, frame: Optional[np.ndarray]) -> None:
        """映像エリアを描画"""
        video_area = canvas[:VIDEO_HEIGHT, :, :]

        if frame is None:
            if not self.mp4_files:
                msg = "No MP4 files found in current directory"
            else:
                msg = "Loading..."
            _put_text(video_area, msg, (self.width // 2 - 150, VIDEO_HEIGHT // 2),
                      self.font_large, 16, COLOR_TEXT_DIM)
            return

        h, w = frame.shape[:2]
        scale = min(self.width / w, VIDEO_HEIGHT / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        resized = cv2.resize(frame, (new_w, new_h))

        x_offset = (self.width - new_w) // 2
        y_offset = (VIDEO_HEIGHT - new_h) // 2
        video_area[y_offset:y_offset + new_h, x_offset:x_offset + new_w] = resized

    def _get_button_rects(self) -> list[tuple[str, int, int, int, int]]:
        """ボタンの矩形座標を返す (name, x1, y1, x2, y2) - バー内座標"""
        btn_y = 30
        btn_h = 32
        center_x = self.width // 2
        rects: list[tuple[str, int, int, int, int]] = []
        for name, x_offset, w in BUTTON_DEFS:
            x1 = center_x + x_offset - w // 2
            x2 = x1 + w
            rects.append((name, x1, btn_y, x2, btn_y + btn_h))
        return rects

    def _render_control_bar(self, canvas: np.ndarray) -> None:
        """コントロールバーを描画"""
        bar = canvas[VIDEO_HEIGHT:, :, :]
        bar[:] = COLOR_BAR_BG

        if not self.mp4_files:
            return

        # シークバー
        seek_y = 10
        seek_x_start = 10
        seek_x_end = self.width - 10
        seek_width = seek_x_end - seek_x_start

        cv2.rectangle(bar, (seek_x_start, seek_y), (seek_x_end, seek_y + 6),
                      COLOR_SEEK_BG, -1)

        if self.total_frames > 0:
            progress = self.current_frame / self.total_frames
            progress_x = seek_x_start + int(seek_width * progress)
            cv2.rectangle(bar, (seek_x_start, seek_y), (progress_x, seek_y + 6),
                          COLOR_SEEK_FG, -1)
            cv2.circle(bar, (progress_x, seek_y + 3), 6, COLOR_SEEK_FG, -1)

        # ボタン描画（三角・四角をcv2の図形で描く）
        for name, x1, y1, x2, y2 in self._get_button_rects():
            # ボタン背景
            cv2.rectangle(bar, (x1, y1), (x2, y2), COLOR_BTN_BG, -1)
            cv2.rectangle(bar, (x1, y1), (x2, y2), COLOR_SEEK_BG, 1)

            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            if name == "play":
                color = COLOR_HIGHLIGHT
            elif name == "repeat" and self.repeat:
                color = COLOR_HIGHLIGHT
            else:
                color = COLOR_TEXT

            if name == "play":
                if self.is_playing:
                    # ⏸ 一時停止: 2本の縦線
                    cv2.rectangle(bar, (cx - 6, cy - 7), (cx - 2, cy + 7), color, -1)
                    cv2.rectangle(bar, (cx + 2, cy - 7), (cx + 6, cy + 7), color, -1)
                else:
                    # ▶ 再生: 右向き三角
                    pts = np.array([[cx - 5, cy - 8], [cx - 5, cy + 8], [cx + 7, cy]], np.int32)
                    cv2.fillPoly(bar, [pts], color)
            elif name == "stop":
                # ⏹ 停止: 四角
                cv2.rectangle(bar, (cx - 6, cy - 6), (cx + 6, cy + 6), color, -1)
            elif name == "prev":
                # ⏮ 前へ: 縦線 + 左向き三角
                cv2.rectangle(bar, (cx - 7, cy - 7), (cx - 5, cy + 7), color, -1)
                pts = np.array([[cx + 7, cy - 7], [cx + 7, cy + 7], [cx - 3, cy]], np.int32)
                cv2.fillPoly(bar, [pts], color)
            elif name == "next":
                # ⏭ 次へ: 右向き三角 + 縦線
                pts = np.array([[cx - 7, cy - 7], [cx - 7, cy + 7], [cx + 3, cy]], np.int32)
                cv2.fillPoly(bar, [pts], color)
                cv2.rectangle(bar, (cx + 5, cy - 7), (cx + 7, cy + 7), color, -1)
            elif name == "repeat":
                # 🔁 リピート: 循環矢印を描画
                cv2.ellipse(bar, (cx, cy), (8, 6), 0, 30, 330, color, 2)
                # 矢印の先端
                pts = np.array([
                    [cx + 7, cy - 6], [cx + 7, cy], [cx + 3, cy - 3]
                ], np.int32)
                cv2.fillPoly(bar, [pts], color)

        # 時間表示（ボタンの左側）
        current_sec = self.current_frame / self.fps if self.fps > 0 else 0
        total_sec = self.total_frames / self.fps if self.fps > 0 else 0
        time_text = f"{self._format_time(current_sec)} / {self._format_time(total_sec)}"
        _put_text(bar, time_text, (10, 38), self.font_medium, 14, COLOR_TEXT)

        # ファイル情報（ボタンの右側）
        if self.mp4_files:
            filepath = self.mp4_files[self.current_index]
            display_name = filepath if len(filepath) <= 45 else filepath[:42] + "..."
            info_text = f"[{self.current_index + 1}/{len(self.mp4_files)}] {display_name}"
            _put_text(bar, info_text, (10, 70), self.font_medium, 14, COLOR_TEXT_DIM)

        # 音声状態
        audio_text = "audio: on" if self.audio.is_available() else "audio: off"
        _put_text(bar, audio_text, (self.width - 80, 70), self.font_small, 11, COLOR_TEXT_DIM)

    def _handle_click(self, x: int, y: int) -> None:
        """クリック処理（シークバー + ボタン）"""
        if y < VIDEO_HEIGHT:
            return

        # バー内のローカル座標
        bar_y = y - VIDEO_HEIGHT

        # シークバー判定（バー内y: 5〜20）
        if 5 <= bar_y <= 20 and 10 <= x <= self.width - 10:
            if self.cap is None or self.total_frames == 0:
                return
            progress = (x - 10) / (self.width - 20)
            target_frame = int(progress * self.total_frames)
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            self.current_frame = target_frame
            offset_sec = target_frame / self.fps if self.fps > 0 else 0
            self.audio.stop()
            if self.is_playing:
                self.audio._play_from_offset(offset_sec)
            # 音声開始後にタイマーをリセット（同期精度向上）
            self.play_start_time = time.monotonic()
            self.play_start_frame = target_frame
            if not self.is_playing:
                self._read_frame()
            return

        # ボタン判定
        for name, x1, y1, x2, y2 in self._get_button_rects():
            if x1 <= x <= x2 and y1 <= bar_y <= y2:
                if name == "play":
                    self._toggle_play()
                elif name == "stop":
                    self._stop()
                elif name == "prev":
                    self._prev_video()
                elif name == "next":
                    self._next_video()
                elif name == "repeat":
                    self.repeat = not self.repeat
                return

    def _next_video(self) -> None:
        """次の動画を再生"""
        if not self.mp4_files:
            return
        next_index = (self.current_index + 1) % len(self.mp4_files)
        self._load_video(next_index)

    def _prev_video(self) -> None:
        """前の動画を再生"""
        if not self.mp4_files:
            return
        prev_index = (self.current_index - 1) % len(self.mp4_files)
        self._load_video(prev_index)

    def _stop(self) -> None:
        """停止して先頭に戻る"""
        self.is_playing = False
        self.audio.stop()
        if self.cap is not None and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.current_frame = 0
            self._read_frame()

    def _toggle_play(self) -> None:
        """再生/一時停止の切り替え"""
        self.is_playing = not self.is_playing
        if self.is_playing:
            # 音声を現在位置から再開
            offset_sec = self.current_frame / self.fps if self.fps > 0 else 0
            self.audio.stop()
            self.audio._play_from_offset(offset_sec)
            # 音声開始後にタイマーを設定（同期精度向上）
            self.play_start_time = time.monotonic()
            self.play_start_frame = self.current_frame
        else:
            self.audio.pause()

    @staticmethod
    def _format_time(seconds: float) -> str:
        """秒をMM:SS形式に変換"""
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes:02d}:{secs:02d}"

    def run(self) -> None:
        """メインループ"""
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_NAME, self.width, self.height)

        def on_mouse(event: int, x: int, y: int, flags: int, param: object) -> None:
            if event == cv2.EVENT_LBUTTONDOWN:
                self._handle_click(x, y)

        cv2.setMouseCallback(WINDOW_NAME, on_mouse)

        # ファイル一覧を表示
        if self.mp4_files:
            print(f"\n{'='*50}")
            print(f"MP4 Player - {len(self.mp4_files)} files found")
            print(f"{'='*50}")
            for i, f in enumerate(self.mp4_files):
                print(f"  {i + 1}. {f}")
            print(f"{'='*50}")
            audio_status = "enabled" if self.audio.is_available() else "disabled (ffmpeg not found)"
            print(f"Audio: {audio_status}")
            print("Keys: Space=Play/Pause  N=Next  P=Prev  S=Stop  Q=Quit")
            print(f"{'='*50}\n")

            self._load_video(0)
        else:
            print("MP4ファイルが見つかりません")

        while True:
            canvas = np.full((self.height, self.width, 3), COLOR_BG, dtype=np.uint8)

            frame = None
            if self.is_playing:
                # 時間ベース同期: 経過時間からあるべきフレーム位置を計算
                elapsed = time.monotonic() - self.play_start_time
                target_frame = self.play_start_frame + int(elapsed * self.fps)

                # 現在位置が目標より遅れている場合はフレームをスキップ
                while self.current_frame < target_frame:
                    ret, f = self.cap.read() if self.cap is not None else (False, None)
                    if not ret:
                        # 動画終了 → リピートONなら同じ曲、OFFなら次の動画
                        if self.repeat:
                            self._load_video(self.current_index)
                        else:
                            self._next_video()
                        break
                    self.current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                    self.last_frame = f
                    frame = f

                if frame is None:
                    frame = self.last_frame
            else:
                frame = self.last_frame

            self._render_video_area(canvas, frame)
            self._render_control_bar(canvas)

            cv2.imshow(WINDOW_NAME, canvas)

            # waitKeyは最小限（UIレスポンス用）
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q') or key == 27:
                break
            elif key == ord(' '):
                self._toggle_play()
            elif key == ord('n'):
                self._next_video()
            elif key == ord('p'):
                self._prev_video()
            elif key == ord('s'):
                self._stop()
            elif key == ord('r'):
                self.repeat = not self.repeat
            elif ord('1') <= key <= ord('9'):
                file_index = key - ord('1')
                if file_index < len(self.mp4_files):
                    self._load_video(file_index)

            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break

        # 終了処理
        self.audio.cleanup()
        if self.cap is not None:
            self.cap.release()
        cv2.destroyAllWindows()


def main() -> None:
    player = Mp4Player()
    player.run()


if __name__ == "__main__":
    main()
