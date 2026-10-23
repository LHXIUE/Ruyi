#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================
 洛雪TV (https://tv.lxyy.club/) TVBox / drpy / Pyramid 影视爬虫源
====================================================================
源名称: 洛雪TV
文件名: luoxue.py
适配:   TVBox / 影视仓 / FongMi / dr_py / Pyramid (type=3, csp python 源)

站点特点（2026-10-18 实测）:
  - 非 maccms 模板站，为自研 Web 应用（Go 后端 + TMDB 数据）
  - 分类数据来自本地 API:
      /api/ranking.php        TMDB 热榜 1000 条（电影+剧集）
      /api/quark-ranking.php  夸克热榜 60 条
      /api/short-drama.php    短剧（服务端分页）
  - 搜索:  GET /api/proxy.php?action=search&wd=&page=   （实时聚合 8 个采集源,
           上游耗时 5~30s, 需先 POST /api/playback-session.php 建立会话 Cookie）
  - 详情:  GET /api/proxy.php?action=detail&source=&id=
           返回多线路 episodes[{group, episodes:[{name,url,playback_grant}]}]
  - 播放:
      * 采集源 (mj/jl/360zy/md/ik/dytt): episodes.url 即 m3u8 直链 -> parse=0
      * 官采源 (qilin/fy): url 为 B站/腾讯 等平台页, 站点走自家 JSON 解析:
          1) GET  /json-player.php?route=official_musbpyqz&url=&source=&grant=
             从返回 HTML 提取 data-authorization
          2) POST /api/json-parse.php {route,url,source,authorization}
             -> {url: .mpd/.m3u8 直链, native_tracks:{video,audio}}
         备用 route: official_muh2fkp2 (仅 official_source=qilin)

部署:
  1. 将本文件上传到你的 py 源目录 (spiders/ 或 txt/py/ 等);
  2. index.json / 配置中注册:
     {"key":"luoxue","name":"洛雪TV","type":3,"api":"luoxue.py"};
  3. 重启或刷新配置即可。

