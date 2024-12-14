import json
import sys

from pathlib import Path
from queue import Empty, Queue
from threading import Event

import yt_dlp

from PySide6 import QtCore, QtGui, QtWidgets

from uic import loadUi


_PATH = Path(__file__).resolve().parent
ICON = _PATH / "icons" / "yt-dlp-qt.png"
UI_FILE = _PATH / "app.ui"
AUDIO_CODECS = ("aac", "vorbis", "mp3", "opus", "wav")
AUDIO_QUALITIES = (0, 2, 5, 8)
VIDEO_CONTAINERS = ("mp4", "mkv", "3gp", "flv", "webm")
VIDEO_RESOLUTIONS = (2160, 1440, 1080, 720, 480)


class Worker(QtCore.QThread):
    started = QtCore.Signal(str)
    finished = QtCore.Signal(str)
    progress = QtCore.Signal(int)

    def __init__(self, queue: Queue, shutdown: Event):
        super().__init__()
        self.queue = queue
        self.shutdown = shutdown

    def run(self):
        while not self.shutdown.is_set():
            try:
                url, options = self.queue.get(timeout=1.5)
                self._download(url, options)
            except Empty:
                pass

    def _progress(self, info: dict):
        if info["status"] == "downloading":
            try:
                progress = info["downloaded_bytes"] / info["total_bytes"]
                self.progress.emit(int(progress * 100))
            except Exception as error:
                print(error)
        elif info["status"] == "finished":
            self.progress.emit(100)

    def _download(self, url: str, options: dict):
        options["progress_hooks"] = [self._progress]
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", "unknown title")
            self.started.emit(title)
            ydl.download([url])
        self.finished.emit(title)


