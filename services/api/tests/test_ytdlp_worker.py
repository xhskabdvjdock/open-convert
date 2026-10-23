"""Downloader policy unit tests; these do not claim any platform integration passed."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

API_DIR=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(API_DIR))
import ytdlp_worker as worker


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


if __name__=="__main__": unittest.main(verbosity=2)
