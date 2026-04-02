---
name: music-tagger
description: Scan music library, fix ID3 tags (year, artist, title), convert WAV to MP3, create playlists, and copy files for import. Use when working with music files, tagging, playlists, or format conversion.
disable-model-invocation: true
allowed-tools: Bash Read Write Edit Glob Grep
---

# Music Tagger & Playlist Builder

You are helping manage a DJ music library at `~/Music/`.

## Library layout

- **Apple Music library:** `~/Music/Music/Media.localized/Music/`
- **Working folder:** `~/Music/TagMusic/`
- **Import folder:** `~/Music/Musify/Download/` — copy converted files here for re-import into Apple Music

## Available actions

When the user invokes `/music-tagger`, ask which action they'd like (or infer from `$ARGUMENTS`):

### 1. Scan library
- Find all audio files (mp3, wav, m4a, flac, aiff) in the library
- Display current ID3 tags: title, artist, album, year, genre, BPM
- Flag tracks with missing or incorrect metadata

### 2. Fix tags
- Use `mutagen` (Python) to read and write ID3 tags
- Always set the **original release year**, not the remix/reissue year
- Fix artist and title fields when they are missing or contain filenames
- For WAV files, use `mutagen.wave.WAVE` which supports ID3 tags

### 3. Convert WAV to MP3
- Use `ffmpeg` at **320kbps**: `ffmpeg -i input.wav -b:a 320k output.mp3`
- Copy ID3 tags to the new MP3 after conversion
- Copy the converted MP3 to `~/Music/Musify/Download/` so the user can import it into Apple Music
- Update any playlist files to point to the new MP3

### 4. Create playlist
- Scan the library for tracks matching a theme/genre/era
- Search by artist folder names and file names
- Create an `.m3u8` playlist file in `~/Music/` with:
  - `#EXTM3U` header
  - `#PLAYLIST:` name
  - `#EXTINF:` entries with artist and title
  - Absolute file paths to each track
- Verify all file paths exist before adding to the playlist

## Important rules

- Never delete original files unless explicitly asked
- Always use absolute paths in playlists
- When fixing years, use the **original song release year**, not the remix year
- Use `python3` with `mutagen` for all tag operations
- Use `ffmpeg` for all format conversions
