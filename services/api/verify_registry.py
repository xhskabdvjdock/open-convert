"""Run real engine conversions and write only passing pairs to conversion_registry.json."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import standalone as api


def check_image_matrix() -> tuple[list[dict],list[dict]]:
    pairs=[];failed=[]
    for source in api.IMAGE_FORMATS:
        raw=io.BytesIO()
        Image.new("RGB",(17,11),(70,120,180)).save(raw,format=source)
        encoded=raw.getvalue()
        for target in api.IMAGE_FORMATS:
            try:
                result=api.convert_image(encoded,target)
                with Image.open(io.BytesIO(result)) as image:
                    assert image.format==target and image.size==(17,11)
                    image.load()
                pairs.append({"input":source,"output":target})
                print(f"PASS image {source} -> {target}")
            except Exception as exc:
                print(f"FAIL image {source} -> {target}: {type(exc).__name__}: {exc}")
                failed.append({"input":source,"output":target,"error":type(exc).__name__})
    return pairs,failed


def generated_media_inputs(folder: Path) -> tuple[dict[str,bytes],dict[str,bytes]]:
    wav=folder/"source.wav"
    subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","sine=frequency=440:duration=0.35","-c:a","pcm_s16le",str(wav),"-y"],check=True)
    wav_data=wav.read_bytes()
    mp4=folder/"source.mp4"
    subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc=size=96x64:rate=12:duration=0.4","-f","lavfi","-i","sine=frequency=440:duration=0.4","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",str(mp4),"-y"],check=True)
    webm=folder/"source.webm"
    subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc=size=96x64:rate=12:duration=0.4","-f","lavfi","-i","sine=frequency=440:duration=0.4","-c:v","libvpx-vp9","-c:a","libopus","-deadline","realtime","-cpu-used","8",str(webm),"-y"],check=True)
    audio={"wav":wav_data}
    if "MP3" in api.actual_outputs("audio"):
        mp3=folder/"source.mp3"
        subprocess.run(["ffmpeg","-v","error","-i",str(wav),"-map","0:a:0","-c:a","libmp3lame","-b:a","192k",str(mp3),"-y"],check=True)
        audio["mp3"]=mp3.read_bytes()
    return audio,{"mp4":mp4.read_bytes(),"webm":webm.read_bytes()}


def check_media_matrix(audio_sources: dict[str,bytes],video_sources: dict[str,bytes]) -> tuple[list[dict],list[dict],list[dict]]:
    audio_pairs=[];video_pairs=[];failed=[]
    candidate={"verified":False,"image_pairs":[],"audio_pairs":[],"video_pairs":[]}
    for source in audio_sources:
        candidate["audio_pairs"] += [{"input":source,"output":output} for output in api.actual_outputs("audio")]
    video_aliases={"mp4":["mov","mp4","m4a","3gp","3g2","mj2"],"webm":["matroska","webm"]}
    for source in video_sources:
        for alias in video_aliases[source]:
            candidate["video_pairs"] += [{"input":alias,"output":output} for output in api.actual_outputs("video")]
    api.REGISTRY=candidate
    for source_name,data in audio_sources.items():
        info=api.probe(data); assert info and info["family"]=="audio",source_name
        aliases=(info["format"].split(","))
        for alias in aliases:
            candidate["audio_pairs"] += [{"input":alias,"output":output} for output in api.actual_outputs("audio")]
    for source_name,data in video_sources.items():
        info=api.probe(data); assert info and info["family"]=="video",source_name
        aliases=info["format"].split(",")
        for alias in aliases:
            candidate["video_pairs"] += [{"input":alias,"output":output} for output in api.actual_outputs("video")]
    for source_name,data in audio_sources.items():
        for target in api.actual_outputs("audio"):
            try:
                output,suffix=api.convert_media(data,target)
                info=api.probe(output,require_registered_input=False); assert info and info["streams"]["audio"]
                with tempfile.NamedTemporaryFile(suffix=suffix) as decoded:
                    decoded.write(output);decoded.flush()
                    subprocess.run(["ffmpeg","-v","error","-i",decoded.name,"-f","null","-"],capture_output=True,check=True,timeout=20)
                audio_pairs.append({"input":source_name,"output":target})
                print(f"PASS audio {source_name.upper()} -> {target}; decoded and probed")
            except Exception as exc:
                print(f"FAIL audio {source_name.upper()} -> {target}: {type(exc).__name__}: {exc}")
                failed.append({"family":"audio","input":source_name,"output":target,"error":type(exc).__name__})
    for source_name,data in video_sources.items():
        for target in api.actual_outputs("video"):
            try:
                output,suffix=api.convert_media(data,target)
                info=api.probe(output,require_registered_input=False); assert info
                if target in api.VIDEO_OUTPUTS: assert info["family"]=="video" and info["width"]==96 and info["height"]==64
                else: assert info["streams"]["audio"] and not info["streams"]["video"]
                with tempfile.NamedTemporaryFile(suffix=suffix) as decoded:
                    decoded.write(output);decoded.flush()
                    subprocess.run(["ffmpeg","-v","error","-i",decoded.name,"-f","null","-"],capture_output=True,check=True,timeout=20)
                video_pairs.append({"input":source_name,"output":target})
                print(f"PASS video {source_name.upper()} -> {target}; decoded and probed")
            except Exception as exc:
                print(f"FAIL video {source_name.upper()} -> {target}: {type(exc).__name__}: {exc}")
                failed.append({"family":"video","input":source_name,"output":target,"error":type(exc).__name__})
    # Registry keys are canonical fixture input formats; API uses the detected FFprobe aliases.
    for pair in audio_pairs: pair["input"]=pair["input"]
    for pair in video_pairs: pair["input"]=pair["input"]
    return audio_pairs,video_pairs,failed


def main() -> int:
    if not api.ffmpeg_version() or not api.shutil.which("ffprobe"):
        print("FAIL: ffmpeg/ffprobe are required to build a verified registry")
        return 1
    with tempfile.TemporaryDirectory(prefix="openconvert-verify-") as work:
        audio_sources,video_sources=generated_media_inputs(Path(work))
        image_pairs,image_failures=check_image_matrix()
        audio_pairs,video_pairs,media_failures=check_media_matrix(audio_sources,video_sources)
    failures=image_failures+media_failures
    report={
        "schema_version":1,"verified":True,"tested_at":datetime.now(timezone.utc).isoformat(),
        "engine_versions":{"pillow":Image.__version__,"ffmpeg":api.ffmpeg_version()},
        "test_inputs":{"image_formats":list(api.IMAGE_FORMATS),"audio_formats":list(audio_sources),"video_formats":list(video_sources)},
        "image_pairs":image_pairs,"audio_pairs":audio_pairs,"video_pairs":video_pairs,
        "failed_pairs":failures,
        "counts":{"image":len(image_pairs),"audio":len(audio_pairs),"video":len(video_pairs),"failed":len(failures)},
    }
    api.REGISTRY_PATH.write_text(json.dumps(report,indent=2)+"\n")
    print(f"Registry written: {api.REGISTRY_PATH}; passed pairs: {sum(report['counts'].values())}; failures removed from advertisement.")
    return 0 if image_pairs and audio_pairs and video_pairs and not failures else 1


if __name__=="__main__": raise SystemExit(main())
