"""
M3U File - Read and edit M3U playlists in place.

Edits only touch the tracks being added or removed; every other line (titles,
comments, other players' directives, original path spelling) is written back
byte for byte, in the file's original encoding and line endings.
"""
import codecs
import logging
import os
from typing import List, Optional
from urllib.request import url2pathname

logger = logging.getLogger(__name__)

# Lines at the top of the file that describe the playlist, not a track
HEADER_PREFIXES = ('#EXTM3U', '#PLAYLIST', '#EXTENC')


def resolve_playlist_entry(entry, playlist_dir):
    """Turn one m3u track line into a playable local path or stream URL.

    file: links become normal paths (with %20 etc. decoded); other links
    with a scheme (http://, rtsp://, ...) are left alone; anything else is a
    path, relative to the playlist's folder if not absolute.
    """
    if entry.lower().startswith('file:'):
        return os.path.normpath(url2pathname(entry[len('file:'):]))
    if '://' in entry:
        return entry
    if not os.path.isabs(entry):
        entry = os.path.join(playlist_dir, entry)
    return os.path.normpath(entry)


def track_key(path):
    """Comparison key for a track: case/slash-insensitive for local files"""
    if '://' in path:
        return path
    return os.path.normcase(os.path.normpath(path))


class M3UTrack:
    """One track: its path line plus the #EXTINF etc. lines just above it"""

    def __init__(self, lines: List[str], playlist_dir: str):
        self.lines = lines                      # raw lines, path line last
        self.path = resolve_playlist_entry(lines[-1].strip(), playlist_dir)
        self.key = track_key(self.path)

    @property
    def title(self) -> Optional[str]:
        """Title from this track's #EXTINF line, if any"""
        for raw in self.lines[:-1]:
            line = raw.strip()
            if line.startswith('#EXTINF:') and ',' in line:
                return line.split(',', 1)[1].strip() or None
        return None


class M3UFile:
    """An M3U playlist loaded for reading or in-place editing.

    Lines are split on '\\n' only and keep any trailing '\\r', and bytes that
    don't decode are kept via surrogateescape, so unchanged parts round-trip
    exactly.
    """

    def __init__(self, path: str):
        self.path = path
        self.playlist_dir = os.path.dirname(path)
        self.encoding = 'utf-8'
        self.bom = False
        self.cr = '\r'                  # line-ending style for new lines
        self.header: List[str] = []     # #EXTM3U etc. at the top
        self.tracks: List[M3UTrack] = []
        self.trailer: List[str] = []    # lines after the last track

    @classmethod
    def new(cls, path: str) -> 'M3UFile':
        """An empty playlist (UTF-8, Windows line endings)"""
        m3u = cls(path)
        m3u.header = ['#EXTM3U\r']
        m3u.trailer = ['']              # end the file with a newline
        return m3u

    @classmethod
    def read(cls, path: str) -> 'M3UFile':
        """Load a playlist from disk; raises OSError if it can't be read"""
        m3u = cls(path)
        with open(path, 'rb') as f:
            data = f.read()

        if data.startswith(codecs.BOM_UTF8):
            m3u.bom = True
            data = data[len(codecs.BOM_UTF8):]
            m3u.encoding = 'utf-8'
        else:
            try:
                data.decode('utf-8')
                m3u.encoding = 'utf-8'
            except UnicodeDecodeError:
                # Older Windows tools save .m3u in the ANSI code page
                m3u.encoding = 'cp1252'
        text = data.decode(m3u.encoding, errors='surrogateescape')

        if not text:
            return m3u

        lines = text.split('\n')
        m3u.cr = '\r' if any(line.endswith('\r') for line in lines[:-1]) else ''

        i = 0
        while i < len(lines) and lines[i].strip().upper().startswith(HEADER_PREFIXES):
            m3u.header.append(lines[i])
            i += 1

        pending = []
        for raw in lines[i:]:
            line = raw.strip()
            if line and not line.startswith('#'):
                m3u.tracks.append(M3UTrack(pending + [raw], m3u.playlist_dir))
                pending = []
            else:
                pending.append(raw)
        m3u.trailer = pending
        return m3u

    def keys(self) -> List[str]:
        return [t.key for t in self.tracks]

    def contains(self, key: str) -> bool:
        return any(t.key == key for t in self.tracks)

    def remove(self, key: str) -> int:
        """Remove every copy of a track (with its #EXTINF lines); returns count"""
        before = len(self.tracks)
        self.tracks = [t for t in self.tracks if t.key != key]
        return before - len(self.tracks)

    def add(self, path: str):
        """Append a track as an absolute path with an #EXTINF title"""
        if '://' not in path:           # stream URLs are written as-is
            path = os.path.normpath(os.path.abspath(path))
        title = os.path.basename(path)

        if not any(h.strip().upper().startswith('#EXTM3U') for h in self.header):
            self.header.insert(0, '#EXTM3U' + self.cr)

        # Anything after the old last track (except the final newline) stays
        # where it was, ahead of the new track
        before = self.trailer[:-1] if self.trailer and self.trailer[-1] == '' else self.trailer
        new_lines = [f'#EXTINF:-1,{title}' + self.cr, path + self.cr]
        self.tracks.append(M3UTrack(before + new_lines, self.playlist_dir))
        self.trailer = ['']

        # Switch the file to UTF-8 if the new track can't be stored in the
        # file's current encoding (e.g. Japanese characters in a cp1252 file)
        try:
            '\n'.join(new_lines).encode(self.encoding)
        except UnicodeEncodeError:
            logger.warning(f'Converting {self.path} from {self.encoding} to UTF-8 '
                           f'to store {path}')
            self.encoding = 'utf-8'
            self.bom = True             # helps other players detect UTF-8

    def to_bytes(self) -> bytes:
        lines = self.header + [line for t in self.tracks for line in t.lines] + self.trailer
        data = '\n'.join(lines).encode(self.encoding, errors='surrogateescape')
        return (codecs.BOM_UTF8 if self.bom else b'') + data

    def write(self):
        """Save via a temp file so a crash mid-write can't truncate the playlist"""
        tmp_path = f'{self.path}.{os.getpid()}.tmp'  # per process: instances may save at once
        with open(tmp_path, 'wb') as f:
            f.write(self.to_bytes())
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.path)
