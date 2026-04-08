#!/usr/bin/env python3
"""カレントディレクトリのMP4ファイルを順次再生するプレーヤー"""

import glob
import tkinter as tk
from tkinter import ttk
from typing import Optional

import cv2
from PIL import Image, ImageTk


class Mp4Player:
    """MP4動画プレーヤー"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MP4 Player")
        self.root.configure(bg="#1e1e1e")

        # 動画関連
        self.cap: Optional[cv2.VideoCapture] = None
        self.mp4_files: list[str] = self._scan_mp4_files()
        self.current_index: int = 0
        self.is_playing: bool = False
        self.total_frames: int = 0
        self.current_frame: int = 0
        self.fps: float = 30.0
        self.seeking: bool = False
        self.photo: Optional[ImageTk.PhotoImage] = None

        # UI構築
        self._build_ui()

        # ファイルがあれば最初の動画をロード
        if self.mp4_files:
            self._load_video(0)
        else:
            self.info_label.config(text="MP4ファイルが見つかりません")

        # ウィンドウ閉じる処理
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    @staticmethod
    def _scan_mp4_files() -> list[str]:
        """カレントディレクトリのMP4ファイルをソートして取得"""
        return sorted(glob.glob("*.mp4"), key=str.lower)

    def _build_ui(self) -> None:
        """UI構築"""
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Dark.TFrame", background="#1e1e1e")
        style.configure("Dark.TButton", padding=6, font=("Helvetica", 12))
        style.configure("Dark.TLabel", background="#1e1e1e", foreground="white",
                         font=("Helvetica", 11))
        style.configure("File.TLabel", background="#2a2a2a", foreground="white",
                         font=("Helvetica", 10))
        style.configure("Active.TLabel", background="#2a2a2a", foreground="#4fc3f7",
                         font=("Helvetica", 10, "bold"))

        # メインフレーム
        main_frame = ttk.Frame(self.root, style="Dark.TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 左: ファイル一覧
        list_frame = ttk.Frame(main_frame, style="Dark.TFrame", width=200)
        list_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(5, 0), pady=5)
        list_frame.pack_propagate(False)

        list_title = ttk.Label(list_frame, text="ファイル一覧", style="Dark.TLabel")
        list_title.pack(pady=(5, 2))

        # スクロール可能なファイルリスト
        list_canvas = tk.Canvas(list_frame, bg="#2a2a2a", highlightthickness=0, width=190)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=list_canvas.yview)
        self.file_list_frame = ttk.Frame(list_canvas, style="Dark.TFrame")

        self.file_list_frame.bind(
            "<Configure>",
            lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all"))
        )
        list_canvas.create_window((0, 0), window=self.file_list_frame, anchor="nw")
        list_canvas.configure(yscrollcommand=scrollbar.set)

        list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.file_labels: list[ttk.Label] = []
        for i, f in enumerate(self.mp4_files):
            label = ttk.Label(self.file_list_frame, text=f, style="File.TLabel",
                              cursor="hand2", wraplength=180)
            label.pack(fill=tk.X, padx=2, pady=1)
            label.bind("<Button-1>", lambda e, idx=i: self._on_file_click(idx))
            self.file_labels.append(label)

        # 右: 映像 + コントロール
        right_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 映像表示エリア
        self.canvas = tk.Canvas(right_frame, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 情報ラベル
        self.info_label = ttk.Label(right_frame, text="", style="Dark.TLabel")
        self.info_label.pack(pady=(5, 0))

        # シークバー
        seek_frame = ttk.Frame(right_frame, style="Dark.TFrame")
        seek_frame.pack(fill=tk.X, pady=5)

        self.time_label = ttk.Label(seek_frame, text="00:00 / 00:00", style="Dark.TLabel")
        self.time_label.pack(side=tk.RIGHT, padx=5)

        self.seek_var = tk.DoubleVar(value=0)
        self.seek_bar = ttk.Scale(seek_frame, from_=0, to=100, orient=tk.HORIZONTAL,
                                   variable=self.seek_var, command=self._on_seek)
        self.seek_bar.pack(fill=tk.X, padx=5)
        self.seek_bar.bind("<ButtonPress-1>", self._on_seek_start)
        self.seek_bar.bind("<ButtonRelease-1>", self._on_seek_end)

        # コントロールボタン
        ctrl_frame = ttk.Frame(right_frame, style="Dark.TFrame")
        ctrl_frame.pack(pady=(0, 10))

        btn_prev = ttk.Button(ctrl_frame, text="⏮ 前へ", command=self._prev_video,
                               style="Dark.TButton")
        btn_prev.pack(side=tk.LEFT, padx=5)

        self.btn_play = ttk.Button(ctrl_frame, text="▶ 再生", command=self._toggle_play,
                                    style="Dark.TButton")
        self.btn_play.pack(side=tk.LEFT, padx=5)

        btn_stop = ttk.Button(ctrl_frame, text="⏹ 停止", command=self._stop,
                               style="Dark.TButton")
        btn_stop.pack(side=tk.LEFT, padx=5)

        btn_next = ttk.Button(ctrl_frame, text="⏭ 次へ", command=self._next_video,
                               style="Dark.TButton")
        btn_next.pack(side=tk.LEFT, padx=5)

        # キーバインド
        self.root.bind("<space>", lambda e: self._toggle_play())
        self.root.bind("<Right>", lambda e: self._next_video())
        self.root.bind("<Left>", lambda e: self._prev_video())
        self.root.bind("<Escape>", lambda e: self._on_close())

    def _load_video(self, index: int) -> None:
        """指定インデックスの動画をロード"""
        if not self.mp4_files:
            return

        self._stop()

        if self.cap is not None:
            self.cap.release()

        self.current_index = index
        filepath = self.mp4_files[index]
        self.cap = cv2.VideoCapture(filepath)

        if not self.cap.isOpened():
            self.info_label.config(text=f"読み込み失敗: {filepath}")
            return

        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.current_frame = 0

        # ファイル一覧のハイライト更新
        for i, label in enumerate(self.file_labels):
            if i == index:
                label.configure(style="Active.TLabel")
            else:
                label.configure(style="File.TLabel")

        # 情報更新
        total_sec = self.total_frames / self.fps
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.info_label.config(
            text=f"[{index + 1}/{len(self.mp4_files)}] {filepath}  "
                 f"({width}x{height}, {self.fps:.1f}fps, {total_sec:.1f}秒)"
        )

        # 最初のフレームを表示して自動再生
        self._show_frame()
        self._toggle_play()

    def _show_frame(self) -> None:
        """現在のフレームを表示"""
        if self.cap is None or not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if not ret:
            # 動画終了 → 次の動画へ
            if self.is_playing:
                self.is_playing = False
                self.root.after(100, self._next_video)
            return

        self.current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))

        # フレームをキャンバスサイズにリサイズ
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10:
            canvas_w, canvas_h = 640, 480

        h, w = frame.shape[:2]
        scale = min(canvas_w / w, canvas_h / h)
        new_w = int(w * scale)
        new_h = int(h * scale)

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_resized = cv2.resize(frame_rgb, (new_w, new_h))

        image = Image.fromarray(frame_resized)
        self.photo = ImageTk.PhotoImage(image=image)

        self.canvas.delete("all")
        x_offset = (canvas_w - new_w) // 2
        y_offset = (canvas_h - new_h) // 2
        self.canvas.create_image(x_offset, y_offset, anchor=tk.NW, image=self.photo)

        # シークバー・時間ラベル更新
        if not self.seeking and self.total_frames > 0:
            progress = (self.current_frame / self.total_frames) * 100
            self.seek_var.set(progress)

        current_sec = self.current_frame / self.fps
        total_sec = self.total_frames / self.fps
        self.time_label.config(
            text=f"{self._format_time(current_sec)} / {self._format_time(total_sec)}"
        )

    def _update(self) -> None:
        """再生ループ"""
        if not self.is_playing:
            return

        self._show_frame()

        if self.is_playing:
            delay = max(1, int(1000 / self.fps))
            self.root.after(delay, self._update)

    def _toggle_play(self) -> None:
        """再生/一時停止の切り替え"""
        if self.cap is None:
            return

        self.is_playing = not self.is_playing
        if self.is_playing:
            self.btn_play.config(text="⏸ 一時停止")
            self._update()
        else:
            self.btn_play.config(text="▶ 再生")

    def _stop(self) -> None:
        """停止して先頭に戻る"""
        self.is_playing = False
        self.btn_play.config(text="▶ 再生")
        if self.cap is not None and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.current_frame = 0
            self._show_frame()

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

    def _on_file_click(self, index: int) -> None:
        """ファイル一覧クリック"""
        self._load_video(index)

    def _on_seek_start(self, event: tk.Event) -> None:
        """シークバードラッグ開始"""
        self.seeking = True

    def _on_seek_end(self, event: tk.Event) -> None:
        """シークバードラッグ終了"""
        self.seeking = False
        self._apply_seek()

    def _on_seek(self, value: str) -> None:
        """シークバー変更"""
        if self.seeking:
            self._apply_seek()

    def _apply_seek(self) -> None:
        """シーク位置を適用"""
        if self.cap is None or self.total_frames == 0:
            return
        target_frame = int((self.seek_var.get() / 100) * self.total_frames)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        self.current_frame = target_frame
        if not self.is_playing:
            self._show_frame()

    @staticmethod
    def _format_time(seconds: float) -> str:
        """秒をMM:SS形式に変換"""
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes:02d}:{secs:02d}"

    def _on_close(self) -> None:
        """終了処理"""
        self.is_playing = False
        if self.cap is not None:
            self.cap.release()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    root.geometry("960x600")
    root.minsize(640, 400)
    Mp4Player(root)
    root.mainloop()


if __name__ == "__main__":
    main()
