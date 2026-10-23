#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TVBox Python 爬虫 - 95da.com
"""

import sys
sys.path.append("..")

import re
import json
import base64
import urllib.parse

try:
    from base.spider import Spider
except Exception:
    class Spider:
        def __init__(self):
            pass
        def fetch(self, url, headers=None, **kwargs):
            import requests
            return requests.get(url, headers=headers or {}, timeout=15, verify=False)
        def post(self, url, data=None, headers=None, **kwargs):
            import requests
            return requests.post(url, data=data, headers=headers or {}, timeout=15, verify=False)

class Spider(Spider):
    pass

MIRROR_DOMAINS = [
    "https://eyr.539582.xyz",
    "https://hib.686235.xyz",
    "https://cba.395923.xyz",
]

CATEGORIES = [
    ("20010496", "强奸迷奸"), ("20020496", "亚洲媚黑"), ("20030496", "国产传媒"),
    ("20040496", "外围探花"), ("20050496", "大神作品"), ("20060496", "夫妻交换"),
    ("20070496", "直播大秀"), ("20080496", "绿帽淫妻"), ("20090496", "网黄女神"),
    ("20100496", "良家人妻"), ("20110496", "国产精品"), ("20120496", "近亲乱伦"),
    ("20130496", "日韩伦理"), ("20140496", "港台三级"), ("20150496", "情侣泄密"),
    ("20160496", "浴室偷拍"), ("20170496", "酒店偷拍"), ("20180496", "女性按摩"),
    ("20190496", "街拍抄底"), ("20200496", "家庭监控"), ("20210496", "激情艳舞"),
    ("20220496", "模特私拍"), ("20230496", "裸贷裸条"), ("20240496", "字母调教"),
    ("20250496", "捆绑绳艺"), ("20260496", "变态重口"), ("20270496", "户外露出"),
    ("20280496", "男女直播"), ("20290496", "学妹直播"), ("20300496", "美女直播"),
    ("20310496", "户外直播"), ("20320496", "淫乱直播"), ("20330496", "直播精品"),
    ("20340496", "TSCD变性"), ("20350496", "丝足诱惑"), ("20360496", "厕拍偷拍"),
    ("20370496", "成人动漫"), ("20380496", "网红流出"), ("20390496", "金主定制"),
    ("20400496", "k福利姬"),
    ("19920497", "国产磁力"), ("19930497", "日本磁力"), ("19940497", "日本无码"),
    ("19950497", "欧美色情"), ("19960497", "传媒作品"), ("19970497", "探花直播"),
    ("19980497", "网黄女神磁力"), ("19990497", "绿帽淫妻磁力"),
]

# ⚠️ 关键修复：彻底移除 Accept-Encoding！
# TVBox 的 fetch 不会自动解压 gzip，如果带上这个头，
# 服务器返回 gzip 压缩数据，播放器拿到二进制垃圾直接黑屏。
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_active_mirror = None


def _decode_page(html_text):
    """解码 JS 混淆页面"""
    try:
        match = re.search(
            r"function\s+\w+\(\w+\)\s*\{"
            r".*?window\.atob\(\w+\).*?"
            r"decodeURIComponent\(escape\(\w+\)\).*?"
            r"return\s+\w+;\s*\}"
            r'\s*var\s+\w+\s*=\s*\w+\(\'(.*?)\'\s*\.\s*split',
            html_text,
            re.DOTALL,
        )
        if not match:
            return None
        raw_reversed = match.group(1)
        b64_str = raw_reversed[::-1]
        decoded_bytes = base64.b64decode(b64_str)
        try:
            return decoded_bytes.decode("utf-8")
        except UnicodeDecodeError:
            percent_str = "".join(
                chr(b) if b < 128 else "%%%02X" % b for b in decoded_bytes
            )
            return urllib.parse.unquote(percent_str, encoding="utf-8")
    except Exception:
        return None


def _extract_j_b64(text):
    """提取 j_b64 JSON"""
    match = re.search(r"j_b64\s*=\s*'([^']+)'", text)
    if not match:
        return None
    try:
        json_str = base64.b64decode(match.group(1)).decode("utf-8")
        return json.loads(json_str)
    except Exception:
        return None


def _fetch_and_decode(self, url):
    """获取并解码页面"""
    try:
        r = self.fetch(url, headers=HEADERS)
        html = r.text if hasattr(r, "text") else r.content.decode("utf-8")
    except Exception:
        return None
    decoded = _decode_page(html)
    if not decoded:
        return None
    return _extract_j_b64(decoded)


def _get_active_mirror(self):
    """探测可用镜像"""
    global _active_mirror
    if _active_mirror:
        try:
            data = _fetch_and_decode(self, _active_mirror + "/")
            if data and "l" in data:
                return _active_mirror
        except Exception:
            pass
        _active_mirror = None

    for mirror in MIRROR_DOMAINS:
        try:
            data = _fetch_and_decode(self, mirror + "/")
            if data and "l" in data:
                _active_mirror = mirror
                return mirror
        except Exception:
            continue

    _active_mirror = MIRROR_DOMAINS[0]
    return _active_mirror


def _build_url(self, path):
    """构建完整 URL"""
    if not path:
        return ""
    if path.startswith("http"):
        return path
    mirror = _get_active_mirror(self)
    return mirror + path if path.startswith("/") else mirror + "/" + path


class Spider(Spider):

    def init(self, ext=""):
        pass

    def destroy(self):
        pass

    def getName(self):
        return "95da.com"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter=False):
        result = {"class": [], "filters": {}}
        for cid, name in CATEGORIES:
            result["class"].append({"type_id": cid, "type_name": name})
        try:
            mirror = _get_active_mirror(self)
            data = _fetch_and_decode(self, mirror + "/")
            if data and "l" in data:
                videos = []
                for section_list in data["l"].values():
                    for item in section_list:
                        url = item.get("url", "")
                        if not url:
                            continue
                        vod_id = url.strip("/")
                        videos.append({
                            "vod_id": vod_id,
                            "vod_name": item.get("title", ""),
                            "vod_pic": item.get("pic", ""),
                            "vod_remarks": "磁力" if "torrent" in url else "在线",
                        })
                seen = set()
                unique = []
                for v in videos:
                    if v["vod_id"] not in seen:
                        seen.add(v["vod_id"])
                        unique.append(v)
                result["list"] = unique
        except Exception:
            result["list"] = []
        return result

    def homeVideoContent(self):
        result = {"list": []}
        try:
            mirror = _get_active_mirror(self)
            data = _fetch_and_decode(self, mirror + "/")
            if data and "l" in data:
                seen = set()
                for section_list in data["l"].values():
                    for item in section_list:
                        url = item.get("url", "")
                        if not url:
                            continue
                        vod_id = url.strip("/")
                        if vod_id in seen:
                            continue
                        seen.add(vod_id)
                        result["list"].append({
                            "vod_id": vod_id,
                            "vod_name": item.get("title", ""),
                            "vod_pic": item.get("pic", ""),
                            "vod_remarks": "磁力" if "torrent" in url else "在线",
                        })
        except Exception:
            pass
        return result

    def categoryContent(self, tid, pg, filter=False, extend=None):
        result = {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}
        try:
            page = int(pg) if pg else 1
            mirror = _get_active_mirror(self)
            url = f"{mirror}/list/{tid}-{page}.html"
            data = _fetch_and_decode(self, url)
            if not data:
                return result
            video_list = []
            if "l" in data:
                for section_list in data["l"].values():
                    for item in section_list:
                        url_path = item.get("url", "")
                        if not url_path:
                            continue
                        vod_id = url_path.strip("/")
                        video_list.append({
                            "vod_id": vod_id,
                            "vod_name": item.get("title", ""),
                            "vod_pic": item.get("pic", ""),
                            "vod_remarks": "磁力" if "torrent" in url_path else "在线",
                        })
            seen = set()
            unique = []
            for v in video_list:
                if v["vod_id"] not in seen:
                    seen.add(v["vod_id"])
                    unique.append(v)
            result["list"] = unique
            if "p" in data:
                p = data["p"]
                result["page"] = int(p.get("c", page)) if p.get("c") is not None else page
                result["pagecount"] = int(p.get("t", 1)) if p.get("t") is not None else 1
                result["total"] = int(p.get("s", len(unique))) if p.get("s") is not None else len(unique)
            else:
                result["page"] = page
                result["pagecount"] = page
                result["total"] = len(unique)
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        result = {"list": []}
        vod_id = ids[0] if isinstance(ids, list) else ids
        try:
            mirror = _get_active_mirror(self)
            if "torrent" in vod_id:
                url = f"{mirror}/{vod_id}"
                data = _fetch_and_decode(self, url)
                if not data:
                    return result
                title = data.get("name", "")
                magnet = data.get("tm", "")
                torrent_url = data.get("tt", "")
                cover = ""
                tc = data.get("tc", "")
                if tc:
                    img_match = re.search(r'<img\s+src="([^"]+)"', tc)
                    if img_match:
                        cover = _build_url(self, img_match.group(1))
                play_parts = []
                if magnet:
                    play_parts.append(f"磁力播放${magnet}")
                if torrent_url:
                    play_parts.append(f"种子下载${_build_url(self, torrent_url)}")
                vod_play_url = "#".join(play_parts) if play_parts else ""
                result["list"] = [{
                    "vod_id": vod_id,
                    "vod_name": title,
                    "vod_pic": cover,
                    "vod_play_from": "95da",
                    "vod_play_url": vod_play_url,
                    "vod_content": f"文件大小: {data.get('ts', '未知')} | 分辨率: {data.get('tr', '未知')}",
                }]
            else:
                url = f"{mirror}/{vod_id}"
                data = _fetch_and_decode(self, url)
                if not data:
                    return result
                title = data.get("name", "")
                m3u8_url = _build_url(self, data.get("m3", ""))
                cover = _build_url(self, data.get("co", ""))
                cn = data.get("cn", "")
                try:
                    decoded_cn = base64.b64decode(cn).decode("utf-8")
                    if decoded_cn:
                        cn = decoded_cn
                except Exception:
                    pass
                play_from_list = []
                play_url_list = []
                seen_names = set()
                if m3u8_url:
                    play_from_list.append("95da")
                    play_url_list.append(f"正片${m3u8_url}")
                    seen_names.add("95da")
                cdn_list = data.get("cdn", [])
                for i, cdn in enumerate(cdn_list):
                    cdn_url = _build_url(self, cdn.get("url", ""))
                    cdn_name = cdn.get("name", f"线路{i+1}")
                    if cdn_name in seen_names:
                        cdn_name = f"{cdn_name}-{i+1}"
                    seen_names.add(cdn_name)
                    if cdn_url:
                        play_from_list.append(cdn_name)
                        play_url_list.append(f"正片${cdn_url}")
                vod_play_from = "$$$".join(play_from_list) if play_from_list else ""
                vod_play_url = "$$$".join(play_url_list) if play_url_list else ""
                result["list"] = [{
                    "vod_id": vod_id,
                    "vod_name": title,
                    "vod_pic": cover,
                    "vod_year": "",
                    "vod_area": "",
                    "type_name": cn,
                    "vod_play_from": vod_play_from,
                    "vod_play_url": vod_play_url,
                    "vod_content": "",
                }]
        except Exception:
            pass
        return result

    def searchContent(self, key, quick, pg=1):
        result = {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}
        try:
            page = int(pg) if pg else 1
            mirror = _get_active_mirror(self)
            content_b64 = base64.b64encode(key.encode("utf-8")).decode("utf-8")
            if page <= 1:
                url = f"{mirror}/search.php?content={content_b64}&type=1"
            else:
                first_url = f"{mirror}/search.php?content={content_b64}&type=1"
                first_data = _fetch_and_decode(self, first_url)
                if not first_data:
                    return result
                ci = first_data.get("ci", "")
                if not ci:
                    return result
                url = f"{mirror}/list/{ci}-{page}.html"
            data = _fetch_and_decode(self, url)
            if not data:
                return result
            video_list = []
            if "l" in data:
                for section_list in data["l"].values():
                    for item in section_list:
                        url_path = item.get("url", "")
                        if not url_path:
                            continue
                        vod_id = url_path.strip("/")
                        video_list.append({
                            "vod_id": vod_id,
                            "vod_name": item.get("title", ""),
                            "vod_pic": item.get("pic", ""),
                            "vod_remarks": "磁力" if "torrent" in url_path else "在线",
                        })
            seen = set()
            unique = []
            for v in video_list:
                if v["vod_id"] not in seen:
                    seen.add(v["vod_id"])
                    unique.append(v)
            result["list"] = unique
            if "p" in data:
                p = data["p"]
                result["page"] = int(p.get("c", page)) if p.get("c") is not None else page
                result["pagecount"] = int(p.get("t", 1)) if p.get("t") is not None else 1
                result["total"] = int(p.get("s", len(unique))) if p.get("s") is not None else len(unique)
        except Exception:
            pass
        return result

    def playerContent(self, flag, id, vipFlags):
        # header 必须是合法 JSON 字符串，绝不能用 ""
        result = {"parse": 0, "header": "{}", "url": "", "playUrl": ""}
        try:
            if not id:
                return result
            mirror = _get_active_mirror(self)
            # ⚠️ 播放专用头：只带 User-Agent + Referer，绝不再带 Accept-Encoding
            play_headers = {
                "User-Agent": HEADERS["User-Agent"],
                "Referer": mirror + "/",
            }
            if id.startswith("torrent:"):
                result["url"] = id[len("torrent:"):]
                result["parse"] = 0
                result["header"] = json.dumps(play_headers)
                return result
            if id.startswith("magnet:"):
                result["url"] = id
                result["parse"] = 0
                result["header"] = json.dumps(play_headers)
                return result
            # CDN API -> 请求获取 m3u8（必须在 .m3u8 判断之前）
            if "api.php" in id:
                try:
                    r = self.fetch(id, headers=play_headers)
                    resp_text = r.text if hasattr(r, "text") else r.content.decode("utf-8")
                    try:
                        resp_json = json.loads(resp_text)
                        m3u8 = resp_json.get("m3u8Url") or resp_json.get("url") or resp_json.get("m3u8") or resp_json.get("play", "")
                        if m3u8:
                            if not m3u8.startswith("http"):
                                m3u8 = _build_url(self, m3u8)
                            result["url"] = m3u8
                            result["parse"] = 0
                            result["header"] = json.dumps(play_headers)
                            return result
                    except json.JSONDecodeError:
                        pass
                    if resp_text.strip().startswith("http"):
                        result["url"] = resp_text.strip()
                        result["parse"] = 0
                        result["header"] = json.dumps(play_headers)
                        return result
                except Exception:
                    pass
                result["url"] = id
                result["parse"] = 0
                result["header"] = json.dumps(play_headers)
                return result
            if ".m3u8" in id:
                result["url"] = id
                result["parse"] = 0
                result["header"] = json.dumps(play_headers)
                return result
            result["url"] = id
            result["parse"] = 0
            result["header"] = json.dumps(play_headers)
        except Exception:
            result["url"] = id
            result["parse"] = 0
            result["header"] = json.dumps({"User-Agent": HEADERS["User-Agent"]})
        return result

    def localProxy(self, param):
        return [200, "video/MP2T", "", ""]


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    spider = Spider()
    spider.init()
    print("=" * 60)
    print("1. homeContent")
    home = spider.homeContent()
    print(f"   分类: {len(home.get('class', []))}, 推荐: {len(home.get('list', []))}")
    print("\n2. categoryContent")
    cat = spider.categoryContent("20110496", "1")
    print(f"   列表: {len(cat.get('list', []))}")
    print("\n3. detailContent")
    if cat.get("list"):
        detail = spider.detailContent([cat["list"][0]["vod_id"]])
        if detail.get("list"):
            d = detail["list"][0]
            print(f"   标题: {d.get('vod_name', '')[:30]}")
            print(f"   源: {d.get('vod_play_from', '')}")
            print(f"   URL: {d.get('vod_play_url', '')[:80]}")
    print("\n4. searchContent")
    search = spider.searchContent("国产", False)
    print(f"   结果: {len(search.get('list', []))}")
    print("\n5. playerContent")
    if detail.get("list"):
        play_url = detail["list"][0].get("vod_play_url", "")
        play_from = detail["list"][0].get("vod_play_from", "")
        if play_url and play_from:
            sources = play_from.split("$$$")
            urls = play_url.split("$$$")
            for i, src in enumerate(sources):
                if i < len(urls):
                    ep_url = urls[i].split("#")[0].split("$", 1)[1] if "$" in urls[i].split("#")[0] else ""
                    player = spider.playerContent(src, ep_url, "")
                    print(f"   [{src}] parse={player.get('parse')} url={player.get('url', '')[:60]}...")
    print("\n测试完成!")
