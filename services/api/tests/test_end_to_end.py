"""Real HTTP integration tests against the standalone API and installed engines."""
from __future__ import annotations

import http.client
import io
import json
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import standalone as api


class QuietHandler(api.Handler):
    def log_message(self, fmt, *args):
        pass


def multipart(filename: str, payload: bytes, target: str | None = None) -> tuple[str, bytes]:
    boundary="OpenConvertE2EBoundary"
    chunks=[f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode(),payload,b"\r\n"]
    if target:
        chunks += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"output_format\"\r\n\r\n{target}\r\n".encode()]
    chunks += [f"--{boundary}--\r\n".encode()]
    return f"multipart/form-data; boundary={boundary}",b"".join(chunks)


class ConversionE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not api.REGISTRY.get("verified"):
            raise RuntimeError("Run services/api/verify_registry.py before integration tests")
        try:
            cls.server=ThreadingHTTPServer(("127.0.0.1",0),QuietHandler)
        except PermissionError:
            raise unittest.SkipTest("Execution sandbox forbids opening loopback sockets; run these real HTTP tests outside the sandbox.")
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.port=cls.server.server_address[1]
        cls.temp=tempfile.TemporaryDirectory(prefix="openconvert-e2e-")
        cls.directory=Path(cls.temp.name)
        wav=cls.directory/"tone.wav"
        subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","sine=frequency=500:duration=0.4","-c:a","pcm_s16le",str(wav),"-y"],check=True)
        cls.audio_sources={"wav":wav.read_bytes()}
        if "mp3" in {p["input"] for p in api.REGISTRY["audio_pairs"]}:
            mp3=cls.directory/"tone.mp3"
            subprocess.run(["ffmpeg","-v","error","-i",str(wav),"-c:a","libmp3lame",str(mp3),"-y"],check=True)
            cls.audio_sources["mp3"]=mp3.read_bytes()
        mp4=cls.directory/"sample.mp4"
        subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc=size=96x64:rate=12:duration=0.4","-f","lavfi","-i","sine=frequency=500:duration=0.4","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",str(mp4),"-y"],check=True)
        cls.video_sources={"mp4":mp4.read_bytes()}
        webm=cls.directory/"sample.webm"
        subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc=size=96x64:rate=12:duration=0.4","-f","lavfi","-i","sine=frequency=500:duration=0.4","-c:v","libvpx-vp9","-c:a","libopus","-deadline","realtime","-cpu-used","8",str(webm),"-y"],check=True)
        cls.video_sources["webm"]=webm.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.temp.cleanup()

    def request(self,path,body=None,content_type=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.port,timeout=60)
        headers={"Content-Length":str(len(body or b""))}
        if content_type: headers["Content-Type"]=content_type
        conn.request("POST" if body is not None else "GET",path,body=body,headers=headers)
        response=conn.getresponse();data=response.read();status=response.status;headers=response.headers;conn.close()
        return status,headers,data

    def test_health_capabilities_and_registry(self):
        conn=http.client.HTTPConnection("127.0.0.1",self.port)
        conn.request("GET","/api/health");response=conn.getresponse();self.assertEqual(response.status,200);self.assertEqual(json.loads(response.read())["status"],"ok")
        conn.request("GET","/api/capabilities");response=conn.getresponse();cap=json.loads(response.read());conn.close()
        self.assertTrue(cap["registry_verified"])
        # Enabled state must reflect the actual configuration instead of a
        # hard-coded value: environments with yt-dlp and ffprobe installed
        # report platform downloads as enabled.
        import shutil
        expected_enabled=bool(api.ENABLE_PLATFORM_DOWNLOADS and api.YTDLP and shutil.which("ffprobe"))
        self.assertEqual(cap["media_downloader"]["enabled"],expected_enabled)

    def test_every_registered_image_pair_over_http(self):
        pairs=api.REGISTRY["image_pairs"]
        self.assertTrue(pairs)
        for pair in pairs:
            source=io.BytesIO();Image.new("RGB",(17,11),(25,105,180)).save(source,format=pair["input"])
            ctype,body=multipart("sample."+pair["input"].lower(),source.getvalue())
            status,_,data=self.request("/api/inspect",body,ctype)
            self.assertEqual(status,200,(pair,status,data[:200]))
            info=json.loads(data);self.assertEqual(info["format"],pair["input"]);self.assertIn(pair["output"],info["outputs"])
            ctype,body=multipart("sample."+pair["input"].lower(),source.getvalue(),pair["output"])
            status,headers,result=self.request("/api/convert",body,ctype)
            self.assertEqual(status,200,(pair,status,result[:200]))
            self.assertIn("filename=",headers.get("Content-Disposition",""))
            with Image.open(io.BytesIO(result)) as image:
                self.assertEqual(image.format,pair["output"]);self.assertEqual(image.size,(17,11));image.load()
        print(f"verified HTTP image pairs: {len(pairs)}")

    def test_every_registered_audio_pair_over_http_and_decodes(self):
        pairs=api.REGISTRY["audio_pairs"];self.assertTrue(pairs)
        for pair in pairs:
            source=self.audio_sources[pair["input"]]
            ctype,body=multipart("tone."+pair["input"],source,pair["output"])
            status,headers,result=self.request("/api/convert",body,ctype)
            self.assertEqual(status,200,(pair,status,result[:200]))
            info=api.probe(result,require_registered_input=False);self.assertTrue(info and info["streams"]["audio"],pair)
            output=Path(self.directory/"verified-audio-output.bin");output.write_bytes(result)
            subprocess.run(["ffmpeg","-v","error","-i",str(output),"-f","null","-"],capture_output=True,check=True,timeout=30)
        print(f"verified HTTP audio pairs: {len(pairs)}")

    def test_every_registered_video_pair_over_http_and_decodes(self):
        pairs=api.REGISTRY["video_pairs"];self.assertTrue(pairs)
        for pair in pairs:
            source=self.video_sources[pair["input"]]
            ctype,body=multipart("clip."+pair["input"],source,pair["output"])
            status,_,result=self.request("/api/convert",body,ctype)
            self.assertEqual(status,200,(pair,status,result[:200]))
            info=api.probe(result,require_registered_input=False);self.assertIsNotNone(info,pair)
            if pair["output"] in api.VIDEO_OUTPUTS:
                self.assertTrue(info["streams"]["video"]);self.assertEqual((info["width"],info["height"]),(96,64))
            else: self.assertTrue(info["streams"]["audio"])
            output=Path(self.directory/"verified-video-output.bin");output.write_bytes(result)
            subprocess.run(["ffmpeg","-v","error","-i",str(output),"-f","null","-"],capture_output=True,check=True,timeout=30)
        print(f"verified HTTP video/extraction pairs: {len(pairs)}")

    def test_rejects_bad_files_and_disabled_unverified_download(self):
        ctype,body=multipart("payload.exe",b"not media","PNG")
        status,_,_=self.request("/api/convert",body,ctype);self.assertIn(status,{415,422})
        enabled=api.ENABLE_PLATFORM_DOWNLOADS
        api.ENABLE_PLATFORM_DOWNLOADS=False
        try:
            status,_,data=self.request("/api/download/analyze",b'{"url":"https://example.com/video.mp4"}',"application/json")
        finally:
            api.ENABLE_PLATFORM_DOWNLOADS=enabled
        self.assertEqual(status,503);self.assertEqual(json.loads(data)["detail"]["code"],"downloader_unavailable")


if __name__=="__main__": unittest.main(verbosity=2)
