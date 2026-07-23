"""Read-only, bounded waveform previews for session-private PCM WAV files.

The game-specific audio panel first resolves a playable sound through its
existing private session/cache route.  This module never decodes a game
container and never creates, replaces, or removes a file: it opens that WAV
read-only, samples a bounded number of PCM16 frames, and paints only normalized
min/max envelope points.  Long soundtrack tracks therefore cost roughly the
same to draw as short menu sounds.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import os
from pathlib import Path
import stat
import sys
from threading import Event
from typing import Callable
import wave

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QSizePolicy, QWidget


class WaveformError(ValueError):
    """A waveform problem that can be explained directly to a modder."""


class WaveformCancelled(RuntimeError):
    """Internal cooperative-cancellation signal; never shown as an error."""


class WaveformRequest:
    """Thread-safe cancellation token for one explicit waveform request."""

    def __init__(self) -> None:
        self._cancelled = Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def check(self) -> None:
        if self.cancelled:
            raise WaveformCancelled("The waveform request was cancelled")


@dataclass(frozen=True, slots=True)
class WaveformEnvelope:
    """Small, retail-free display model derived from one private PCM WAV."""

    sample_rate: int
    frame_count: int
    channel_peaks: tuple[tuple[tuple[float, float], ...], ...]
    sampled_frame_count: int

    def __post_init__(self) -> None:
        if self.sample_rate <= 0 or self.frame_count < 0:
            raise ValueError("Invalid waveform timing")
        if not self.channel_peaks:
            raise ValueError("A waveform needs at least one channel")
        point_count = len(self.channel_peaks[0])
        if point_count <= 0 or any(
            len(channel) != point_count for channel in self.channel_peaks
        ):
            raise ValueError("Waveform channels must have matching points")
        if self.sampled_frame_count < 0:
            raise ValueError("Invalid sampled-frame count")

    @property
    def channel_count(self) -> int:
        return len(self.channel_peaks)

    @property
    def point_count(self) -> int:
        return len(self.channel_peaks[0])

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate


def _sample_window_starts(
    start: int,
    stop: int,
    budget: int,
) -> tuple[tuple[int, int], ...]:
    """Choose bounded, evenly distributed windows inside one display bucket."""

    span = max(0, stop - start)
    if span <= budget:
        return ((start, span),) if span else ()
    window_count = 4
    window_frames = max(1, budget // window_count)
    available = span - window_frames
    return tuple(
        (
            start + round(available * index / (window_count - 1)),
            window_frames,
        )
        for index in range(window_count)
    )


def read_pcm16_waveform(
    path: Path,
    *,
    max_points: int = 640,
    frames_per_point: int = 1024,
    cancelled: Callable[[], bool] | None = None,
) -> WaveformEnvelope:
    """Sample a regular, non-link PCM16 WAV without writing or reading it whole.

    At most ``max_points * frames_per_point`` frames are decoded into Python
    arrays. Long buckets use four evenly distributed windows, while short
    sounds are sampled completely. Only normalized min/max points survive.
    """

    if not 16 <= max_points <= 4096:
        raise ValueError("max_points must be between 16 and 4096")
    if not 64 <= frames_per_point <= 16_384:
        raise ValueError("frames_per_point must be between 64 and 16384")
    cancel_check = cancelled or (lambda: False)

    supplied = path.expanduser()
    try:
        supplied_stat = supplied.lstat()
    except OSError as exc:
        raise WaveformError("The private WAV preview is no longer available") from exc
    if not stat.S_ISREG(supplied_stat.st_mode) or stat.S_ISLNK(supplied_stat.st_mode):
        raise WaveformError("The private WAV preview is not a regular, non-link file")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(supplied, flags)
    except OSError as exc:
        raise WaveformError("The private WAV preview could not be opened safely") from exc

    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise WaveformError("The private WAV preview is not a regular file")
        if (opened.st_dev, opened.st_ino) != (
            supplied_stat.st_dev,
            supplied_stat.st_ino,
        ):
            raise WaveformError(
                "The private WAV preview changed before its read-only open"
            )
        if cancel_check():
            raise WaveformCancelled("The waveform request was cancelled")
        with os.fdopen(descriptor, "rb", closefd=True) as source:
            descriptor = -1
            try:
                with wave.open(source, "rb") as reader:
                    channels = reader.getnchannels()
                    sample_width = reader.getsampwidth()
                    sample_rate = reader.getframerate()
                    frame_count = reader.getnframes()
                    compression = reader.getcomptype()
                    if not 1 <= channels <= 8:
                        raise WaveformError(
                            f"The verified WAV has an unsupported {channels}-channel layout"
                        )
                    if sample_width != 2 or compression != "NONE":
                        raise WaveformError(
                            "Waveform preview needs the verified PCM16 WAV"
                        )
                    if sample_rate <= 0 or frame_count <= 0:
                        raise WaveformError("The verified WAV contains no audio frames")

                    point_count = min(max_points, frame_count)
                    peaks: list[list[tuple[float, float]]] = [
                        [] for _ in range(channels)
                    ]
                    sampled_frames = 0
                    for point_index in range(point_count):
                        if cancel_check():
                            raise WaveformCancelled(
                                "The waveform request was cancelled"
                            )
                        bucket_start = frame_count * point_index // point_count
                        bucket_stop = frame_count * (point_index + 1) // point_count
                        minimums = [32767] * channels
                        maximums = [-32768] * channels
                        found = False
                        for window_start, window_frames in _sample_window_starts(
                            bucket_start,
                            bucket_stop,
                            frames_per_point,
                        ):
                            reader.setpos(window_start)
                            payload = reader.readframes(window_frames)
                            samples = array("h")
                            samples.frombytes(payload)
                            if sys.byteorder != "little":
                                samples.byteswap()
                            complete_samples = len(samples) - len(samples) % channels
                            sampled_frames += complete_samples // channels
                            for sample_index in range(complete_samples):
                                channel = sample_index % channels
                                value = samples[sample_index]
                                if value < minimums[channel]:
                                    minimums[channel] = value
                                if value > maximums[channel]:
                                    maximums[channel] = value
                            found = found or complete_samples > 0
                        if not found:
                            raise WaveformError(
                                "The verified WAV ended before its declared frame count"
                            )
                        for channel in range(channels):
                            low = minimums[channel] / 32768.0
                            high = maximums[channel] / 32767.0
                            peaks[channel].append(
                                (
                                    max(-1.0, min(1.0, low)),
                                    max(-1.0, min(1.0, high)),
                                )
                            )
            except wave.Error as exc:
                raise WaveformError(
                    "The private audio preview is not a readable PCM WAV"
                ) from exc

            after = os.fstat(source.fileno())
            if (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ) != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
            ):
                raise WaveformError(
                    "The private WAV changed while its waveform was being read"
                )
    except (OSError, EOFError) as exc:
        raise WaveformError("The private WAV could not be read completely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    return WaveformEnvelope(
        sample_rate=sample_rate,
        frame_count=frame_count,
        channel_peaks=tuple(tuple(channel) for channel in peaks),
        sampled_frame_count=sampled_frames,
    )


def _duration_text(seconds: float) -> str:
    whole = max(0, int(round(seconds)))
    minutes, remainder = divmod(whole, 60)
    return f"{minutes}:{remainder:02d}"


class AudioWaveformPreview(QWidget):
    """Compact Qt waveform canvas with explicit empty/loading/error states."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("audioWaveformPreview")
        self.setAccessibleName("Selected sound waveform")
        self.setMinimumHeight(104)
        self.setMaximumHeight(132)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._state = "empty"
        self._message = "Choose a playable sound, then load its waveform."
        self._envelope: WaveformEnvelope | None = None
        self.setToolTip(self._message)

    @property
    def state(self) -> str:
        return self._state

    @property
    def envelope(self) -> WaveformEnvelope | None:
        return self._envelope

    def set_empty(self, message: str) -> None:
        self._set_state("empty", message)

    def set_loading(self, message: str) -> None:
        self._set_state("loading", message)

    def set_unavailable(self, message: str) -> None:
        self._set_state("unavailable", message)

    def set_error(self, message: str) -> None:
        self._set_state("error", message)

    def set_envelope(self, envelope: WaveformEnvelope) -> None:
        self._state = "ready"
        self._envelope = envelope
        channel_text = (
            "mono"
            if envelope.channel_count == 1
            else "stereo"
            if envelope.channel_count == 2
            else f"{envelope.channel_count} channels"
        )
        self._message = (
            f"Waveform ready · {channel_text} · {envelope.sample_rate:,} Hz · "
            f"{_duration_text(envelope.duration_seconds)}. This is a read-only view "
            "of the private current WAV; it does not play automatically."
        )
        self.setAccessibleDescription(self._message)
        self.setToolTip(self._message)
        self.update()

    def _set_state(self, state: str, message: str) -> None:
        self._state = state
        self._message = message
        self._envelope = None
        self.setAccessibleDescription(message)
        self.setToolTip(message)
        self.update()

    def paintEvent(self, event: object) -> None:
        super().paintEvent(event)  # type: ignore[arg-type]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        bounds = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        painter.fillRect(bounds, QColor("#09111d"))
        border = {
            "ready": QColor("#2f6f91"),
            "loading": QColor("#f2bd5a"),
            "error": QColor("#ff6b7a"),
            "unavailable": QColor("#48576d"),
        }.get(self._state, QColor("#30415a"))
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(bounds, 7.0, 7.0)

        envelope = self._envelope
        if self._state != "ready" or envelope is None:
            painter.setPen(
                QColor("#ff9aa7")
                if self._state == "error"
                else QColor("#aebbd0")
            )
            prefix = {
                "loading": "◌  Preparing waveform\n",
                "error": "!  Waveform unavailable\n",
                "unavailable": "—  No waveform for this row\n",
            }.get(self._state, "▥  Waveform not loaded\n")
            painter.drawText(
                bounds.adjusted(14.0, 10.0, -14.0, -10.0),
                int(Qt.AlignCenter | Qt.TextWordWrap),
                prefix + self._message,
            )
            painter.end()
            return

        channel_text = (
            "MONO"
            if envelope.channel_count == 1
            else "STEREO"
            if envelope.channel_count == 2
            else f"{envelope.channel_count} CHANNELS"
        )
        painter.setPen(QColor("#aebbd0"))
        painter.drawText(
            bounds.adjusted(10.0, 5.0, -10.0, -5.0),
            int(Qt.AlignTop | Qt.AlignLeft),
            f"{channel_text}  •  {envelope.sample_rate / 1000:g} kHz  •  "
            f"{_duration_text(envelope.duration_seconds)}",
        )
        plot = bounds.adjusted(8.0, 24.0, -8.0, -7.0)
        channel_height = plot.height() / envelope.channel_count
        painter.setPen(QPen(QColor("#243650"), 1.0))
        for channel_index in range(envelope.channel_count):
            middle = plot.top() + channel_height * (channel_index + 0.5)
            painter.drawLine(plot.left(), middle, plot.right(), middle)

        painter.setPen(QPen(QColor("#64d8ff"), 1.15))
        x_scale = plot.width() / max(1, envelope.point_count - 1)
        amplitude = max(2.0, channel_height * 0.44)
        for channel_index, peaks in enumerate(envelope.channel_peaks):
            middle = plot.top() + channel_height * (channel_index + 0.5)
            upper = QPainterPath()
            lower = QPainterPath()
            for point_index, (minimum, maximum) in enumerate(peaks):
                x = plot.left() + point_index * x_scale
                upper_y = middle - maximum * amplitude
                lower_y = middle - minimum * amplitude
                if point_index == 0:
                    upper.moveTo(x, upper_y)
                    lower.moveTo(x, lower_y)
                else:
                    upper.lineTo(x, upper_y)
                    lower.lineTo(x, lower_y)
            painter.drawPath(upper)
            painter.drawPath(lower)
        painter.end()


__all__ = [
    "AudioWaveformPreview",
    "WaveformCancelled",
    "WaveformEnvelope",
    "WaveformError",
    "WaveformRequest",
    "read_pcm16_waveform",
]
