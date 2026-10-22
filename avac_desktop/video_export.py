"""Backpressured, asynchronous MP4 encoding using the bundled Qt backend."""
from pathlib import Path
import os
import uuid

from PySide6.QtCore import QObject, QSize, QTimer, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import (QMediaCaptureSession, QMediaFormat, QMediaRecorder,
                                  QVideoFrame, QVideoFrameFormat, QVideoFrameInput)


class VideoExport(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, path, size, fps, count, render, parent=None):
        super().__init__(parent)
        self.path = Path(path).with_suffix(".mp4")
        self.temporary = self.path.with_name(f".{self.path.stem}-{uuid.uuid4().hex[:8]}.partial.mp4")
        self.size = QSize(max(2, size.width()//2*2), max(2, size.height()//2*2))
        self.fps, self.count, self.render = fps, count, render
        self.index, self.pending, self.image, self.ending = 0, False, None, False
        self.done, self.cancelled = False, False
        self.session = QMediaCaptureSession(self)
        self.recorder = QMediaRecorder(self)
        self.session.setRecorder(self.recorder)
        format = QVideoFrameFormat(self.size, QVideoFrameFormat.PixelFormat.Format_RGBA8888)
        format.setStreamFrameRate(fps)
        self.input = QVideoFrameInput(format, self)
        self.session.setVideoFrameInput(self.input)
        media = QMediaFormat(QMediaFormat.FileFormat.MPEG4)
        supported = media.supportedVideoCodecs(QMediaFormat.ConversionMode.Encode)
        codec = QMediaFormat.VideoCodec.H264 if QMediaFormat.VideoCodec.H264 in supported else QMediaFormat.VideoCodec.MPEG4
        media.setVideoCodec(codec)
        self.recorder.setMediaFormat(media)
        self.recorder.setVideoResolution(self.size)
        self.recorder.setVideoFrameRate(fps)
        self.recorder.setQuality(QMediaRecorder.Quality.HighQuality)
        self.recorder.setAutoStop(True)
        self.recorder.setOutputLocation(QUrl.fromLocalFile(str(self.temporary.resolve())))
        self.input.readyToSendVideoFrame.connect(self._request)
        self.recorder.errorOccurred.connect(lambda *_: self._fail(self.recorder.errorString()))
        self.recorder.recorderStateChanged.connect(self._state)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.setInterval(60000)
        self.deadline.timeout.connect(lambda: self._fail("MP4 encoding stopped responding."))

    def start(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.deadline.start()
        self.recorder.record()

    def _request(self):
        if self.done or self.pending or self.ending:
            return
        if self.image is not None:
            self._send(self.image)
        elif self.index < self.count:
            self.pending = True
            self.deadline.start()
            self.render(self.index, self._send)
        else:
            self.ending = True
            if not self.input.sendVideoFrame(QVideoFrame()):
                self.ending = False

    def _send(self, image):
        self.pending = False
        if self.done:
            return
        image = image.scaled(self.size).convertToFormat(QImage.Format_RGBA8888)
        frame = QVideoFrame(image)
        frame.setStartTime(round(self.index*1_000_000/self.fps))
        frame.setEndTime(round((self.index+1)*1_000_000/self.fps))
        self.pending = True
        accepted = self.input.sendVideoFrame(frame)
        self.pending = False
        if accepted:
            self.image = None
            self.index += 1
            self.progress.emit(self.index, self.count)
            self.deadline.start()
            QTimer.singleShot(0, self._request)
        else:
            self.image = image

    def _state(self, state):
        if state != QMediaRecorder.RecorderState.StoppedState or self.done:
            return
        if not self.ending or self.index != self.count or not self.temporary.is_file() or self.temporary.stat().st_size == 0:
            self._fail("The MP4 encoder did not produce a complete video.")
            return
        self.done = True
        self.deadline.stop()
        try:
            os.replace(self.temporary, self.path)
        except OSError as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(self.path)

    def cancel(self):
        self._fail("MP4 export cancelled.")

    def _fail(self, message):
        if self.done:
            return
        self.done = True
        self.deadline.stop()
        self.recorder.stop()
        # Keep an incomplete file explicitly named .partial.mp4 for diagnosis;
        # never replace an existing chosen output on failure or cancellation.
        self.failed.emit(message)
