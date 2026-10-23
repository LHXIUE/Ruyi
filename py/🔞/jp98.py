#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jp98 影视 (苹果CMS V10 · XML协议) - 全家桶格式版
=================================================
TVBox / TVBoxOSC / FongMi / 影视仓 / PyramidStore 通用 Python 爬虫源
按「麦田全家桶爬虫格式规范」编写（模板基线: 麦田app.py）：

  · class Spider 继承 base.spider.Spider（try/except ImportError 兜底），
    实现统一接口清单：init / getName / homeContent / homeVideoContent /
    categoryContent / detailContent / searchContent / searchContentPage /
    playerContent / isVideoFormat / manualVideoCheck / localProxy；
  · 接口返回标准 dict 字段；封面走本地代理；
  · 默认必带筛选器（type_extend 真筛选，缺省年份兜底）；
  · 零第三方依赖：HTTP 用标准库 urllib（XML 纯 REST 无加密），
    XML 解析用标准库 xml.etree.ElementTree。

站点协议（苹果CMS V10 逆向核对 2026-10-21，真实抓包验证）：
  · ext = 苹果CMS API 根地址（https://jp98.vip/api.php/provide/vod/at/xml/）；
  · 服务器默认返回 gzip，已在 HTTP 层自动解压；
  · 端点（query string 形式，统一用 ac=detail 取列表以带回封面 pic）：
      GET {api}                  → <class>(分类) + <list>(最新列表,无 pic,仅供 homeContent 取分类)
      GET {api}?ac=detail&pg=    → 首页最新列表(含 pic + 分页属性)
      GET {api}?ac=detail&t=<tid>&pg=  → 分类列表(含 pic,<list>分页)
      GET {api}?ac=detail&ids=<id>     → 详情(含 pic/lang/area/year/actor/des/dl)
      GET {api}?ac=detail&wd=<kw>&pg=  → 搜索列表(含 pic)
    注: 该站 ac=list 列表项不含 <pic>, 故列表类接口统一改用 ac=detail 以带回封面。
  · 返回结构:
      <rss version="5.1">
        <class><ty id="20">国产自拍</ty>...</class>
        <list page="1" pagecount="134" pagesize="20" recordcount="2667">
          <video><id/><tid/><name/><type/><pic/><note/>...</video>
        </list>
      </rss>
  · 详情播放串: <dl><dd flag="线路名">第01集$url#第02集$url</dd></dl>
  · UA: okhttp/4.9.3；
  · 播放: 详情里 dd 文本已是 "集$直链" 串，多为 m3u8 直链 => parse:0；
    非直链再走 NBY 备用解析池，全挂交播放器。

对接（TVBox sites 配置）：
    {"key":"jp98","name":"jp98影视","type":3,"api":"./jp98.py",
     "searchable":1,"quickSearch":1,"filterable":1,
     "ext":"https://jp98.vip/api.php/provide/vod/at/xml/"}
    （ext 填 API 根地址即可；留空用内置默认）
