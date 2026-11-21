# NanoCut

An English-language desktop video editor for assembling short videos. Cut on exact frames, arrange footage on any number of visual tracks, mix audio, and generate captions locally.

**[Download NanoCut 1.1.0.1 for Windows x64](https://github.com/Interprole/NanoCut/releases/download/v1.1.0.1/NanoCut-1.1.0.1-Setup.exe)**

## Start on Windows

1. Run **NanoCut-1.1.0.1-Setup.exe**. The graphical installer checks existing components, shows progress, and downloads missing dependencies. Choose the Whisper models and background removal on the components page. All six Whisper models and background removal are selected by default.
2. Open **NanoCut** from Start. The Windows application uses a C# Windows Forms window with embedded WebView2 and a local Python media engine. Choose **Try the example project** to explore the timeline.
3. To add models later, choose **File → Models and tools**. Existing projects use the same file format as 1.0.

## Edit a sequence

| Action | Control |
| --- | --- |
| Add media | The first import builds a sequence. For later imports, drag a media-pool item to a track or click its **+** to append. |
| Cut and move | Select a block, click the ruler and press **S**. Drag the block to change its time or track. Drag either edge to trim. |
| Make clips meet | Turn on **Snap**. Edges align with the playhead and nearby clip boundaries. Hold **Alt** to bypass snapping. **Close track gaps** packs the selected track from frame zero. |
| Overlay or align | Place a clip on **V2**, set its size in the inspector and drag its image in the monitor. The center and outer edges snap to the canvas. Use the X, Y and size fields for precise placement. |
| Walk frame by frame | **Left / Right** advances one project frame. Hold **Shift** for ten. Zoom in until the ruler labels individual frames and the grid shows their boundaries. The last two timecode digits count frames. |
| Change speed | The monitor speed selector affects playback. **Clip speed** in the inspector changes the edit, clip duration, captions and exported audio/video. |
| Mix sound | New video clips with sound create linked picture and waveform audio clips. Use **A1** for music or voiceover, adjust volume per clip, or set it to zero. A video placed on A1 contributes its audio. |
| Undo and duplicate | **Ctrl Z**, **Ctrl Shift Z**, **Ctrl D**, and **Delete**. On macOS, Command also works. |
| Save | **Ctrl S** saves a `.nano` project. **File → Recover last session** opens the most recent recovery copy. Projects reference source files and prompt to locate missing media. |

Two clips can overlap on the same visual track. The later-starting clip appears on top, and both clips contribute audio. V2 appears above V1. A blank gap renders black. The sequence ends at the last included clip edge.

## Tracks, ranges and narration

Drop media below the last track to create compatible tracks at that time. Use **+ Add** to insert tracks, graphics and sounds. Ctrl-click clips or track labels to extend the selection. Link or unlink from **Selection**. Shift-drag a track to mark a frame range and enable **Loop**. **Isolate marked range** splits the boundaries for independent editing. Whisper uses the marked intersection with the selected clip. Shift-drag a picture in the monitor to resize, Alt-drag to rotate, or right-click to arrange and reset.

Paste your transcript into the Whisper dialog to match its lines against recognized word times. Styles have live samples. New subtitles occupy a separate video track. **Translate subtitles** preserves timings. **Voice these captions** creates a separate WAV audio track with speech fitted to each cue. **Dub voice or script** starts with recognition and optionally translates before voicing. Mute original dialogue in the audio inspector when mixing a dub.

Local translation runs Argos language packages on CPU with CTranslate2. A prepared language pair works offline. The first use downloads missing software and the selected direct language pair. Piper downloads an offline neural voice on first use. Select English, Russian, German, Spanish or French in the voice dialog. Windows system speech uses installed desktop voices and an optional exact voice name. The OpenAI provider accepts a per-task key or the OPENAI_API_KEY environment variable. Cloud translation and narration send the cue text to the API. Use **Show captions** in the inspector to toggle a subtitle layer in the preview and export. Project saves contain neither keys nor browser cookies.

## Captions and foreground extraction

Select a clip with audio and choose **Transcribe with Whisper**. Choose **tiny**, **base**, **small**, **medium**, **large-v3** or **turbo**. The estimate changes as you select models. The first estimate uses a rough CPU range. Later estimates use the last measured recognition time for the same model on this installation. Model download and initialization take additional time. **Change model** during recognition cancels the current pass and opens the model selector again.

Choose **Studio**, **Headline**, **Cinema**, **Boxed** or **Signal**. **Edit captions** accepts one timed cue per line. Times refer to the original source, so captions follow trims, splits and speed changes. The video export burns in the selected style. **Export → SRT** writes editable subtitle text and timings.

**Remove background** processes the selected interval with local rembg / U²-Net. It creates a transparent VP9 WebM for motion or PNG for stills, keeps the original in the pool, and replaces the timeline clip with the foreground. Video processing uses the project frame rate and a maximum long edge of 1280 pixels. Put background footage on V1 and the foreground on V2.

## Downloads, conversion and export

**↓** beside **Import media** opens the yt-dlp downloader. Paste a YouTube or TikTok video URL, enter start and end times in seconds or HH:MM:SS, and choose MP4 or MP3. Downloaded media, generated graphics, narration and background cutouts go in the project media folder. Saving an untitled project copies staged media beside the project file. Choose your signed-in browser in the download dialog when authentication is required. The placement selector sends the result to the pool, sequence end, playhead, overlay track or preview-only audio track. **Full source transfer** downloads the entire media file and trims locally when a source cannot serve a partial download. Availability also depends on the source site's access restrictions. Setup reuses compatible downloader packages.

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

The Windows workflow builds the native host and installer, verifies editing and installed startup, and publishes the versioned installer to GitHub Releases. See `.github/workflows/windows.yml` for the Windows build commands.

The private Windows runtime lives in `%LOCALAPPDATA%\NanoCutRuntime`. Cache, browser profile and recovery data live under `~/.nanocut`. Speech and segmentation weights use their respective upstream model caches. Removing the application preserves projects, source footage and the downloaded runtime.

