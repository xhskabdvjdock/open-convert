"""Downloader policy unit tests; these do not claim any platform integration passed."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

API_DIR=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(API_DIR))
import ytdlp_worker as worker
import standalone as api


class YtDlpWorkerTests(unittest.TestCase):
    def test_options_are_derived_from_extractor_format_metadata(self):
        info={"formats":[
            {"format_id":"137","height":1080,"vcodec":"avc1","acodec":"none","tbr":4000},
            {"format_id":"136","height":720,"vcodec":"avc1","acodec":"none","tbr":2000},
            {"format_id":"140","vcodec":"none","acodec":"mp4a","abr":128},
        ]}
        options=worker.quality_options(info)
        self.assertEqual([x["key"] for x in options],["video:1080","video:720","audio:best"])
        self.assertTrue(all(x["has_audio"] for x in options))

    def test_format_selection_uses_only_returned_format_ids(self):
        info={"formats":[
            {"format_id":"137","height":1080,"vcodec":"avc1","acodec":"none","tbr":4000},
            {"format_id":"140","vcodec":"none","acodec":"mp4a","abr":128},
        ]}
        self.assertEqual(worker.pick_format(info,"video:1080"),"137+140")
        with self.assertRaises(ValueError): worker.pick_format(info,"video:2160")
        with self.assertRaises(ValueError): worker.pick_format(info,"137+140")

    def test_network_guard_rejects_loopback_without_fetching(self):
        command=[sys.executable,str(API_DIR/"ytdlp_worker.py")]
        result=subprocess.run(command,input=json.dumps({"mode":"analyze","url":"http://127.0.0.1:8000/"}).encode(),capture_output=True,timeout=10)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b"Restricted destination",result.stderr)

    def test_platform_errors_are_mapped_to_actionable_safe_messages(self):
        self.assertEqual(api.map_ytdlp_error("HTTP Error 429: Too Many Requests").code,"platform_rate_limited")
        self.assertEqual(api.map_ytdlp_error("Unsupported URL: https://example.invalid").code,"platform_unsupported")
        self.assertEqual(api.map_ytdlp_error("Sign in to confirm your age").code,"platform_restricted")
        self.assertEqual(api.map_ytdlp_error("Failed to resolve 'www.youtube.com'").code,"platform_network_error")
        self.assertEqual(api.map_ytdlp_error("[download] 20512.00kB is larger than max-filesize").code,"download_too_large")

    def test_public_youtube_and_x_video_urls_pass_url_validation(self):
        urls=[
            "https://www.youtube.com/watch?v=affZMZfn9xA",
            "https://x.com/Nostalgicmedias/status/2113541742280818791/video/1",
        ]
        for url in urls:
            self.assertEqual(api.validate_platform_url(url),url)

    def test_twitter_like_unknown_codecs_merge_video_with_audio(self):
        # Twitter/X HLS metadata: audio-only entries report acodec None while
        # vcodec is explicitly "none", and muxed http variants report both
        # codecs as unknown with a known height.
        info={"formats":[
            {"format_id":"hls-audio-128000","vcodec":"none","acodec":None,"abr":128,"protocol":"m3u8_native"},
            {"format_id":"http-2176","vcodec":None,"acodec":None,"height":548,"protocol":"https"},
            {"format_id":"hls-566","vcodec":"avc1.64001E","acodec":"none","height":548,"protocol":"m3u8_native"},
            {"format_id":"hls-312","vcodec":"avc1.4D4015","acodec":"none","height":360,"protocol":"m3u8_native"},
        ]}
        options=worker.quality_options(info)
        self.assertEqual([o["key"] for o in options],["video:548","video:360","audio:best"])
        self.assertTrue(all(o["has_audio"] for o in options))
        self.assertEqual(worker.pick_format(info,"video:548"),"hls-566+hls-audio-128000")
        self.assertEqual(worker.pick_format(info,"audio:best"),"hls-audio-128000")

    def test_video_only_height_falls_back_to_pure_video_stream(self):
        # A platform that returns video heights without any audio stream still
        # selects the best video-only format for a requested height.
        info={"formats":[{"format_id":"v333","vcodec":"avc1","acodec":"none","height":333}]}
        options=worker.quality_options(info)
        self.assertEqual([o["key"] for o in options],["video:333"])
        self.assertEqual([o["has_audio"] for o in options],[False])
        self.assertEqual(worker.pick_format(info,"video:333"),"v333")

    def test_worker_error_marker_survives_dependency_stderr_noise(self):
        stderr=b"warning from downloader\nOPENCONVERT_ERROR:{\"error\":\"extract failed\",\"error_type\":\"ExtractorError\"}\n"
        failure=api.parse_worker_failure(stderr)
        self.assertEqual(failure["error_type"],"ExtractorError")
        self.assertEqual(failure["error"],"extract failed")


if __name__=="__main__": unittest.main(verbosity=2)
