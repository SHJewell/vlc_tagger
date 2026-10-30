"""
Media Info - Reads artist, album and length from media files in the
background, using a separate VLC instance so playback isn't affected.

Results arrive through the info_ready signal on the GUI thread and are
cached, so reloading a playlist doesn't read the same files again.
"""
import logging
import queue
import threading
import time

import vlc
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication

PARSE_TIMEOUT_MS = 5000

_STOP = object()


class MediaInfoLoader(QObject):
    # path, {'artist': str, 'album': str, 'length_ms': int (-1 = unknown)}
    info_ready = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self._cache = {}
        self._queued = set()
        self._queue = queue.Queue()
        self._thread = None
        self._lock = threading.Lock()

        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.stop)

    def cached(self, path):
        """Info already read for this path, or None"""
        return self._cache.get(path)

    def request(self, paths):
        """Queue files to read; ones already read or queued are skipped.
        Stream URLs are skipped (reading them would mean connecting)."""
        with self._lock:
            for path in paths:
                if path in self._cache or path in self._queued or '://' in path:
                    continue
                self._queued.add(path)
                self._queue.put(path)
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name='media-info',
                                            daemon=True)
            self._thread.start()

    def cancel_pending(self):
        """Drop everything still queued (e.g. a different playlist loaded)"""
        with self._lock:
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._queued.clear()

    def is_pending(self, path):
        with self._lock:
            return path in self._queued

    def stop(self):
        """Stop the reader thread (called when the app quits)"""
        if self._thread is not None:
            self.cancel_pending()
            self._queue.put(_STOP)
            self._thread.join(timeout=PARSE_TIMEOUT_MS / 1000 + 1)
            self._thread = None

    def _run(self):
        instance = vlc.Instance('--quiet', '--no-video', '--no-audio')
        try:
            while True:
                path = self._queue.get()
                if path is _STOP:
                    return
                with self._lock:
                    if path not in self._queued:     # cancelled meanwhile
                        continue
                info = self._read(instance, path)
                with self._lock:
                    if path not in self._queued:
                        continue
                    self._queued.discard(path)
                    self._cache[path] = info
                self.info_ready.emit(path, info)
        finally:
            instance.release()

    def _read(self, instance, path):
        info = {'artist': '', 'album': '', 'length_ms': -1}
        media = None
        try:
            media = instance.media_new_path(path)
            media.parse_with_options(vlc.MediaParseFlag.local, PARSE_TIMEOUT_MS)
            deadline = time.monotonic() + PARSE_TIMEOUT_MS / 1000 + 0.5
            while media.get_parsed_status() == 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            info['artist'] = media.get_meta(vlc.Meta.Artist) or ''
            info['album'] = media.get_meta(vlc.Meta.Album) or ''
            duration = media.get_duration()
            info['length_ms'] = duration if duration and duration > 0 else -1
        except Exception as e:
            self.logger.warning(f'Could not read media info for {path}: {e}')
        finally:
            if media is not None:
                media.release()
        return info


def format_length(length_ms):
    """3:07, or 1:02:03 for an hour or more; blank when unknown"""
    if length_ms is None or length_ms < 0:
        return ''
    seconds = int(round(length_ms / 1000))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{seconds:02d}'
    return f'{minutes}:{seconds:02d}'
