"""yt-dlp subprocess adapter with public-IP-only outbound connections.

Input and output are JSON. It accepts no cookies, arbitrary flags, or format
selectors from callers. The caller selects one of the extracted option keys.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import shlex
import shutil
import socket
import sys
from pathlib import Path


def install_public_network_guard():
    original_getaddrinfo = socket.getaddrinfo
    original_connect = socket.socket.connect

    def checked_records(host, port, *args, **kwargs):
        if isinstance(host, str) and not host:
            raise OSError("Empty destination host")
        records = original_getaddrinfo(host, port, *args, **kwargs)
        if not records:
            raise OSError("Destination did not resolve")
        for record in records:
            address = record[4][0].split("%", 1)[0]
            if not ipaddress.ip_address(address).is_global:
                raise OSError("Restricted destination address")
        return records

    def checked_connect(sock, address):
        if not isinstance(address, tuple) or len(address) < 2:
            raise OSError("Unsupported socket destination")
        host, port = address[0], address[1]
        records = checked_records(host, port, type=sock.family, proto=sock.proto)
        last_error = None
        for family, socktype, proto, _canonname, sockaddr in records:
            if family != sock.family:
                continue
            try:
                return original_connect(sock, sockaddr)
            except OSError as exc:
                last_error = exc
        if last_error:
            raise last_error
        raise OSError("No public address for destination")

    socket.getaddrinfo = checked_records
    socket.socket.connect = checked_connect
    # Do not let system proxy variables route requests around the IP guard.
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(key, None)


def quality_options(info: dict) -> list[dict]:
    formats = info.get("formats") or []
    video = [f for f in formats if f.get("vcodec") not in (None, "none") and isinstance(f.get("height"), int)]
    audio = [f for f in formats if f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")]
    options=[]
    heights=sorted({f["height"] for f in video}, reverse=True)
    for height in heights:
        at_height=[f for f in video if f.get("height")==height]
        # A progressive format is self-contained; otherwise yt-dlp merges the
        # selected video stream with the best audio stream using FFmpeg.
        progressive=[f for f in at_height if f.get("acodec") not in (None,"none")]
        split=[f for f in at_height if f.get("acodec") in (None,"none")]
        options.append({"key":f"video:{height}","kind":"video","height":height,"label":f"{height}p","has_audio":bool(progressive or (split and audio))})
    if audio or any(f.get("acodec") not in (None,"none") for f in video):
        options.append({"key":"audio:best","kind":"audio","height":None,"label":"Audio only","has_audio":True})
    return options


def safe_format_id(value) -> str | None:
    if value is None: return None
    text=str(value)
    return text if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}",text) else None


def pick_format(info: dict, option_key: str) -> str:
    formats=info.get("formats") or []
    if option_key not in {option.get("key") for option in quality_options(info)}:
        raise ValueError("Choose one of the analyzed output options")
    if option_key == "audio:best":
        audio=[f for f in formats if f.get("acodec") not in (None,"none") and safe_format_id(f.get("format_id"))]
        if not audio: raise ValueError("No audio-only option is available")
        audio_only=[f for f in audio if f.get("vcodec") in (None,"none")]
        choices=audio_only or audio
        chosen=max(choices,key=lambda f:(f.get("abr") or f.get("tbr") or 0))
        return safe_format_id(chosen["format_id"])
    match=re.fullmatch(r"video:(\d{1,4})",option_key or "")
    if not match: raise ValueError("Choose one of the analyzed output options")
    maximum=int(match.group(1))
    video=[f for f in formats if f.get("vcodec") not in (None,"none") and isinstance(f.get("height"),int) and f["height"]<=maximum and safe_format_id(f.get("format_id"))]
    audio=[f for f in formats if f.get("acodec") not in (None,"none") and f.get("vcodec") in (None,"none") and safe_format_id(f.get("format_id"))]
    if not video: raise ValueError("The selected video quality is no longer available")
    video_only=[f for f in video if f.get("acodec") in (None,"none")]
    if video_only and audio:
        v=max(video_only,key=lambda f:(f.get("height") or 0,f.get("fps") or 0,f.get("tbr") or 0))
        a=max(audio,key=lambda f:(f.get("abr") or f.get("tbr") or 0))
        return safe_format_id(v["format_id"])+"+"+safe_format_id(a["format_id"])
    progressive=[f for f in video if f.get("acodec") not in (None,"none")]
    if not progressive: raise ValueError("No compatible audio stream is available for this video")
    chosen=max(progressive,key=lambda f:(f.get("height") or 0,f.get("fps") or 0,f.get("tbr") or 0))
    return safe_format_id(chosen["format_id"])


def main():
    request=json.load(sys.stdin)
    url=request.get("url")
    mode=request.get("mode")
    if not isinstance(url,str) or len(url)>4096 or mode not in {"analyze","download"}:
        raise ValueError("Invalid request")
    # URL credentials and non-HTTP schemes are never allowed.
    from urllib.parse import urlsplit
    parts=urlsplit(url)
    if parts.scheme not in {"http","https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Only public HTTP(S) media page URLs are accepted")
    install_public_network_guard()
    from yt_dlp import YoutubeDL
    # Keep yt-dlp's normal request headers. A custom product User-Agent can
    # cause otherwise public platform pages to reject extraction requests.
    options={"quiet":True,"no_warnings":True,"noplaylist":True,"skip_download":True,"cachedir":False,"socket_timeout":10,"retries":1,"extractor_retries":1,"fragment_retries":1,"ignoreerrors":False,"logger":None,"nocheckcertificate":False,"proxy":None}
    if mode=="analyze":
        with YoutubeDL(options) as ydl:
            info=ydl.extract_info(url,download=False)
        if not isinstance(info,dict): raise ValueError("The platform did not return media information")
        options_out=quality_options(info)
        if not options_out: raise ValueError("No downloadable audio or video formats were returned")
        print(json.dumps({"id":str(info.get("id") or "")[:120],"title":str(info.get("title") or "Media")[:240],"extractor":str(info.get("extractor_key") or info.get("extractor") or "unknown")[:80],"duration":info.get("duration"),"options":options_out},ensure_ascii=False))
        return
    option_key=request.get("option")
    output_dir=Path(request.get("output_dir") or "")
    if not output_dir.is_dir(): raise ValueError("Output directory is unavailable")
    # Resolve once to validate option identifiers, then let yt-dlp extract again
    # in download mode. No cookies, credentials, playlists, or user flags.
    guarded_tools=output_dir/".guarded-tools"
    guarded_tools.mkdir(mode=0o700)
    for tool in ("ffmpeg","ffprobe"):
        binary=shutil.which(tool)
        if not binary: raise ValueError(f"{tool} is required to validate and merge media")
        wrapper=guarded_tools/tool
        wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(binary) + " -protocol_whitelist file,pipe \"$@\"\n")
        wrapper.chmod(0o700)
    options["ffmpeg_location"]=str(guarded_tools)
    with YoutubeDL(options) as ydl:
        info=ydl.extract_info(url,download=False)
        if not isinstance(info,dict): raise ValueError("The platform did not return media information")
        selector=pick_format(info,str(option_key or ""))
        available={safe_format_id(f.get("format_id")) for f in info.get("formats") or []}
        if any(part not in available for part in selector.split("+")):
            raise ValueError("Selected format is no longer available")
        ydl.params.update({"skip_download":False,"format":selector,"outtmpl":str(output_dir/"%(id)s.%(ext)s"),"max_filesize":int(request.get("max_bytes",100*1024*1024)),"overwrites":False,"continuedl":False,"nopart":True,"writethumbnail":False,"writeinfojson":False,"writesubtitles":False,"writeautomaticsub":False,"noplaylist":True,"merge_output_format":"mkv"})
        if option_key=="audio:best":
            ydl.params["postprocessors"]=[{"key":"FFmpegExtractAudio","preferredcodec":"best","preferredquality":0}]
            ydl.params["keepvideo"]=False
        downloaded=ydl.process_ie_result(info,download=True)
    files=[p for p in output_dir.iterdir() if p.is_file() and p.suffix not in {".part",".ytdl",".json",".jpg",".png",".webp"}]
    if len(files)!=1: raise ValueError("Downloader did not produce exactly one media file")
    print(json.dumps({"id":str(info.get("id") or "")[:120],"title":str(info.get("title") or "Media")[:240],"filename":files[0].name,"path":str(files[0]),"size_bytes":files[0].stat().st_size},ensure_ascii=False))


if __name__=="__main__":
    try: main()
    except Exception as exc:
        # No stack traces, URL query strings, or credentials in API output.
        print(json.dumps({"error":str(exc)[:300],"error_type":type(exc).__name__},ensure_ascii=False),file=sys.stderr)
        raise SystemExit(2)