class YtDlpQt(QtWidgets.QMainWindow):

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        loadUi(UI_FILE, base=self)
        self.setWindowIcon(QtGui.QIcon(str(ICON)))
        self.config = QtCore.QSettings("Whitie", "yt-dlp-qt")
        self.tray = None
        self.last_url = ""
        self.apply_config()
        self.status = self.statusBar()
        self.clipboard = QtWidgets.QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.check_clipboard)
        self.action_quit.triggered.connect(self._quit)
        self.browse.clicked.connect(self.set_download_location)
        self.download.clicked.connect(self.start_download)
        self.audio_only.stateChanged.connect(self._only_audio)
        self.queue = Queue()
        self.shutdown = Event()
        self.worker = Worker(self.queue, self.shutdown)
        self.worker.started.connect(self.download_started)
        self.worker.finished.connect(self.download_finished)
        self.worker.progress.connect(self.download_progress)
        self.worker.start()
        self._only_audio()

    def _quit(self):
        self.dump_config()
        self.hide()
        self.shutdown.set()
        self.worker.wait()
        self.worker.quit()
        app = QtWidgets.QApplication.instance()
        app.quit()

    def _only_audio(self, state: int | None = None):
        self.video_resolution.setDisabled(self.audio_only.isChecked())
        self.video_format.setDisabled(self.audio_only.isChecked())

    def check_clipboard(self):
        if self.monitor_clipboard.isChecked():
            if text := self.clipboard.text().strip():
                if "://" in text and text != self.last_url:
                    self.last_url = text
                    self.url.setText(text)

    def set_download_location(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Choose location",
            self.output_path.text(),
            QtWidgets.QFileDialog.ShowDirsOnly,
        )
        if folder:
            self.output_path.setText(folder)

    def start_download(self):
        url = self.url.text().strip()
        if not url:
            return
        self.queue.put((url, self.get_ytdlp_options()))

    def download_started(self, title: str):
        self.tray.showMessage("YT-DLP-QT", f"Downloading {title}")
        self.status.showMessage(f"Downloading: {title}")
        self.progress.setValue(1)

    def download_finished(self, title: str):
        self.tray.showMessage("YT-DLP-QT", f"Download finished: {title}")
        self.status.showMessage(f"Finished: {title}", 5000)

    def download_progress(self, progress: int):
        self.progress.setValue(progress)

    def get_ytdlp_options(self) -> dict:
        if self.audio_only.isChecked():
            options = self._get_audio_options()
        else:
            options = self._get_video_options()
        if text := self.own_format.text().strip():
            options["format"] = text
        options["paths"] = {"home": self.output_path.text()}
        options["outtmpl"] = {"default": self.output_name.text()}
        return options

    def _get_audio_options(self):
        codec = AUDIO_CODECS[self.audio_format.currentIndex()]
        quality = AUDIO_QUALITIES[self.audio_quality.currentIndex()]
        return {
            "format": f"{codec}/bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": codec,
                    "preferredquality": quality,
                }
            ],
        }

    def _get_video_options(self):
        container = VIDEO_CONTAINERS[self.video_format.currentIndex()]
        resolution = VIDEO_RESOLUTIONS[self.video_resolution.currentIndex()]
        if container == "mp4":
            audio_codec = "m4a"
        else:
            audio_codec = "bestaudio"
        return {
            "format": (
                f"{container}[height={resolution}]+{audio_codec}/"
                f"bestvideo[height<={resolution}]+bestaudio"
            )
        }

    def apply_config(self):
        self.video_resolution.setCurrentIndex(
            int(self.config.value("video/resolution", 2))
        )
        self.video_format.setCurrentIndex(
            int(self.config.value("video/format", 0))
        )
        self.audio_quality.setCurrentIndex(
            int(self.config.value("audio/quality", 0))
        )
        self.audio_format.setCurrentIndex(
            int(self.config.value("audio/format", 0))
        )
        self.audio_only.setChecked(
            _bool(self.config.value("audio/only", False))
        )
        self.output_path.setText(
            self.config.value("output/path", _get_download_location())
        )
        self.output_name.setText(
            self.config.value("output/name", "%(title)s.%(ext)s")
        )
        self.monitor_clipboard.setChecked(
            _bool(self.config.value("clipboard/monitor", False))
        )
        self.own_format.setText(self.config.value("expert/format", ""))
        self.setGeometry(
            int(self.config.value("window/x", 0)),
            int(self.config.value("window/y", 0)),
            int(self.config.value("window/width", 440)),
            int(self.config.value("window/height", 440)),
        )
        self.last_url = self.config.value("url/last", "")

    def dump_config(self):
        self.config.setValue(
            "video/resolution", self.video_resolution.currentIndex()
        )
        self.config.setValue("video/format", self.video_format.currentIndex())
        self.config.setValue(
            "audio/quality", self.audio_quality.currentIndex()
        )
        self.config.setValue("audio/format", self.audio_format.currentIndex())
        self.config.setValue("audio/only", self.audio_only.isChecked())
        self.config.setValue("output/path", self.output_path.text())
        self.config.setValue("output/name", self.output_name.text())
        self.config.setValue(
            "clipboard/monitor", self.monitor_clipboard.isChecked()
        )
        self.config.setValue("expert/format", self.own_format.text())
        self.config.setValue("window/x", self.x())
        self.config.setValue("window/y", self.y())
        self.config.setValue("window/width", self.width())
        self.config.setValue("window/height", self.height())
        self.config.setValue("url/last", self.last_url)
        self.config.sync()


def _bool(value: str) -> bool:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value == "true"


def _get_download_location() -> str:
    path = Path.home() / "Downloads"
    if path.is_dir():
        return str(path)
    return str(Path.home())


def main():
    app = QtWidgets.QApplication([])
    window = YtDlpQt()
    if QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        app.setQuitOnLastWindowClosed(False)
        icon = QtGui.QIcon(str(ICON))
        tray = QtWidgets.QSystemTrayIcon(icon)
        tray.setVisible(True)
        menu = QtWidgets.QMenu()
        action_show = QtGui.QAction("Show Window")
        action_show.triggered.connect(window.show)
        menu.addAction(action_show)
        action_quit = QtGui.QAction("Quit")
        action_quit.triggered.connect(window._quit)
        menu.addAction(action_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(window.show)
        window.tray = tray
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