"""

import os
import re
import sys
import json
import time
import gzip
import zlib
import codecs

import ssl
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from urllib.parse import quote

try:
    sys.path.append("../../")
except Exception:
    pass
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def init(self, extend=""):
            pass


# ============================================================================
# 0. 图片魔数判定 / 默认筛选器（全家桶模板级组件）
# ============================================================================
def detect_image_mime(data) -> str:
    if not data:
        return "application/octet-stream"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] in (b"GIF8",):
        return "image/gif"
    return "application/octet-stream"


def build_default_filters() -> list:
    current_year = int(time.strftime("%Y"))
    years = [{"n": "全部", "v": ""}]
    for y in range(current_year, current_year - 11, -1):
        years.append({"n": str(y), "v": str(y)})
    return [
        {"key": "year", "name": "年份", "value": years},
    ]


# ============================================================================
# 1. 零依赖 HTTP 客户端（仅标准库，含 gzip/deflate 自动解压）
# ============================================================================
_HTTP_INSECURE_CTX = None
try:
    _HTTP_INSECURE_CTX = ssl._create_unverified_context()
except Exception:
    _HTTP_INSECURE_CTX = None


def _http_request(method, url, headers=None, data=None, timeout=15, verify=True):
    req = urllib.request.Request(url, headers=headers or {}, data=data, method=method)
    ctx = None if verify else _HTTP_INSECURE_CTX
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        body = resp.read()
        enc = (resp.headers.get("Content-Encoding", "") or "").lower()
        if enc == "gzip":
            body = gzip.decompress(body)
        elif enc == "deflate":
            body = zlib.decompress(body)
        return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            enc = (e.headers.get("Content-Encoding", "") or "").lower()
            if enc == "gzip":
                body = gzip.decompress(body)
            elif enc == "deflate":
                body = zlib.decompress(body)
        except Exception:
            pass
        return e.code, body


# ============================================================================
# 2. Spider 主体（全家桶标准接口）
# ============================================================================
_PLAY_UA = ("Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")

_V6_UA = "okhttp/4.9.3"

_LOCAL_PROXY_PREFIX = "http://127.0.0.1:9978/proxy?do=py&action=proxy"

# 直链判断(jar 同款: .*(m3u8|mp4|mkv).* )
_DIRECT_RE = re.compile(r"(m3u8|mp4|mkv|flv|ts|avi|webm)", re.I)


class Spider(Spider):
    """jp98 影视（苹果CMS V10 · XML协议）全家桶格式爬虫源"""

    # 聚合搜索配置(全家桶约定)
    searchable = 1
    quickSearch = 1
    filterable = 1
    changeable = 1

    def __init__(self):
        self.api = ""
        self.headers = {
            "User-Agent": _V6_UA,
            "Accept-Encoding": "gzip, deflate",
        }
        self.last_init_error = ""

    def getName(self):
        return "jp98影视"

    # API 根地址(2026-10-21 实测可用; ext 传入时以 ext 为准)
    DEFAULT_EXT = "https://jp98.vip/api.php/provide/vod/at/xml/"

    def init(self, extend=""):
        self.last_init_error = ""
        ext = (extend or "").strip()
        if not ext:
            ext = self.DEFAULT_EXT
        if ext.startswith("{"):
            try:
                j = json.loads(ext)
                ext = str(j.get("api") or j.get("host") or "").strip()
            except Exception:
                pass
        if not ext.startswith(("http://", "https://")):
            self.api = ""
            self.last_init_error = "苹果CMS ext需为API根地址"
            return
        ext = ext.rstrip("/")
        # 兼容只给到 /provide/vod 的情况, 自动补 at/xml
        if "/provide/vod" in ext and not ext.endswith("/at/xml"):
            ext = ext.split("/provide/vod")[0] + "/provide/vod/at/xml"
        self.api = ext

    # -------- 苹果CMS XML 请求/解析 --------
    def _get_xml(self, query):
        if not self.api:
            raise RuntimeError(self.last_init_error or "苹果CMS init失败")
        url = self.api + "?" + query
        status, body = _http_request("GET", url, headers=self.headers,
                                     timeout=15, verify=False)
        if status >= 400:
            raise RuntimeError("苹果CMS HTTP %s" % status)
        try:
            return ET.fromstring(body)
        except Exception as e:
            text = body.decode("utf-8", "replace")
            a = text.find("<rss")
            if a >= 0:
                return ET.fromstring(text[a:])
            raise

    def _video_list(self, root):
        lst = root.find("list") if root is not None else None
        if lst is None:
            return []
        return lst.findall("video")

    # -------- 全家桶标准接口 --------
    def homeContent(self, filter=False):
        try:
            root = self._get_xml("")
            classes, filters = [], {}
            cls = root.find("class")
            if cls is not None:
                for ty in cls.findall("ty"):
                    tid = (ty.get("id") or "").strip()
                    name = (ty.text or "").strip()
                    if not tid or not name:
                        continue
                    if ("直播" in name) or ("电视直播" in name):
                        continue
                    classes.append({"type_id": tid, "type_name": name})
                    if filter:
                        filters[tid] = build_default_filters()
            return {"class": classes, "filters": filters if filter else {}, "list": []}
        except Exception as e:
            return {"list": [], "msg": str(e)}

    def homeVideoContent(self):
        try:
            # 用 ac=detail 取首页最新, 带回封面 pic
            root = self._get_xml("ac=detail&pg=1")
            return {"list": self._parse_vod_list(root)}
        except Exception as e:
            return {"list": [], "msg": str(e)}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            extend = extend if isinstance(extend, dict) else {}
            # ac=detail 列表项含 pic(封面), 比 ac=list 更完整
            params = "ac=detail&t=%s&pg=%s" % (tid, pg or 1)
            # 苹果CMS 支持 class/area/lang/year 二级筛选(跟随延伸参数)
            for k in ("class", "area", "lang", "year"):
                v = str(extend.get(k, "") or "")
                if v:
                    params += "&%s=%s" % (k, quote(v, safe=""))
            root = self._get_xml(params)
            lst = root.find("list")
            page = int((lst.get("page", pg or 1) if lst is not None else pg or 1) or pg or 1)
            pagecount = int((lst.get("pagecount", 0) if lst is not None else 0) or 0)
            limit = int((lst.get("pagesize", 20) if lst is not None else 20) or 20)
            total = int((lst.get("recordcount", 0) if lst is not None else 0) or 0)
            return {
                "list": self._parse_vod_list(root),
                "page": page,
                "pagecount": pagecount or 9999,
                "limit": limit,
                "total": total or (pagecount or 9999) * limit,
            }
        except Exception as e:
            return {"list": [], "page": int(pg or 1), "pagecount": 1,
                    "limit": 20, "total": 0, "msg": str(e)}

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
            root = self._get_xml("ac=detail&ids=%s" % quote(str(vod_id), safe=""))
            v = root.find("list/video")
            if v is None:
                return {"list": [], "msg": "苹果CMS detail空"}
            vod = {
                "vod_id": (v.findtext("id") or str(vod_id)).strip(),
                "vod_name": (v.findtext("name") or "").strip(),
                "vod_pic": self._cover_url(v.findtext("pic") or ""),
                "vod_remarks": (v.findtext("note") or "").strip(),
            }
            for k, fld in (("vod_year", "year"), ("vod_area", "area"),
                           ("vod_lang", "lang"), ("vod_actor", "actor"),
                           ("vod_director", "director")):
                val = (v.findtext(fld) or "").strip()
                if val:
                    vod[k] = val
            des = (v.findtext("des") or v.findtext("desc") or "").strip()
            if des:
                vod["vod_content"] = des
            dl = v.find("dl")
            froms, urls = [], []
            if dl is not None:
                for dd in dl.findall("dd"):
                    flag = (dd.get("flag") or "").strip() or "默认"
                    text = (dd.text or "").strip()
                    if not text:
                        continue
                    # dd 文本已是 集数$直链#集数$直链, 直接作为该线路播放串
                    froms.append(flag)
                    urls.append(text)
            if froms:
                vod["vod_play_from"] = "$$$".join(froms)
                vod["vod_play_url"] = "$$$".join(urls)
            return {"list": [vod]}
        except Exception as e:
            return {"list": [], "msg": str(e)}

    def searchContent(self, key, quick=False, pg=1):
        try:
            # ac=detail 列表项含 pic(封面)
            root = self._get_xml("ac=detail&wd=%s&pg=%s" % (quote(str(key), safe=""), pg or 1))
            return {"list": self._parse_vod_list(root)}
        except Exception as e:
            return {"list": [], "msg": str(e)}

    def searchContentPage(self, key, quick=False, pg=1):
        return self.searchContent(key, quick, pg)

    def playerContent(self, flag, pid, vipFlags=None):
        pid = str(pid or "")
        if not pid:
            return {"parse": 0, "playUrl": "", "url": "", "header": ""}
        # ① 直链(jar 同款正则: m3u8/mp4/mkv/...)
        if pid.startswith(("http://", "https://")) and _DIRECT_RE.search(pid):
            return {"parse": 0, "playUrl": "", "url": pid,
                    "header": json.dumps({"User-Agent": _PLAY_UA})}
        # ② 非直链走备用解析池
        if pid.startswith(("http://", "https://")):
            for fb in self._fallback_apis():
                try:
                    url = self._resolve_parse(fb, pid)
                    if url:
                        return {"parse": 0, "playUrl": "", "url": url,
                                "header": json.dumps({"User-Agent": _PLAY_UA})}
                except Exception:
                    continue
            return {"parse": 1, "playUrl": "", "url": pid, "header": ""}
        return {"parse": 1, "playUrl": "", "url": pid, "header": ""}

    _DEFAULT_PARSE_FALLBACK = [
        "https://api.nbyjson.top:7788/api/?key=4yyLz4SGC9RPLOl6E1&url=",
    ]

    @staticmethod
    def _host_of(api):
        m = re.match(r"^https?://([^/:]+)", str(api or ""))
        return m.group(1) if m else ""

    def _fallback_apis(self):
        out = []
        for u in self._DEFAULT_PARSE_FALLBACK:
            u = str(u).strip()
            if u.startswith(("http://", "https://")):
                out.append(u)
        return out

    def _resolve_parse(self, parse_api, play_id):
        api = str(parse_api or "")
        if not api:
            return ""
        if api.endswith("="):
            target = api + quote(play_id, safe="")
        else:
            sep = "&" if "?" in api else "?"
            target = api + sep + "url=" + quote(play_id, safe="")
        status, body = _http_request("GET", target, headers={"User-Agent": _PLAY_UA},
                                     timeout=20, verify=False)
        text = body.decode("utf-8", "replace") or ""
        try:
            obj = json.loads(text)
        except Exception:
            obj = None
        url = self._pick_url(obj) or self._extract_play_url(text)
        # 解析站返回站根落地页不是直链, 视为失败
        if url and re.match(r"^https?://[^/]+/?$", url):
            url = ""
        return url

    @staticmethod
    def _pick_url(obj):
        if isinstance(obj, str):
            return obj if obj.startswith(("http://", "https://")) else ""
        if isinstance(obj, list):
            for x in obj:
                u = Spider._pick_url(x)
                if u:
                    return u
            return ""
        if not isinstance(obj, dict):
            return ""
        for k in ("url", "play_url", "source_url", "videoUrl", "video_url"):
            v = obj.get(k)
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                return v
        for v in obj.values():
            u = Spider._pick_url(v)
            if u:
                return u
        return ""

    @staticmethod
    def _extract_play_url(text):
        m = re.search(r'https?://[^\s"\'\<>]+\.(?:m3u8|mp4|mkv|flv)(?:\?[^\s"\'\<>]*)?',
                      str(text or ""))
        return m.group(0) if m else ""

    # -------- 解析辅助 --------
    def _cover_url(self, pic):
        # 该站图床 98jpg1.vip 可直连(实测 HTTP200/无需 Referer),
        # 直接返回真实 URL 由壳子加载, 避免依赖本地代理(127.0.0.1:9978)。
        pic = str(pic or "").strip()
        if not pic:
            return ""
        if pic.startswith(("http://", "https://")):
            return pic
        return "http://" + pic.lstrip("/")

    def _parse_vod_list(self, root):
        out = []
        for v in self._video_list(root):
            out.append({
                "vod_id": (v.findtext("id") or "").strip(),
                "vod_name": (v.findtext("name") or "").strip(),
                "vod_pic": self._cover_url(v.findtext("pic") or ""),
                "vod_remarks": (v.findtext("note") or "").strip(),
            })
        return out

    # -------- 全家桶附加接口 --------
    def isVideoFormat(self, url):
        if not url or not isinstance(url, str):
            return False
        if not url.startswith("http"):
            return False
        return bool(_DIRECT_RE.search(url))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        def _first(v):
            if isinstance(v, list):
                return v[0].strip() if v and v[0] else ""
            return (v or "").strip()

        url = _first(param.get('url'))
        ptype = _first(param.get('type'))
        headers = {"User-Agent": _PLAY_UA}
        try:
            if ptype == 'cover' or (url and re.search(r"\.(jpg|jpeg|png|webp|gif)(\?|$)", url, re.I)):
                status, body = _http_request("GET", url, headers=headers,
                                             timeout=10, verify=False)
                if status == 200 and body:
                    return [200, detect_image_mime(body), body]
                return [404, "text/plain", b"cover not found"]
            if ptype == 'm3u8' or (url and '.m3u8' in url):
                status, body = _http_request("GET", url, headers=headers,
                                             timeout=15, verify=False)
                return [200, "application/vnd.apple.mpegurl", body.decode("utf-8", "replace")]
            if ptype == 'media':
                status, body = _http_request("GET", url, headers=headers,
                                             timeout=15, verify=False)
                return [206, "application/octet-stream", body]
            status, body = _http_request("GET", url, headers=headers,
                                         timeout=15, verify=False)
            return [200, "text/plain", body.decode("utf-8", "replace")]
        except Exception as e:
            return [500, "text/plain", str(e)]


# ============================================================================
# 模块级函数转发层（兼容 webhome / 部分 OK影视 / 影视仓 的模块级加载）
# ============================================================================
_spider_instance = None


def _get_spider():
    global _spider_instance
    if _spider_instance is None:
        _spider_instance = Spider()
        _spider_instance.init()
    return _spider_instance


def getName():
    return _get_spider().getName()


def init(extend=""):
    return _get_spider().init(extend)


def homeContent(filter=False):
    return _get_spider().homeContent(filter)


def homeVideoContent():
    return _get_spider().homeVideoContent()


def categoryContent(tid, pg, filter=False, extend=None):
    return _get_spider().categoryContent(tid, pg, filter, extend)


def detailContent(ids):
    return _get_spider().detailContent(ids)


def playerContent(flag, pid, vip_flags=None):
    return _get_spider().playerContent(flag, pid, vip_flags)


def searchContent(key, quick=False, pg=1):
    return _get_spider().searchContent(key, quick, pg)


def isVideoFormat(url):
    return _get_spider().isVideoFormat(url)


def manualVideoCheck():
    return _get_spider().manualVideoCheck()


def localProxy(param):
    return _get_spider().localProxy(param)


# ============================================================================
# 离线自检（python jp98.py）
# ============================================================================
if __name__ == "__main__":
    print("===== jp98 苹果CMS V10 XML 自检 =====")
    assert detect_image_mime(b'\xff\xd8\xff\xe0') == 'image/jpeg'
    assert detect_image_mime(b'\x89PNG\r\n\x1a\n') == 'image/png'
    assert build_default_filters() and build_default_filters()[0]["key"] == "year"
    print("[mime/filters] ok")
    sp = Spider()
    sp.init("")
    print("[OK] init:", sp.getName(), "| api:", sp.api)
    cover = sp._cover_url("https://98jpg1.vip/a.jpg")
    assert cover == "https://98jpg1.vip/a.jpg", cover
    print("[OK] 封面直链:", cover)
    assert sp._cover_url("//x.y/b.jpg") == "http://x.y/b.jpg"
    # XML 解析静态测试(模拟真实结构)
    sample = ('<?xml version="1.0" encoding="utf-8"?>'
              '<rss version="5.1">'
              '<list page="1" pagecount="2" pagesize="20" recordcount="40">'
              '<video><id>1</id><name>测试影片</name><pic>https://x/y.jpg</pic>'
              '<note>高清</note></video></list>'
              '<class><ty id="20">国产自拍</ty><ty id="56">日本无码</ty></class>'
              '</rss>')
    root = ET.fromstring(sample)
    vl = sp._parse_vod_list(root)
    assert vl and vl[0]["vod_name"] == "测试影片", vl
    print("[OK] XML列表解析:", [v["vod_name"] for v in vl])
    cls = root.find("class")
    assert cls.find("ty").get("id") == "20"
    print("[OK] XML分类解析")
    assert sp.isVideoFormat("http://x.y/a.m3u8") is True
    assert sp.isVideoFormat("http://x.y/play?id=1") is False
    assert sp.manualVideoCheck() is False
    print("[OK] isVideoFormat/manualVideoCheck")
    assert isinstance(homeContent(False), dict)
    print("[OK] 模块级转发层可用")
    print("===== 自测完成（联网接口请用壳子实测） =====")
