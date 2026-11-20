# NanoCut

An English-language desktop video editor for assembling short videos. Cut on exact frames, arrange footage on two visual tracks, mix audio, and generate captions locally.

**[Download the Windows x64 installer](https://github.com/Interprole/NanoCut/raw/refs/heads/main/downloads/NanoCut-Setup.exe)**

## Start on Windows

1. Run **NanoCut-Setup.exe** and leave **Set up and open NanoCut** selected. First launch needs internet access to install Python, FFmpeg, Node.js and yt-dlp. Setup runs under your Windows account. You can also extract the source ZIP and double-click **NanoCut.cmd**.
2. Select **Import media** or **Try the example project**. The example includes two original motion clips and an audio track.
3. For transcription and background removal, open **Install local AI** in the NanoCut Start menu folder, or run **Install-AI.cmd**. Model weights download on first use. Cached models process your footage on your computer. The CPU backend works on systems with AMD integrated graphics.

On subsequent launches use the **NanoCut** Start menu shortcut. The editor opens in a dedicated Edge or Chrome window. A local Python process handles media, file dialogs and rendering. An installed default browser can open the editor when a supported app-window browser is unavailable.

## Edit a sequence

| Action | Control |
| --- | --- |
| Add media | The first import builds a sequence. For later imports, drag a media-pool item to a track or click its **+** to append. |
| Cut and move | Select a block, click the ruler and press **S**. Drag the block to change its time or track. Drag either edge to trim. |
| Make clips meet | Turn on **Snap**. Edges align with the playhead and nearby clip boundaries. Hold **Alt** to bypass snapping. **Close track gaps** packs the selected track from frame zero. |
| Overlay or align | Place a clip on **V2**, set its size in the inspector and drag its image in the monitor. The center and outer edges snap to the canvas. Use the X, Y and size fields for precise placement. |
| Walk frame by frame | **Left / Right** advances one project frame. Hold **Shift** for ten. Zoom in until the ruler labels individual frames and the grid shows their boundaries. The last two timecode digits count frames. |
| Change speed | The monitor speed selector affects playback. **Clip speed** in the inspector changes the edit, clip duration, captions and exported audio/video. |
| Mix sound | Video tracks carry their source sound. Use **A1** for music or voiceover, adjust volume per clip, or set it to zero. A video placed on A1 contributes its audio. |
| Undo and duplicate | **Ctrl Z**, **Ctrl Shift Z**, **Ctrl D**, and **Delete**. On macOS, Command also works. |
| Save | **Ctrl S** saves a `.nano` project. **File → Recover last session** opens the most recent recovery copy. Projects reference source files and prompt to locate missing media. |

Two clips can overlap on the same visual track. The later-starting clip appears on top, and both clips contribute audio. V2 appears above V1. A blank gap renders black. The sequence ends at the last included clip edge.

## Captions and foreground extraction

Select a clip with audio and choose **Transcribe with Whisper**. Choose **tiny**, **base**, **small**, **medium**, **large-v3** or **turbo**. The estimate changes as you select models. The first estimate uses a rough CPU range. Later estimates use the last measured recognition time for the same model on this installation. Model download and initialization take additional time. **Change model** during recognition cancels the current pass and opens the model selector again.

Choose **Studio**, **Headline**, **Cinema**, **Boxed** or **Signal**. **Edit captions** accepts one timed cue per line. Times refer to the original source, so captions follow trims, splits and speed changes. The video export burns in the selected style. **Export → SRT** writes editable subtitle text and timings.

**Remove background** processes the selected interval with local rembg / U²-Net. It creates a transparent VP9 WebM for motion or PNG for stills, keeps the original in the pool, and replaces the timeline clip with the foreground. Video processing uses the project frame rate and a maximum long edge of 1280 pixels. Put background footage on V1 and the foreground on V2.

## Downloads, conversion and export

**↓** beside **Import media** opens the yt-dlp downloader. Paste a YouTube or TikTok video URL, enter start and end times in seconds or HH:MM:SS, and choose MP4 or MP3. The file picker selects the destination folder and filename. The placement selector sends the result to the pool, sequence end, playhead, overlay track or preview-only audio track. **Full source transfer** downloads the entire media file and trims locally when a source cannot serve a partial download. Availability also depends on the source site's access restrictions. Rerun setup to update the downloader.

To convert a single file, start an empty project, import the file and choose **Export**. The same dialog renders a complete edit. Video formats include MP4, MOV, MKV and WebM. Audio formats include MP3, WAV, M4A and FLAC. Choose a landscape, square, portrait or 4:5 project canvas and set the timeline frame rate in **Project settings**. Export resolution and frame rate can be set independently. An export with a different aspect ratio fits the composition inside the new canvas.

## TikTok

**TikTok studio** can import audio from a TikTok **video** link or an existing local file as a preview-only guide. Line up cuts against the guide, export, and add the official sound inside TikTok. A TikTok video may contain voiceover and other sounds in addition to the song. The web uploader is available from the same menu.

For personal developer-app integration, register a desktop TikTok application with Login Kit and Content Posting API, obtain access to `video.upload`, and register the redirect URI `http://127.0.0.1:53682/callback/`. Set `TIKTOK_CLIENT_KEY` and `TIKTOK_CLIENT_SECRET` in the local environment before launching NanoCut. An alternative port can be set with `TIKTOK_REDIRECT_PORT` and must match the registered URI. Keep your own personal app credentials on your machine.

With both variables present, choose **Authorize and send an exported MP4 to my TikTok inbox** and select the export. The browser handles sign-in using PKCE. NanoCut transfers the selected file, checks processing status and discards the session token. Finish editing, choose music and publish in TikTok. The distributed installer ships without TikTok developer credentials. [TikTok desktop login](https://developers.tiktok.com/doc/login-kit-desktop/) · [Upload to TikTok](https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content/)

## Linux, macOS and development

Use Python 3.11–3.13 with Tk, FFmpeg 7+ with ffprobe, libass, libx264 and libvpx, and a desktop browser. yt-dlp's YouTube extractor can also use a supported Node.js or Deno runtime. On Linux install your distribution's Tk package if needed.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python NanoCut.py
```

Install optional AI dependencies with `python -m pip install -r requirements-ai.txt`. Run `python NanoCut.py --serve` to print the private local URL for an existing browser. The server binds to loopback and uses a fresh random session URL on each launch.

```sh
python -m unittest discover -s tests -v
python -m pip install playwright
python -m playwright install chromium
python tests/smoke_ui.py
```

The regression tests render media and inspect frame colors, audio samples, duration, captions and project round trips. The UI smoke test drives editing and export, substituting temporary destinations for native file pickers. Set `NANOCUT_TEST_BROWSER` to test with an existing Chromium executable.

To rebuild the Windows bootstrap installer, install NSIS 3, create the `dist` directory and run `makensis packaging/installer.nsi` from the repository root. The installer contains NanoCut and the setup scripts. Runtime dependencies download directly from their distributors at first launch.

The private Windows runtime lives in `%LOCALAPPDATA%\NanoCutRuntime`. Cache, browser profile and recovery data live under `~/.nanocut`. Speech and segmentation weights use their respective upstream model caches. Removing the application preserves projects, source footage and the downloaded runtime.

