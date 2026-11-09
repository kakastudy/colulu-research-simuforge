# -*- coding: utf-8 -*-
"""直接下载 scipy wheel 并用 zipfile 解压到 tools/vendor。"""
import sys
import os
import urllib.request
import zipfile
import io

VENDOR = os.path.join(os.path.dirname(__file__), "vendor")
os.makedirs(VENDOR, exist_ok=True)

# scipy cp312 win_amd64 wheel URL（PyPI 稳定版）
WHEELS = [
    "https://files.pythonhosted.org/packages/1e/9a/7e1b0a3a0e3f3c3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3/scipy-1.14.1-cp312-cp312-win_amd64.whl",
]

# 用 PyPI JSON API 获取正确 URL
def get_wheel_url():
    import json
    url = "https://pypi.org/pypi/scipy/1.14.1/json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pip"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        for f in data["urls"]:
            if "cp312" in f["filename"] and "win_amd64" in f["filename"]:
                return f["url"], f["filename"]
    except Exception as e:
        print(f"JSON API failed: {e}")
    # fallback: try direct
    return None, None


def download_and_extract():
    url, fname = get_wheel_url()
    if url is None:
        print("Could not find scipy wheel URL")
        return False
    print(f"Downloading {fname} from {url[:80]}...")
    req = urllib.request.Request(url, headers={"User-Agent": "pip"})
    # chunked 读取 + 重试
    max_retries = 5
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                total = int(r.headers.get("Content-Length", 0))
                print(f"  Size: {total/1e6:.1f} MB, attempt {attempt+1}")
                buf = bytearray()
                while True:
                    chunk = r.read(1024*1024)  # 1MB chunks
                    if not chunk:
                        break
                    buf.extend(chunk)
                data = bytes(buf)
            print(f"Downloaded {len(data)/1e6:.1f} MB")
            break
        except Exception as e:
            print(f"  Retry {attempt+1} failed: {e}")
            if attempt == max_retries - 1:
                print("All retries failed")
                return False
    else:
        return False
    # 解压到 vendor
    zf = zipfile.ZipFile(io.BytesIO(data))
    for member in zf.namelist():
        zf.extract(member, VENDOR)
    print(f"Extracted to {VENDOR}")
    return True


if __name__ == "__main__":
    download_and_extract()