依赖: requests (框架环境自带; 独立运行请 pip install requests)
====================================================================
"""

import re
import sys
import time
import json
import base64
import threading
from urllib.parse import quote, unquote, urlencode

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    requests = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    try:
        from base.spider import BaseSpider
    except Exception:
        class BaseSpider(object):
            pass


# ==================================================================
# 配置中心
# ==================================================================
DEFAULT_CONFIG = {
    "host": "https://tv.lxyy.club",
    "site_name": "洛雪TV",
    "timeout": 30,
    "search_timeout": 42,      # 聚合搜索上游慢（实测 5~30s）
    "detail_timeout": 38,
    "page_size": 40,
    "search_interval": 1.2,    # 搜索节流（秒）
    "ua_pc": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "ua_play": "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    # 站点声明的 8 个采集源（order 即官网优先级）
    "sources": {
        "qilin": {"name": "官采蓝光", "direct": False, "order": 0},
        "mj":    {"name": "4K60帧",  "direct": True,  "order": 1},
        "jl":    {"name": "自营",    "direct": True,  "order": 2},
        "360zy": {"name": "360资源", "direct": True,  "order": 3},
        "dytt":  {"name": "电影天堂", "direct": True,  "order": 4},
        "ik":    {"name": "ikun资源", "direct": True,  "order": 5},
        "md":    {"name": "魔都资源", "direct": True,  "order": 6},
        "fy":    {"name": "官方源",   "direct": False, "order": 7},
    },
    # 官采 JSON 解析 route
    "json_routes": ["official_musbpyqz", "official_muh2fkp2"],
    # 平台组（官采线路 group / 平台页域名）
    "platform_groups": {"qq", "qiyi", "iqiyi", "youku", "mgtv", "bilibili", "rrmj", "hmdj", "mango"},
    "platform_domains": ["v.qq.com", "bilibili.com", "iqiyi.com", "youku.com", "mgtv.com", "rrmj"],
    "direct_source_priority": ["mj", "jl", "360zy", "md", "ik", "dytt"],
    # 分类定义: (type_id, 名称, 数据源)
    "categories": [
        ("rank", "影视热榜", "rank"),
        ("quark", "夸克热榜", "quark"),
        ("shortdrama", "短剧", "sd"),
    ],
    "detail_cache_ttl": 1500,       # 详情聚合缓存 25min（grant 有效期相关）
    "parse_cache_ttl": 1200,        # 官采解析结果缓存 20min
    "list_cache_ttl": 600,
    "aggregate_sources": 6,         # 详情聚合最多取几个源
}

_GLOBAL = {
    "cookies": None,                # 站点会话 cookie dict
    "session_lock": threading.Lock(),
    "search_lock": threading.Lock(),
    "last_search_at": 0.0,
    "detail_cache": {},             # key -> (ts, vod dict)
    "parse_cache": {},              # platform url -> (ts, direct url)
    "list_cache": {},               # list key -> (ts, items)
    "detail_cache_lock": threading.Lock(),
}


# ==================================================================
# 工具函数
# ==================================================================
def _b64e(obj):
    """对象 -> urlsafe base64（无 padding），用作 vod_id / play id"""
    try:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    except Exception:
        return ""


def _b64d(s):
    """urlsafe base64 -> 对象"""
    try:
        s = str(s or "").strip()
        s += "=" * (-len(s) % 4)
        return json.loads(base64.urlsafe_b64decode(s.encode("ascii")).decode("utf-8"))
    except Exception:
        return None


def _s(v):
    return str(v or "").strip()


def _now():
    return time.time()


def _cache_get(store, key, ttl):
    try:
        item = store.get(key)
        if item and _now() - item[0] < ttl:
            return item[1]
    except Exception:
        pass
    return None


def _cache_set(store, key, value):
    try:
        with _GLOBAL["detail_cache_lock"]:
            if len(store) > 200:
                oldest = sorted(store.items(), key=lambda kv: kv[1][0])[:50]
                for k, _ in oldest:
                    try:
                        del store[k]
                    except Exception:
                        pass
            store[key] = (_now(), value)
    except Exception:
        pass


class _Http:
    """线程安全的站点 HTTP 客户端（每线程独立 Session，共享会话 Cookie）"""

    def __init__(self, cfg):
        self.cfg = cfg
        self._tls = threading.local()

    def _session(self):
        s = getattr(self._tls, "session", None)
        if s is None:
            s = requests.Session()
            s.headers.update({
                "User-Agent": self.cfg["ua_pc"],
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": self.cfg["host"] + "/",
            })
            self._tls.session = s
        return s

    def ensure_session(self, force=False):
        """POST /api/playback-session.php 建立站点会话，保存 Cookie"""
        if not HAS_REQUESTS:
            return False
        if _GLOBAL["cookies"] and not force:
            return True
        with _GLOBAL["session_lock"]:
            if _GLOBAL["cookies"] and not force:
                return True
            try:
                r = self._session().post(
                    self.cfg["host"] + "/api/playback-session.php",
                    timeout=self.cfg["timeout"], data="")
                j = r.json() if r.status_code == 200 else {}
                if j.get("success") and r.cookies:
                    _GLOBAL["cookies"] = {c.name: c.value for c in r.cookies}
                    return True
            except Exception:
                pass
            return False

    def request(self, method, url, **kw):
        """带会话 Cookie 的请求；授权失效自动重建一次"""
        if not HAS_REQUESTS:
            return None
        cookies = _GLOBAL["cookies"]
        for attempt in (0, 1):
            s = self._session()
            try:
                r = s.request(method, url, cookies=cookies, **kw)
            except Exception:
                r = None
            if r is None:
                if attempt == 0:
                    self.ensure_session(force=True)
                    cookies = _GLOBAL["cookies"]
                    continue
                return None
            if r.status_code in (401, 403) and attempt == 0:
                self.ensure_session(force=True)
                cookies = _GLOBAL["cookies"]
                continue
            return r
        return None

    def get_json(self, url, timeout=None):
        r = self.request("GET", url, timeout=timeout or self.cfg["timeout"])
        if r is None or r.status_code != 200:
            return None
        try:
            return r.json()
        except Exception:
            return None

    def get_text(self, url, timeout=None, headers=None):
        r = self.request("GET", url, timeout=timeout or self.cfg["timeout"], headers=headers)
        if r is None or r.status_code != 200:
            return ""
        try:
            r.encoding = "utf-8"
            return r.text or ""
        except Exception:
            return ""


_HTTP = None  # 延迟初始化


def _http():
    global _HTTP
    if _HTTP is None:
        _HTTP = _Http(DEFAULT_CONFIG)
    return _HTTP


# ==================================================================
# 站点 API 封装
# ==================================================================
def _api_search(wd, page=1):
    """聚合搜索: results[{source,id,name,pic,remarks,source_name,type,year}]"""
    wd = _s(wd)
    if not wd:
        return []
    # 节流
    interval = DEFAULT_CONFIG["search_interval"]
    if interval > 0:
        with _GLOBAL["search_lock"]:
            delta = _now() - _GLOBAL["last_search_at"]
            if 0 < delta < interval:
                try:
                    time.sleep(interval - delta)
                except Exception:
                    pass
            _GLOBAL["last_search_at"] = _now()
    _http().ensure_session()
    url = "%s/api/proxy.php?action=search&wd=%s&page=%d" % (
        DEFAULT_CONFIG["host"], quote(wd), max(1, int(page or 1)))
    j = _http().get_json(url, timeout=DEFAULT_CONFIG["search_timeout"])
    if not isinstance(j, dict) or not j.get("success"):
        return []
    rows = j.get("results") or []
    out = []
    for r in rows:
        try:
            if not isinstance(r, dict):
                continue
            out.append({
                "source": _s(r.get("source")),
                "id": _s(r.get("id")),
                "name": _s(r.get("name")),
                "pic": _s(r.get("pic")),
                "remarks": _s(r.get("remarks")),
                "source_name": _s(r.get("source_name")) or _s(r.get("source")),
                "type": _s(r.get("type")),
                "year": _s(r.get("year")),
            })
        except Exception:
            continue
    return [x for x in out if x["source"] and x["id"] and x["name"]]


def _api_detail(source, vid):
    """单源详情 -> (name, pic, lines)  lines=[(group, [(ep_name, url, grant), ...])]"""
    source = _s(source)
    vid = _s(vid)
    if not source or not vid:
        return None
    _http().ensure_session()
    url = "%s/api/proxy.php?action=detail&source=%s&id=%s" % (
        DEFAULT_CONFIG["host"], quote(source), quote(vid))
    j = _http().get_json(url, timeout=DEFAULT_CONFIG["detail_timeout"])
    if not isinstance(j, dict) or not j.get("success"):
        return None
    dts = j.get("details") or []
    if not dts or not isinstance(dts[0], dict):
        return None
    d = dts[0]
    meta = {
        "name": _s(d.get("name")),
        "pic": _s(d.get("pic")),
        "type": _s(d.get("type")),
        "year": _s(d.get("year")),
        "area": _s(d.get("area")),
        "actor": _s(d.get("actor")),
        "director": _s(d.get("director")),
        "content": _s(d.get("content")),
        "remarks": _s(d.get("remarks")),
        "source": source,
    }
    lines = []
    for ln in d.get("episodes") or []:
        try:
            if not isinstance(ln, dict):
                continue
            group = _s(ln.get("group")) or "默认"
            eps = []
            for ep in ln.get("episodes") or []:
                try:
                    if not isinstance(ep, dict):
                        continue
                    u = _s(ep.get("url"))
                    if not u:
                        continue
                    eps.append((_s(ep.get("name")) or "", u, _s(ep.get("playback_grant"))))
                except Exception:
                    continue
            if eps:
                lines.append((group, eps))
        except Exception:
            continue
    meta["lines"] = lines
    return meta


def _api_ranking():
    """TMDB 热榜 1000 条（本地缓存 10min）"""
    cache_key = "rank"
    got = _cache_get(_GLOBAL["list_cache"], cache_key, DEFAULT_CONFIG["list_cache_ttl"])
    if got is not None:
        return got
    j = _http().get_json(DEFAULT_CONFIG["host"] + "/api/ranking.php",
                         timeout=DEFAULT_CONFIG["timeout"])
    items = []
    if isinstance(j, dict) and j.get("available"):
        for r in j.get("items") or []:
            try:
                if not isinstance(r, dict):
                    continue
                title = _s(r.get("title"))
                if not title:
                    continue
                poster = "https://image.tmdb.org/t/p/w342" + _s(r.get("posterPath")) \
                    if _s(r.get("posterPath")) else ""
                items.append({
                    "title": title,
                    "media": _s(r.get("mediaType")) or "movie",
                    "pic": poster,
                    "year": "",
                })
            except Exception:
                continue
    if items:
        _cache_set(_GLOBAL["list_cache"], cache_key, items)
    return items


def _api_quark():
    """夸克热榜 60 条"""
    cache_key = "quark"
    got = _cache_get(_GLOBAL["list_cache"], cache_key, DEFAULT_CONFIG["list_cache_ttl"])
    if got is not None:
        return got
    j = _http().get_json(DEFAULT_CONFIG["host"] + "/api/quark-ranking.php",
                         timeout=DEFAULT_CONFIG["timeout"])
    items = []
    if isinstance(j, dict) and j.get("available"):
        for r in j.get("items") or []:
            try:
                if not isinstance(r, dict):
                    continue
                title = _s(r.get("title"))
                if not title:
                    continue
                items.append({
                    "title": title,
                    "channel": _s(r.get("channel")),
                    "pic": _s(r.get("src")),
                    "year": _s(r.get("year"))[:4],
                    "remarks": _s(r.get("episodes")) or _s(r.get("category")),
                })
            except Exception:
                continue
    if items:
        _cache_set(_GLOBAL["list_cache"], cache_key, items)
    return items


def _api_shortdrama(page=1):
    """短剧（服务端分页） -> (items, has_more)"""
    page = max(1, int(page or 1))
    j = _http().get_json(
        DEFAULT_CONFIG["host"] + "/api/short-drama.php?page=%d" % page,
        timeout=DEFAULT_CONFIG["timeout"])
    items = []
    has_more = False
    if isinstance(j, dict) and j.get("success"):
        has_more = bool(j.get("hasMore"))
        for r in j.get("items") or []:
            try:
                if not isinstance(r, dict):
                    continue
                title = _s(r.get("title"))
                if not title:
                    continue
                items.append({
                    "title": title,
                    "pic": _s(r.get("poster")),
                    "year": _s(r.get("year"))[:4],
                    "remarks": ("全%s集" % r.get("episodes")) if r.get("episodes") else "",
                })
            except Exception:
                continue
    return items, has_more


# ==================================================================
# 播放链解析
# ==================================================================
def _is_platform_url(u):
    low = _s(u).lower()
    return any(d in low for d in DEFAULT_CONFIG["platform_domains"])


def _is_platform_group(group):
    return _s(group).lower() in DEFAULT_CONFIG["platform_groups"]


def _is_direct_url(u):
    low = _s(u).lower().split("#")[0]
    if any(f in low for f in (".m3u8", ".mp4", ".flv", ".mkv", ".mpd")):
        return True
    # 采集源常见动态 m3u8（无扩展名但非平台页）默认按直链处理
    return not _is_platform_url(low)


def _resolve_official(play_url, grant, source):
    """官采平台页 -> 直链（站点 JSON 解析两步法）"""
    play_url = _s(play_url)
    grant = _s(grant)
    source = _s(source)
    cached = _cache_get(_GLOBAL["parse_cache"], play_url, DEFAULT_CONFIG["parse_cache_ttl"])
    if cached:
        return cached
    h = _http()
    h.ensure_session()
    for route in DEFAULT_CONFIG["json_routes"]:
        try:
            page_url = ("%s/json-player.php?route=%s&url=%s&source=%s&grant=%s" % (
                DEFAULT_CONFIG["host"], route,
                quote(play_url, safe=""), quote(source, safe=""), quote(grant, safe="")))
            html = h.get_text(page_url, timeout=DEFAULT_CONFIG["timeout"])
            if not html:
                continue
            m = re.search(r'data-authorization="([^"]+)"', html)
            if not m:
                continue
            auth = m.group(1)
            r = h.request(
                "POST", DEFAULT_CONFIG["host"] + "/api/json-parse.php",
                timeout=DEFAULT_CONFIG["timeout"],
                headers={"Content-Type": "application/json", "Referer": DEFAULT_CONFIG["host"] + "/"},
                data=json.dumps({
                    "route": route, "url": play_url,
                    "source": source, "authorization": auth,
                }).encode("utf-8"))
            j = r.json() if r is not None and r.status_code == 200 else {}
            if isinstance(j, dict) and j.get("success") and _s(j.get("url")):
                direct = _s(j["url"])
                if direct.startswith("http"):
                    _cache_set(_GLOBAL["parse_cache"], play_url, direct)
                    return direct
        except Exception:
            continue
    return ""


# ==================================================================
# 数据装配
# ==================================================================
def _row_score(row, title, kind):
    """详情聚合时的行评分（越高越优先）"""
    score = 0
    name = row["name"]
    info = DEFAULT_CONFIG["sources"].get(row["source"]) or {}
    if row["source"] in DEFAULT_CONFIG["direct_source_priority"]:
        score += 6
    if name == title:
        score += 10
    elif name.startswith(title):
        score += 5
    elif title in name:
        score += 3
    if kind == "sd":
        blob = row["type"] + row["remarks"] + row["source_name"]
        if "短剧" in blob:
            score += 12
    return score


def _play_line_name(source, group):
    sname = (DEFAULT_CONFIG["sources"].get(source) or {}).get("name") or source
    g = _s(group)
    if g and g.lower() not in ("default",):
        return "%s·%s" % (sname, g)
    return sname


def _aggregate_detail(title, kind):
    """标题 -> 多源聚合详情（缓存）"""
    title = _s(title)
    if not title:
        return None
    ck = "agg:%s:%s" % (kind, title)
    got = _cache_get(_GLOBAL["detail_cache"], ck, DEFAULT_CONFIG["detail_cache_ttl"])
    if got is not None:
        return got
    try:
        rows = _api_search(title, 1)
    except Exception:
        rows = []
    if not rows:
        return None
    rows.sort(key=lambda r: _row_score(r, title, kind), reverse=True)
    picked, seen_src = [], set()
    for r in rows:
        if r["source"] in seen_src:
            continue
        seen_src.add(r["source"])
        picked.append(r)
        if len(picked) >= DEFAULT_CONFIG["aggregate_sources"]:
            break
    results = [None] * len(picked)

    def worker(i, row):
        try:
            results[i] = _api_detail(row["source"], row["id"])
        except Exception:
            results[i] = None

    threads = []
    for i, row in enumerate(picked):
        t = threading.Thread(target=worker, args=(i, row), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        try:
            t.join(DEFAULT_CONFIG["detail_timeout"] + 6)
        except Exception:
            pass
    metas = [m for m in results if m and m.get("lines")]
    if not metas:
        return None
    return {"name": metas[0]["name"] or title, "pic": metas[0]["pic"],
            "metas": metas, "title": title}


def _meta_to_vod(title, kind, pic, metas):
    """聚合元数据 -> TVBox vod dict（多线路多集）"""
    vod_id = _b64e({"k": kind, "t": title})
    play_from = []
    play_url = []
    remarks_set = []
    for meta in metas:
        src = meta.get("source") or ""
        for group, eps in meta.get("lines") or []:
            lname = _play_line_name(src, group)
            if lname in play_from:
                continue
            ep_parts = []
            for ep_name, u, grant in eps:
                ep_name = _s(ep_name) or "播放"
                pid = _b64e({"u": u, "g": grant, "s": src, "grp": group})
                ep_parts.append("%s$%s" % (ep_name, pid))
            if not ep_parts:
                continue
            play_from.append(lname)
            play_url.append("#".join(ep_parts))
            remarks_set.append(_s(meta.get("remarks")))
    if not play_from:
        return None
    vod = {
        "vod_id": vod_id,
        "vod_name": title,
        "vod_pic": pic or "",
        "vod_remarks": remarks_set[0] if remarks_set else "",
        "vod_year": _s(metas[0].get("year")),
        "vod_area": _s(metas[0].get("area")),
        "vod_actor": _s(metas[0].get("actor"))[:500],
        "vod_director": _s(metas[0].get("director"))[:200],
        "vod_content": (_s(metas[0].get("content")) or _s(metas[0].get("remarks")))[:900],
        "vod_play_from": "$$$".join(play_from),
        "vod_play_url": "$$$".join(play_url),
    }
    return vod


def _list_item(kind, title, pic, remarks="", year=""):
    return {
        "vod_id": _b64e({"k": kind, "t": _s(title)}),
        "vod_name": _s(title),
        "vod_pic": _s(pic),
        "vod_remarks": _s(remarks),
        "vod_year": _s(year)[:4],
    }


def _search_item(row):
    vod_id = _b64e({
        "k": "x", "s": row["source"], "i": row["id"],
        "n": row["name"], "p": row["pic"],
    })
    return {
        "vod_id": vod_id,
        "vod_name": row["name"],
        "vod_pic": row["pic"],
        "vod_remarks": " ".join(x for x in (row["remarks"], row["source_name"]) if x),
        "vod_year": row["year"],
    }


# ==================================================================
# Spider 主类
# ==================================================================
class Spider(BaseSpider):

    name = DEFAULT_CONFIG["site_name"]
    base_url = DEFAULT_CONFIG["host"]
    site_url = DEFAULT_CONFIG["host"]
    class_name = [c[1] for c in DEFAULT_CONFIG["categories"]]
    class_url = [c[0] for c in DEFAULT_CONFIG["categories"]]
    config = {"player": {}, "filter": {}}
    header = {"User-Agent": DEFAULT_CONFIG["ua_pc"], "Referer": DEFAULT_CONFIG["host"] + "/"}

    def __init__(self, *args, **kwargs):
        try:
            super(Spider, self).__init__(*args, **kwargs)
        except Exception:
            pass
        if not hasattr(self, "extend"):
            self.extend = ""
        self._log_prefix = "[" + self.name + "]"

    # ---------- 基础 ----------
    def getName(self):
        return self.name

    def init(self, extend=""):
        self.extend = extend if isinstance(extend, str) else ""
        try:
            _http().ensure_session()
        except Exception:
            pass

    def getDependence(self):
        return []

    def destroy(self):
        try:
            if _HTTP is not None:
                s = getattr(_HTTP._tls, "session", None)
        except Exception:
            pass

    def isVideoFormat(self, url):
        fmts = [".m3u8", ".mp4", ".flv", ".avi", ".mkv", ".mov", ".ts", ".mpd", ".webm"]
        return any(f in _s(url).lower() for f in fmts)

    def manualVideoCheck(self):
        return False

    def localProxy(self, param=None, **kwargs):
        return {"url": "", "header": "", "mimeType": ""}

    def _log(self, msg):
        try:
            print("%s %s" % (self._log_prefix, msg))
        except Exception:
            pass

    # ---------- 首页 ----------
    def homeContent(self, filter=False, **kwargs):
        result = {"class": [], "list": [], "filters": {}}
        for tid, tname, _src in DEFAULT_CONFIG["categories"]:
            result["class"].append({"type_name": tname, "type_id": tid})
        result["filters"] = {
            "rank": [{
                "key": "type", "name": "类型",
                "value": [
                    {"n": "全部", "v": ""},
                    {"n": "电影", "v": "movie"},
                    {"n": "剧集", "v": "tv"},
                ],
            }],
            "quark": [{
                "key": "channel", "name": "频道",
                "value": [
                    {"n": "全部", "v": ""},
                    {"n": "电视剧", "v": "电视剧"},
                    {"n": "电影", "v": "电影"},
                    {"n": "综艺", "v": "综艺"},
                    {"n": "动漫", "v": "动漫"},
                ],
            }],
        }
        try:
            items = _api_ranking()[:24]
            result["list"] = [_list_item("r", it["title"], it["pic"], it.get("remarks", ""), it.get("year", ""))
                              for it in items]
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        out = []
        try:
            for it in _api_ranking()[:30]:
                out.append(_list_item("r", it["title"], it["pic"], "", it.get("year", "")))
        except Exception:
            pass
        return {"list": out}

    # ---------- 分类 ----------
    def _ext_val(self, extend, key):
        if not extend:
            return ""
        try:
            if isinstance(extend, str):
                extend = json.loads(extend)
            if isinstance(extend, dict):
                return _s(extend.get(key))
        except Exception:
            pass
        return ""

    def categoryContent(self, tid, pg=1, filter=False, extend=None, **kwargs):
        try:
            pg = int(str(pg).strip() or 1)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        size = DEFAULT_CONFIG["page_size"]
        result = {"list": [], "page": pg, "pagecount": pg, "limit": size, "total": size}
        try:
            if tid == "rank":
                items = _api_ranking()
                f = self._ext_val(extend, "type")
                if f:
                    items = [it for it in items if it.get("media") == f]
                total = len(items)
                pagecount = max(1, (total + size - 1) // size)
                chunk = items[(pg - 1) * size: pg * size]
                result.update({
                    "list": [_list_item("r", it["title"], it["pic"], "热榜", it.get("year", ""))
                             for it in chunk],
                    "pagecount": pagecount, "total": total,
                })
            elif tid == "quark":
                items = _api_quark()
                f = self._ext_val(extend, "channel")
                if f:
                    items = [it for it in items if f in it.get("channel", "")]
                total = len(items)
                pagecount = max(1, (total + size - 1) // size)
                chunk = items[(pg - 1) * size: pg * size]
                result.update({
                    "list": [_list_item("q", it["title"], it["pic"], it.get("remarks", ""), it.get("year", ""))
                             for it in chunk],
                    "pagecount": pagecount, "total": total,
                })
            elif tid == "shortdrama":
                items, has_more = _api_shortdrama(pg)
                result.update({
                    "list": [_list_item("s", it["title"], it["pic"], it.get("remarks", ""), it.get("year", ""))
                             for it in items],
                    "pagecount": pg + 1 if (has_more or items) else pg,
                    "total": pg * size,
                })
        except Exception as e:
            self._log("category异常: %s" % e)
        return result

    # ---------- 详情 ----------
    def detailContent(self, ids, **kwargs):
        try:
            ids = ids if isinstance(ids, list) else [ids]
            payload = _b64d(ids[0])
            if not isinstance(payload, dict):
                return {"list": []}
            kind = _s(payload.get("k")) or "r"
            if kind == "x":
                # 搜索行直达单源详情
                src, vid = _s(payload.get("s")), _s(payload.get("i"))
                meta = _api_detail(src, vid)
                if not meta:
                    return {"list": []}
                vod = _meta_to_vod(meta["name"] or _s(payload.get("n")), "x",
                                   payload.get("p") or meta["pic"], [meta])
                vod["vod_name"] = meta["name"] or _s(payload.get("n"))
                return {"list": [vod]} if vod else {"list": []}
            title = _s(payload.get("t"))
            pic = ""
            # 分类入口：先取海报
            if kind == "r":
                for it in _api_ranking():
                    if it["title"] == title:
                        pic = it["pic"]
                        break
            elif kind == "q":
                for it in _api_quark():
                    if it["title"] == title:
                        pic = it["pic"]
                        break
            elif kind == "s":
                try:
                    sd_items, _hm = _api_shortdrama(1)
                    for it in sd_items:
                        if it["title"] == title:
                            pic = it["pic"]
                            break
                except Exception:
                    pass
            agg = _aggregate_detail(title, kind)
            if not agg:
                # 找不到源：返回占位详情（可展示海报/简介，播放为空）
                return {"list": [{
                    "vod_id": _b64e(payload), "vod_name": title, "vod_pic": pic,
                    "vod_remarks": "", "vod_play_from": "", "vod_play_url": "",
                    "vod_content": "暂未在采集源中找到该影片的播放数据。",
                }]}
            if not pic:
                pic = agg.get("pic") or ""
            vod = _meta_to_vod(title, kind, pic, agg["metas"])
            if not vod:
                return {"list": []}
            return {"list": [vod]}
        except Exception as e:
            self._log("detail异常: %s" % e)
            return {"list": []}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg=1, *args, **kwargs):
        # 布尔/页码混用归一化（quick 位可能被传成页码）
        page = pg if isinstance(quick, bool) else (quick if str(quick).isdigit() else pg)
        try:
            page = int(str(page).strip() or 1)
        except Exception:
            page = 1
        key = _s(key)
        result = {"list": [], "page": page, "pagecount": page, "limit": 40, "total": 0}
        if not key:
            return result
        try:
            rows = _api_search(key, page)
        except Exception as e:
            self._log("search异常: %s" % e)
            return result
        # 精确匹配优先（保持站点内顺序），提升搜索体验
        try:
            def _rank(r):
                n = r.get("name", "")
                if n == key:
                    return 0
                if n.startswith(key):
                    return 1
                if key in n:
                    return 2
                return 3
            rows.sort(key=_rank)
        except Exception:
            pass
        # 同名同源去重
        seen = set()
        out = []
        for r in rows:
            uk = (r["source"], r["id"])
            if uk in seen:
                continue
            seen.add(uk)
            out.append(_search_item(r))
        if out:
            result.update({"list": out, "total": len(out),
                           "pagecount": page + 1 if len(out) >= 20 else page})
        return result

    def searchContentPage(self, key, quick=False, pg=1):
        return self.searchContent(key, quick, pg)

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags=None, **kwargs):
        ua = DEFAULT_CONFIG["ua_play"]
        header_ua = json.dumps({"User-Agent": ua})
        fallback = {"parse": 1, "url": "", "header": header_ua}
        try:
            payload = _b64d(id)
            if not isinstance(payload, dict):
                payload = {"u": str(id)}
            u = _s(payload.get("u"))
            grant = _s(payload.get("g"))
            src = _s(payload.get("s"))
            grp = _s(payload.get("grp"))
            if not u:
                return fallback
            # 平台页 -> 官采 JSON 解析
            if _is_platform_url(u) or _is_platform_group(grp):
                direct = _resolve_official(u, grant, src)
                if direct:
                    return {"parse": 0, "url": direct, "header": header_ua}
                # 解析失败 -> 交客户端 web 解析兜底
                return {"parse": 1, "url": u, "header": json.dumps({"User-Agent": DEFAULT_CONFIG["ua_pc"]})}
            # 采集直链（m3u8/mp4 等）—— UA-only，不带 Referer（规避字节系 CDN 403）
            if _is_direct_url(u):
                return {"parse": 0, "url": u, "header": header_ua}
            # 未知形态：尝试官采解析，否则直链透传
            direct = _resolve_official(u, grant, src)
            if direct:
                return {"parse": 0, "url": direct, "header": header_ua}
            return {"parse": 0, "url": u, "header": header_ua}
        except Exception as e:
            self._log("player异常: %s" % e)
            return fallback


SpiderCustom = Spider   # 兼容别名


# ==================================================================
# 实机自检入口:  python3 luoxue.py
# ==================================================================
if __name__ == "__main__":
    if not HAS_REQUESTS:
        print("请先安装: pip install requests")
        sys.exit(1)

    sp = Spider()
    sp.init("")
    print("== name:", sp.getName())

    print("\n== homeContent ==")
    hc = sp.homeContent(True)
    print("classes:", [c["type_name"] for c in hc.get("class", [])],
          "| home list:", len(hc.get("list", [])))

    print("\n== category rank p1 ==")
    cc = sp.categoryContent("rank", 1, False, {})
    print("n=%s pagecount=%s" % (len(cc["list"]), cc["pagecount"]))
    if cc["list"]:
        print("item0:", json.dumps(cc["list"][0], ensure_ascii=False)[:160])

    print("\n== category shortdrama p1 ==")
    sd = sp.categoryContent("shortdrama", 1, False, {})
    print("n=%s pagecount=%s" % (len(sd["list"]), sd["pagecount"]))
    if sd["list"]:
        print("item0:", json.dumps(sd["list"][0], ensure_ascii=False)[:160])

    print("\n== search: 家业 ==")
    sc = sp.searchContent("家业", False, 1)
    print("n=%s" % len(sc["list"]))
    if sc["list"]:
        print("item0:", json.dumps(sc["list"][0], ensure_ascii=False)[:160])
        print("\n== detail (search row) ==")
        dt = sp.detailContent([sc["list"][0]["vod_id"]])
        if dt["list"]:
            v = dt["list"][0]
            print("name:", v.get("vod_name"), "| lines:", v.get("vod_play_from"))
            first_line = (v.get("vod_play_url") or "").split("$$$")[0]
            first_ep = first_line.split("#")[0]
            pid = first_ep.split("$", 1)[1] if "$" in first_ep else ""
            print("ep0 pid len:", len(pid))
            print("\n== player (direct) ==")
            pc = sp.playerContent("", pid)
            print("parse=%s url=%s" % (pc.get("parse"), str(pc.get("url"))[:120]))
            if pc.get("parse") == 0 and pc.get("url", "").lower().startswith("http"):
                try:
                    rr = requests.get(pc["url"], headers={"User-Agent": DEFAULT_CONFIG["ua_play"]},
                                      timeout=20, stream=True)
                    chunk = next(rr.iter_content(256), b"") or b""
                    print("拉流前缀:", chunk[:40])
                    rr.close()
                except Exception as ex:
                    print("拉流失败:", ex)

    print("\n== detail (category aggregate: rank item) ==")
    if cc["list"]:
        dt2 = sp.detailContent([cc["list"][0]["vod_id"]])
        if dt2["list"]:
            v2 = dt2["list"][0]
            print("name:", v2.get("vod_name"), "| lines:", str(v2.get("vod_play_from"))[:180])
            fl = (v2.get("vod_play_url") or "").split("$$$")[0].split("#")[0]
            pid2 = fl.split("$", 1)[1] if "$" in fl else ""
            if pid2:
                print("\n== player (aggregate ep0) ==")
                pc2 = sp.playerContent("", pid2)
                print("parse=%s url=%s" % (pc2.get("parse"), str(pc2.get("url"))[:120]))
                if pc2.get("parse") == 0 and pc2.get("url", "").lower().startswith("http"):
                    try:
                        rr = requests.get(pc2["url"], headers={"User-Agent": DEFAULT_CONFIG["ua_play"]},
                                          timeout=25, stream=True)
                        chunk = next(rr.iter_content(256), b"") or b""
                        print("拉流前缀:", chunk[:40])
                        rr.close()
                    except Exception as ex:
                        print("拉流失败:", ex)

    print("\n== ALL DONE ==")
