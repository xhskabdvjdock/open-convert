"""Dependency-light local API. Uses only stdlib, Pillow, and installed FFmpeg tools."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import warnings
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageOps, UnidentifiedImageError

Image.init()
HOST = os.getenv("API_HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))
MAX_UPLOAD = int(os.getenv("MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
MAX_IMAGE = int(os.getenv("MAX_IMAGE_UPLOAD_BYTES", str(20 * 1024 * 1024)))
MAX_OUTPUT = int(os.getenv("MAX_MEDIA_OUTPUT_BYTES", str(200 * 1024 * 1024)))
ORIGINS = {part.strip() for part in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if part.strip()}
IMAGE_SPECS = {
    "PNG": ("png", "image/png"), "JPEG": ("jpg", "image/jpeg"), "WEBP": ("webp", "image/webp"),
    "AVIF": ("avif", "image/avif"), "GIF": ("gif", "image/gif"), "TIFF": ("tiff", "image/tiff"), "BMP": ("bmp", "image/bmp"),
}
IMAGE_FORMATS = {name: value for name, value in IMAGE_SPECS.items() if name in Image.OPEN and name in Image.SAVE}
AUDIO_OUTPUTS = {"MP3": ("mp3", "libmp3lame"), "WAV": ("wav", "pcm_s16le"), "FLAC": ("flac", "flac"), "AAC": ("adts", "aac"), "M4A": ("ipod", "aac"), "OGG": ("ogg", "libvorbis"), "OPUS": ("opus", "libopus")}
VIDEO_OUTPUTS = {"MP4": ("mp4", "libx264", "aac"), "WEBM": ("webm", "libvpx-vp9", "libopus"), "MOV": ("mov", "libx264", "aac"), "MKV": ("matroska", "libx264", "aac")}
REGISTRY_PATH = Path(__file__).with_name("conversion_registry.json")
ENABLE_PLATFORM_DOWNLOADS = os.getenv("ENABLE_PLATFORM_DOWNLOADS", "true").lower() == "true"
YTDLP = shutil.which("yt-dlp")
YTDLP_WORKER = Path(__file__).with_name("ytdlp_worker.py")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def media_encoders() -> set[str]:
    binary = shutil.which("ffmpeg")
    if not binary:
        return set()
    try:
        result = subprocess.run([binary, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=5)
        return {m.group(1) for line in result.stdout.splitlines() if (m := re.match(r"\s*[A-Z.]{6}\s+(\S+)", line))}
    except (OSError, subprocess.TimeoutExpired):
        return set()


def actual_outputs(family: str) -> list[str]:
    encoders = media_encoders()
    audio = [name for name, (_, codec) in AUDIO_OUTPUTS.items() if codec in encoders]
    if family == "audio":
        return audio
    return [name for name, (_, video, audio_codec) in VIDEO_OUTPUTS.items() if video in encoders and audio_codec in encoders] + audio


def ffmpeg_version() -> str | None:
    binary=shutil.which("ffmpeg")
    if not binary: return None
    try: return subprocess.run([binary,"-version"],capture_output=True,text=True,timeout=3).stdout.splitlines()[0]
    except (OSError,subprocess.TimeoutExpired,IndexError): return None


def load_verified_registry() -> dict:
    try:
        candidate=json.loads(REGISTRY_PATH.read_text())
        versions=candidate.get("engine_versions",{})
        if not candidate.get("verified") or versions.get("pillow") != Image.__version__ or versions.get("ffmpeg") != ffmpeg_version():
            raise ValueError("Installed processing engines differ from the integration tested versions.")
        return candidate
    except (OSError,ValueError,TypeError,json.JSONDecodeError):
        return {"verified":False,"reason":"No conversion registry matches the installed engine versions.","image_pairs":[],"audio_pairs":[],"video_pairs":[]}


REGISTRY = load_verified_registry()


def verified_outputs(family: str, detected: list[str]) -> list[str]:
    installed=set(actual_outputs(family)) if family in {"audio","video"} else set(IMAGE_FORMATS)
    found=set(detected)
    return list(dict.fromkeys(pair["output"] for pair in REGISTRY.get(f"{family}_pairs",[]) if pair["input"] in found and pair["output"] in installed))


def safe_name(filename: str) -> str:
    filename = filename.replace("\\", "/").split("/")[-1]
    filename = re.sub(r"[^\w.() -]", "_", filename, flags=re.UNICODE).strip(" .")[:180]
    return filename or "converted-file"


def content_disposition(filename: str) -> str:
    fallback = filename.encode("ascii", "ignore").decode("ascii") or "downloaded-file"
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename)}'


def probe(data: bytes, require_registered_input: bool = True) -> dict | None:
    binary = shutil.which("ffprobe")
    if not binary:
        return None
    try:
        result = subprocess.run([binary, "-v", "error", "-show_entries", "format=format_name,duration:stream=codec_type,width,height", "-of", "json", "pipe:0"], input=data, capture_output=True, timeout=12, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C"})
        if result.returncode:
            return None
        obj = json.loads(result.stdout)
        streams = obj.get("streams", [])
        video = any(s.get("codec_type") == "video" for s in streams)
        audio = any(s.get("codec_type") == "audio" for s in streams)
        if not audio and not video:
            return None
        formats = (obj.get("format", {}).get("format_name") or "").lower().split(",")
        names = {"mov", "mp4", "m4a", "3gp", "3g2", "mj2", "matroska", "webm", "avi", "mpeg", "mpegts", "asf", "flv", "ogg"} if video else {"mp3", "wav", "flac", "aac", "adts", "ipod", "m4a", "ogg", "opus", "aiff", "ape", "wma", "amr"}
        found = sorted(set(formats) & names)
        if not found:
            return None
        family = "video" if video else "audio"
        output_formats = verified_outputs(family,found) if require_registered_input else actual_outputs(family)
        if require_registered_input and not output_formats: return None
        stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        return {"family": family, "format": ", ".join(found), "width": stream.get("width"), "height": stream.get("height"), "duration": obj.get("format", {}).get("duration"), "streams": {"audio": audio, "video": video}, "outputs": output_formats}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def inspect_file(data: bytes) -> dict:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                fmt = (image.format or "").upper()
                if fmt in IMAGE_FORMATS:
                    if len(data) > MAX_IMAGE:
                        raise ApiError(413, "image_too_large", "Image exceeds the configured image size limit.")
                    if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1:
                        raise ApiError(422, "animated_image", "Animated images are not supported.")
                    image.verify()
                    outputs=verified_outputs("image",[fmt])
                    if not outputs: raise ApiError(415,"unverified_conversion","No verified conversion pair is configured for this image format.")
                    return {"family": "image", "format": fmt, "width": image.width, "height": image.height, "size_bytes": len(data), "outputs": outputs}
    except ApiError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        pass
    info = probe(data)
    if info:
        info["size_bytes"] = len(data)
        return info
    raise ApiError(415, "unsupported_input", "File signature is not a supported image, audio, or video format.")


def convert_image(data: bytes, target: str) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if (image.format or "").upper() not in IMAGE_FORMATS:
                    raise ApiError(415, "unsupported_input", "Unsupported image input.")
                if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1:
                    raise ApiError(422, "animated_image", "Animated images are not supported.")
                image.verify()
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)
            if target == "JPEG" and image.mode not in ("RGB", "L"):
                if image.mode == "P" and "transparency" in image.info: image = image.convert("RGBA")
                background = Image.new("RGB", image.size, (255, 255, 255))
                if "A" in image.getbands(): background.paste(image, mask=image.getchannel("A"))
                else: background.paste(image.convert("RGB"))
                image = background
            elif target in {"BMP", "GIF"} and image.mode not in ("RGB", "L", "P"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                if "A" in image.getbands(): background.paste(image, mask=image.getchannel("A"))
                else: background.paste(image.convert("RGB"))
                image = background
            if target == "GIF" and image.mode != "P": image = image.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
            elif target == "PNG" and image.mode == "P": image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            elif target == "PNG" and image.mode not in {"1", "L", "LA", "RGB", "RGBA", "I", "I;16"}: image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            elif target == "WEBP" and image.mode not in ("RGB", "RGBA"): image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            elif target == "AVIF" and image.mode not in ("RGB", "RGBA", "L"): image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            size = image.size
            out = io.BytesIO()
            options = {"quality": 88, "method": 5} if target == "WEBP" else ({"quality": 90, "optimize": True} if target == "JPEG" else {"optimize": True} if target == "PNG" else {})
            image.save(out, format=target, **options)
        with Image.open(io.BytesIO(out.getvalue())) as check:
            if check.format != target or check.size != size: raise ApiError(500, "output_invalid", "Converted image failed output validation.")
            check.verify()
        return out.getvalue()
    except ApiError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ApiError(422, "invalid_image", "Image could not be decoded or converted.") from None


def convert_media(data: bytes, target: str) -> tuple[bytes, str]:
    info = inspect_file(data)
    if target not in info["outputs"]:
        raise ApiError(422, "unsupported_conversion", "This conversion pair is not enabled for the detected input.")
    binary = shutil.which("ffmpeg")
    if not binary: raise ApiError(503, "engine_unavailable", "FFmpeg is not installed.")
    suffixes = {"MP3":".mp3", "WAV":".wav", "FLAC":".flac", "AAC":".aac", "M4A":".m4a", "OGG":".ogg", "OPUS":".opus", "MP4":".mp4", "WEBM":".webm", "MOV":".mov", "MKV":".mkv"}
    suffix = suffixes[target]
    temp = tempfile.TemporaryDirectory(prefix="openconvert-")
    output = Path(temp.name) / ("result" + suffix)
    cmd = [binary, "-nostdin", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "pipe", "-i", "pipe:0"]
    if target in AUDIO_OUTPUTS:
        container, codec = AUDIO_OUTPUTS[target]
        cmd += ["-map", "0:a:0", "-vn", "-c:a", codec]
        if target in {"MP3", "AAC", "M4A", "OGG", "OPUS"}: cmd += ["-b:a", "192k"]
        cmd += ["-f", container]
    else:
        container, vcodec, acodec = VIDEO_OUTPUTS[target]
        cmd += ["-map", "0:v:0", "-map", "0:a?", "-c:v", vcodec, "-c:a", acodec, "-threads", "2"]
        if target == "MP4": cmd += ["-movflags", "+faststart"]
        if target == "WEBM": cmd += ["-deadline", "good", "-cpu-used", "4"]
        cmd += ["-f", container]
    cmd += ["-fs", str(MAX_OUTPUT + 1), str(output)]
    try:
        result = subprocess.run(cmd, input=data, capture_output=True, timeout=180, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C"})
        if result.returncode or not output.is_file(): raise ApiError(422, "conversion_failed", "FFmpeg could not convert this media file.")
        if output.stat().st_size > MAX_OUTPUT: raise ApiError(413, "output_too_large", "Converted output exceeds its size limit.")
        payload = output.read_bytes()
        checked = probe(payload,require_registered_input=False)
        if not checked or (target in VIDEO_OUTPUTS and checked["family"] != "video") or (target in AUDIO_OUTPUTS and not checked["streams"]["audio"]):
            raise ApiError(500, "output_invalid", "Converted media failed output validation.")
        return payload, suffix
    except subprocess.TimeoutExpired:
        raise ApiError(408, "conversion_timeout", "Media conversion exceeded the time limit.") from None
    finally:
        temp.cleanup()


def parse_multipart(content_type: str, body: bytes) -> dict:
    message = BytesParser(policy=policy.default).parsebytes(b"Content-Type: " + content_type.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
    if not message.is_multipart(): raise ApiError(400,"invalid_multipart","Expected multipart form data.")
    fields={}
    for part in message.iter_parts():
        name=part.get_param("name",header="content-disposition")
        if not name: continue
        payload=part.get_payload(decode=True) or b""
        filename=part.get_filename()
        fields[name]=(filename,payload) if filename is not None else payload.decode("utf-8","replace")
    return fields


def capability_report():
    ytdlp_version=None
    if YTDLP:
        try: ytdlp_version=subprocess.run([YTDLP,"--version"],capture_output=True,text=True,timeout=3).stdout.strip()
        except (OSError,subprocess.TimeoutExpired): pass
    platform_enabled=bool(ENABLE_PLATFORM_DOWNLOADS and YTDLP and shutil.which("ffprobe"))
    return {"engines":{"images":f"Pillow {Image.__version__}","media":ffmpeg_version(),"probe":bool(shutil.which("ffprobe")),"yt_dlp":ytdlp_version},"max_upload_bytes":MAX_UPLOAD,"max_image_upload_bytes":MAX_IMAGE,"max_media_output_bytes":MAX_OUTPUT,"verified_registry":"/api/formats","registry_verified":REGISTRY.get("verified",False),"media_downloader":{"enabled":platform_enabled,"direct_file_urls":False,"platform_urls":platform_enabled,"engine":"yt-dlp" if YTDLP else None,"integration_tested":False,"reason":"Each public URL is analyzed live; unsupported or restricted links fail explicitly. Set ENABLE_PLATFORM_DOWNLOADS=false to disable." if platform_enabled else "yt-dlp or ffprobe is unavailable, or platform downloads were disabled by configuration."}}


def map_ytdlp_error(diagnostic: str) -> ApiError:
    text=diagnostic.lower()
    if any(value in text for value in ("restricted destination", "name or service not known", "temporary failure in name resolution", "could not resolve", "failed to resolve", "connection timed out")):
        return ApiError(502,"platform_network_error","The platform or its media host could not be reached from this server.")
    if "429" in text or "too many requests" in text or "rate limit" in text:
        return ApiError(429,"platform_rate_limited","The platform is temporarily limiting requests. Wait a while before trying again.")
    if "login" in text or "authentication" in text or "sign in" in text or "private video" in text or "private content" in text:
        return ApiError(403,"platform_restricted","The platform requires access this service does not use, or restricts this media.")
    if "403" in text or "forbidden" in text:
        return ApiError(403,"platform_restricted","The platform denied this server's request. The link may require access or may be region-restricted.")
    if "drm" in text or "encrypted" in text:
        return ApiError(415,"protected_media","Protected media cannot be downloaded.")
    if "unsupported url" in text or "no suitable extractor" in text:
        return ApiError(422,"platform_unsupported","This link format is not supported by the installed media engine.")
    if "requested format is not available" in text or "no video formats found" in text or "no downloadable formats" in text:
        return ApiError(422,"no_formats","The platform did not provide a downloadable format for this link.")
    if "video unavailable" in text or "media unavailable" in text or "http error 404" in text or "not found" in text:
        return ApiError(404,"media_unavailable","The platform did not make this media available to the downloader. It may still play in your browser.")
    return ApiError(422,"platform_unsupported","The link could not be analyzed. It may be restricted, unavailable, or unsupported by the installed media engine.")


def run_ytdlp(payload: dict, timeout: int) -> dict:
    if not (ENABLE_PLATFORM_DOWNLOADS and YTDLP and shutil.which("ffprobe")):
        raise ApiError(503,"downloader_unavailable","Platform downloading is disabled or the required engine is unavailable.")
    env={key:value for key,value in os.environ.items() if key not in {"HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","http_proxy","https_proxy","all_proxy","YT_DLP_PROXY"}}
    env.update({"PYTHONNOUSERSITE":"1","PYTHONDONTWRITEBYTECODE":"1","LANG":"C.UTF-8"})
    try:
        result=subprocess.run([sys.executable,str(YTDLP_WORKER)],input=json.dumps(payload).encode(),capture_output=True,timeout=timeout,check=False,env=env)
    except subprocess.TimeoutExpired:
        raise ApiError(408,"platform_timeout","The platform took too long to respond. Try again later.") from None
    except OSError:
        raise ApiError(503,"downloader_unavailable","The platform downloader could not be started.") from None
    if result.returncode:
        try: diagnostic=json.loads(result.stderr.decode("utf-8","replace")).get("error","").lower()
        except (ValueError,AttributeError): diagnostic=""
        raise map_ytdlp_error(diagnostic)
    try: return json.loads(result.stdout)
    except (ValueError,UnicodeDecodeError): raise ApiError(502,"invalid_platform_response","The platform returned invalid media information.") from None


def validate_platform_url(url) -> str:
    if not isinstance(url,str) or len(url)>4096 or any(ord(char)<32 for char in url):
        raise ApiError(422,"invalid_url","Enter a valid public platform URL.")
    parts=urlsplit(url)
    if parts.scheme not in {"http","https"} or not parts.hostname or parts.username or parts.password:
        raise ApiError(422,"invalid_url","Only public HTTP(S) platform URLs are accepted.")
    return url


class Handler(BaseHTTPRequestHandler):
    server_version = "OpenConvertLocal/0.3"

    def log_message(self, fmt, *args):
        # Avoid logging request bodies or sensitive URLs/query strings.
        print(f"[{self.log_date_time_string()}] {self.command} {self.path.split('?')[0]} {args[1] if len(args)>1 else ''}")

    def send_json(self, status: int, payload: dict):
        data=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(data))); self.send_header("Cache-Control","no-store"); self.cors(); self.end_headers(); self.wfile.write(data)

    def cors(self):
        origin=self.headers.get("Origin")
        if origin in ORIGINS:
            self.send_header("Access-Control-Allow-Origin",origin); self.send_header("Vary","Origin")

    def do_OPTIONS(self):
        self.send_response(204); self.cors(); self.send_header("Access-Control-Allow-Methods","GET, POST, OPTIONS"); self.send_header("Access-Control-Allow-Headers","Content-Type"); self.send_header("Access-Control-Max-Age","600"); self.end_headers()

    def do_GET(self):
        if self.path == "/api/health": return self.send_json(200,{"status":"ok","version":"0.3.0"})
        if self.path == "/api/capabilities": return self.send_json(200,capability_report())
        if self.path == "/api/formats": return self.send_json(200,REGISTRY)
        self.send_json(404,{"detail":{"code":"not_found","message":"Endpoint not found."}})

    def read_body(self):
        try: length=int(self.headers.get("Content-Length","-1"))
        except ValueError: length=-1
        if length < 0: raise ApiError(411,"content_length_required","Content-Length is required.")
        if length > MAX_UPLOAD + 1024*1024: raise ApiError(413,"request_too_large","Request exceeds the configured limit.")
        return self.rfile.read(length)

    def do_POST(self):
        try:
            body=self.read_body()
            if self.path in {"/api/inspect","/api/convert"}:
                fields=parse_multipart(self.headers.get("Content-Type",""),body)
                upload=fields.get("file")
                if not upload or not upload[1]: raise ApiError(400,"empty_file","Choose a non-empty file.")
                filename,data=upload
                if len(data)>MAX_UPLOAD: raise ApiError(413,"file_too_large","File exceeds the configured size limit.")
                info=inspect_file(data)
                if self.path=="/api/inspect": return self.send_json(200,info)
                target=str(fields.get("output_format","")).upper()
                if target not in info["outputs"]: raise ApiError(422,"unsupported_conversion","This conversion pair is not enabled for this input.")
                safe=safe_name(filename or "converted-file"); base=safe.rsplit(".",1)[0] if "." in safe else safe
                if info["family"]=="image":
                    result=convert_image(data,target); ext,mime=IMAGE_FORMATS[target]
                else:
                    result,ext=convert_media(data,target); mime="application/octet-stream"
                output_name=f"{base}.{ext}"
                self.send_response(200); self.send_header("Content-Type",mime); self.send_header("Content-Disposition",content_disposition(output_name)); self.send_header("Content-Length",str(len(result))); self.send_header("Cache-Control","no-store"); self.send_header("X-Content-Type-Options","nosniff"); self.cors(); self.end_headers(); self.wfile.write(result); return
            if self.path in {"/api/download/analyze","/api/download"}:
                if len(body)>16*1024: raise ApiError(413,"request_too_large","Platform URL request is too large.")
                try: data=json.loads(body)
                except (ValueError,TypeError): raise ApiError(422,"invalid_request","A JSON request is required.") from None
                url=validate_platform_url(data.get("url"))
                if self.path=="/api/download/analyze":
                    result=run_ytdlp({"mode":"analyze","url":url},timeout=50)
                    options=result.get("options") or []
                    if not options: raise ApiError(422,"no_formats","The platform did not return downloadable formats.")
                    return self.send_json(200,{"title":result.get("title") or "Media","extractor":result.get("extractor") or "Platform extractor","duration":result.get("duration"),"options":options,"engine":"yt-dlp"})
                option=str(data.get("option") or "")
                if option!="audio:best" and not re.fullmatch(r"video:\d{1,4}",option):
                    raise ApiError(422,"invalid_option","Select one of the quality options returned by link analysis.")
                temp=tempfile.TemporaryDirectory(prefix="openconvert-platform-")
                try:
                    result=run_ytdlp({"mode":"download","url":url,"option":option,"output_dir":temp.name,"max_bytes":MAX_UPLOAD},timeout=240)
                    output_path=Path(temp.name)/Path(result.get("filename","")).name
                    if not output_path.is_file(): raise ApiError(502,"download_missing","The downloader did not create a result file.")
                    size=output_path.stat().st_size
                    if not size or size>MAX_UPLOAD: raise ApiError(413,"download_too_large","Downloaded media is empty or exceeds the configured size limit.")
                    payload=output_path.read_bytes()
                    details=probe(payload,require_registered_input=False)
                    if not details or not (details["streams"]["video"] or details["streams"]["audio"]):
                        raise ApiError(415,"download_validation_failed","Downloaded output did not contain a valid media stream.")
                    if option=="audio:best" and details["streams"]["video"]:
                        raise ApiError(415,"download_validation_failed","Audio-only selection unexpectedly contained video.")
                    if option.startswith("video:") and not details["streams"]["video"]:
                        raise ApiError(415,"download_validation_failed","Selected video output has no video stream.")
                    ffmpeg=shutil.which("ffmpeg")
                    if not ffmpeg: raise ApiError(503,"validation_engine_unavailable","FFmpeg is required to validate downloaded media.")
                    try:
                        validation=subprocess.run([ffmpeg,"-nostdin","-v","error","-protocol_whitelist","pipe","-i","pipe:0","-f","null","-"],input=payload,capture_output=True,timeout=90,check=False,env={"PATH":os.environ.get("PATH","/usr/bin:/bin"),"LANG":"C"})
                    except subprocess.TimeoutExpired: raise ApiError(408,"validation_timeout","Downloaded media validation exceeded its time limit.") from None
                    if validation.returncode: raise ApiError(415,"download_validation_failed","Downloaded output could not be decoded.")
                    filename=safe_name(result.get("filename") or "downloaded-media.mp4")
                    self.send_response(200);self.send_header("Content-Type","application/octet-stream");self.send_header("Content-Disposition",content_disposition(filename));self.send_header("Content-Length",str(len(payload)));self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff");self.cors();self.end_headers();self.wfile.write(payload)
                finally: temp.cleanup()
                return
            raise ApiError(404,"not_found","Endpoint not found.")
        except ApiError as error:
            self.send_json(error.status,{"detail":{"code":error.code,"message":error.message}})
        except (BrokenPipeError,ConnectionResetError):
            return
        except Exception:
            self.send_json(500,{"detail":{"code":"internal_error","message":"The request could not be completed."}})


def main():
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    server.daemon_threads=True
    print(f"OpenConvert standalone API on http://{HOST}:{PORT}")
    print(json.dumps(capability_report(),ensure_ascii=False))
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=="__main__": main()
