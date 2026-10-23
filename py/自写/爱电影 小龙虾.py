# -*- coding: utf-8 -*-
"""
TVBox py 爬虫源 —— 爱电影 (m.kuhh4jo.com)
模式: T4/客户端双兼容 (try-import base.spider, 客户端无 base 时回退独立类)
接口: /mw-movie/*  签名: sign = sha1(md5("参数排序串&key=<KEY>&t=<毫秒>")) 头部带 client-type:3
播放: /anonymous/v2/video/episode/url 返回多清晰度官方 m3u8(auth_key 时效), 点击实时解析
分类: type=子类id, type1=大类id(1电影/2剧/3综艺/4动漫/88短剧), v_class/area/year 为文本筛选
"""
import hashlib
import json
import re
import time
import uuid
import ssl
import urllib.request
from urllib.parse import urlencode

from base.spider import Spider

try:
    import requests as _rq
except ImportError:
    _rq = None

API_BASE = "https://m.kuhh4jo.com/mw-movie"
SITE_HOST = "https://m.kuhh4jo.com"
SEO_ID = 115
FALLBACK_DOMAINS = ["kuhh4jo.com", "2go0qf.com", "7ighz2.com", "pgd2ff0.com"]
SIGN_KEY = "cb808529bae6b6be45ecfab29a4889bc"
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
PAGE_SIZE = 24

CATEGORIES = [
    ("1", "电影", 1), ("14", "国产剧", 2), ("15", "欧美剧", 2), ("16", "港台剧", 2),
    ("62", "日韩剧", 2), ("68", "其他剧", 2), ("69", "国产综艺", 3), ("70", "港台综艺", 3),
    ("72", "日韩综艺", 3), ("73", "欧美综艺", 3), ("75", "国产动漫", 4), ("76", "日韩动漫", 4),
    ("77", "欧美动漫", 4), ("94", "短剧·剧情", 88), ("95", "短剧·爱情", 88), ("96", "短剧·古装", 88),
    ("97", "短剧·悬疑", 88), ("98", "短剧·惊悚", 88), ("99", "短剧·奇幻", 88), ("100", "短剧·喜剧", 88),
]
T1 = {tid: t1 for tid, _, t1 in CATEGORIES}
CLASS_F = {1: ["喜剧", "动作", "科幻", "爱情", "悬疑", "奇幻", "剧情", "恐怖", "犯罪", "动画", "惊悚", "战争", "冒险", "灾难", "伦理", "其他"],
           2: ["古装", "喜剧", "爱情", "剧情", "悬疑", "都市", "战争", "奇幻", "武侠", "科幻", "家庭", "犯罪"],
           3: ["真人秀", "脱口秀", "音乐", "歌舞", "访谈", "游戏", "晚会"],
           4: ["热血", "冒险", "搞笑", "恋爱", "战斗", "玄幻", "科幻", "奇幻"],
           88: ["剧情", "爱情", "古装", "悬疑", "惊悚", "奇幻", "喜剧"]}
AREA_F = {1: ["中国大陆", "中国香港", "中国台湾", "美国", "日本", "韩国", "印度", "泰国", "英国", "法国", "其他"],
          2: ["中国大陆", "中国香港", "中国台湾", "日本", "韩国", "美国", "泰国", "其他"],
          3: ["中国大陆", "中国香港", "中国台湾", "日本", "韩国", "美国", "其他"],
          4: ["中国大陆", "日本", "美国", "其他"], 88: []}
YEAR_F = {k: [str(y) for y in range(2026, 2019, -1)] for k in (3, 88)}
YEAR_F.update({k: [str(y) for y in range(2026, 2009, -1)] for k in (1, 2, 4)})


def _empty(v):
    return v is None or v == "" or v != v or (isinstance(v, (dict, list, tuple)) and len(v) == 0)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items() if not _empty(v)}
    if isinstance(o, list):
        return [_clean(x) for x in o if not _empty(x)]
    return o


def _sign(params, t):
    m = _clean(dict(params or {}))
    s = "&".join("%s=%s" % (k, m[k]) for k in sorted(m))
    src = ("%s&key=%s&t=%s" % (s, SIGN_KEY, t)) if s else ("key=%s&t=%s" % (SIGN_KEY, t))
    return hashlib.sha1(hashlib.md5(src.encode("utf-8")).hexdigest().encode("utf-8")).hexdigest()


def _strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


class Spider(Spider):
    def getName(self):
        return "爱电影"

    def getDependence(self):
        return []

    def init(self, extend=""):
        ext = {}
        if isinstance(extend, str) and extend.strip().startswith("{"):
            try:
                ext = json.loads(extend)
            except Exception:
                ext = {}
        self.ext = ext if isinstance(ext, dict) else {}
        self.device = str(uuid.uuid4())
        self.session = _rq.Session() if _rq else None
        proxy = self.ext.get("proxy")
        if proxy and self.session:
            p = proxy if str(proxy).startswith("http") else "http://" + str(proxy)
            self.session.proxies.update({"http": p, "https": p})
        self.headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                        "client-type": "3", "authorization": "", "deviceId": self.device,
                        "Referer": SITE_HOST + "/", "Origin": SITE_HOST}
        self._domain_lock = object()
        self._last_refresh = 0.0
        self.domains = list(FALLBACK_DOMAINS)
        self._refresh_domains(force=True)

    def _refresh_domains(self, force=False):
        """域名池下发接口 (jwkpkfgbs.com 为官方主推域, 实测最快)"""
        now = time.time()
        if not force and now - self._last_refresh < 600:
            return
        fetched = []
        host = self.domains[0] if self.domains else FALLBACK_DOMAINS[0]
        for h in ([host] + FALLBACK_DOMAINS):
            try:
                url = "https://m." + h + "/mw-movie/anonymous/website/get/domain?websiteSeoId=%d" % SEO_ID
                if self.session is not None:
                    r = self.session.get(url, headers={"User-Agent": UA, "Accept": "application/json",
                                                       "Referer": "https://m." + h + "/"}, timeout=8)
                    j = r.json()
                else:
                    req = urllib.request.Request(url, headers={"User-Agent": UA})
                    j = json.loads(urllib.request.urlopen(req, timeout=8).read().decode("utf-8"))
                if j.get("code") == 200 and isinstance(j.get("data"), list):
                    fetched = [str(x).strip().lstrip(".") for x in j["data"] if x]
                    break
            except Exception:
                continue
        pool = [d for d in fetched if d] + list(FALLBACK_DOMAINS)
        seen, uniq = set(), []
        for d in pool:
            if d not in seen:
                seen.add(d)
                uniq.append(d)
        self.domains = uniq
        self._last_refresh = now

    def _switch_domain(self):
        if len(self.domains) > 1:
            self.domains.append(self.domains.pop(0))

    def _api(self, path, params=None):
        params = _clean(dict(params or {}))
        t = str(int(time.time() * 1000))
        heads = dict(self.headers)
        heads.update({"sign": _sign(params, t), "t": t})
        last_err = None
        for attempt in range(len(self.domains)):
            host = self.domains[0]
            api = "https://m." + host + "/mw-movie"
            try:
                if self.session is not None:
                    r = self.session.get(api + path, params=params, headers=heads, timeout=15)
                    j = r.json()
                else:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    url = api + path + ("?" + urlencode(params) if params else "")
                    req = urllib.request.Request(url, headers=heads)
                    j = json.loads(urllib.request.urlopen(req, timeout=15, context=ctx).read().decode("utf-8"))
                if j.get("code") == 200:
                    return j.get("data")
                if j.get("code") in (122012, 122001):
                    return {}
                last_err = RuntimeError("api %s -> %s %s" % (path, j.get("code"), j.get("msg")))
            except Exception as e:
                last_err = e
            self._switch_domain()
        self._refresh_domains(force=True)
        if last_err:
            raise last_err
        return {}

    @staticmethod
    def _item(v):
        return {"vod_id": str(v.get("vodId") or ""), "vod_name": v.get("vodName") or "",
                "vod_pic": v.get("vodPic") or "", "vod_remarks": v.get("vodRemarks") or ""}

    @classmethod
    def _items(cls, lst):
        out, seen = [], set()
        for v in (lst or []):
            it = cls._item(v)
            if it["vod_id"] and it["vod_id"] not in seen:
                seen.add(it["vod_id"])
                out.append(it)
        return out

    def homeContent(self, filter=None):
        classes = [{"type_id": tid, "type_name": name} for tid, name, _ in CATEGORIES]
        filters = {}
        for tid, _, t1 in CATEGORIES:
            fl = []
            if CLASS_F.get(t1):
                fl.append({"key": "class", "name": "类型", "value": [{"n": x, "v": x} for x in CLASS_F[t1]]})
            if AREA_F.get(t1):
                fl.append({"key": "area", "name": "地区", "value": [{"n": x, "v": x} for x in AREA_F[t1]]})
            if YEAR_F.get(t1):
                fl.append({"key": "year", "name": "年份", "value": [{"n": x, "v": x} for x in YEAR_F[t1]]})
            filters[tid] = fl
        return {"class": classes, "filters": filters, "list": []}

    def homeVideoContent(self):
        vods, seen = [], set()
        data = self._api("/anonymous/v1/home/all/list") or {}
        for key in ("homeBroadcastPageData", "homeNewMoviePageData", "homeManagerPageData",
                    "newestTvPageData", "newestVarietyPageData", "newestCartoonPageData",
                    "newestShortTvPageData"):
            for v in ((data.get(key) or {}).get("list") or []):
                it = self._item(v)
                if it["vod_id"] and it["vod_id"] not in seen:
                    seen.add(it["vod_id"])
                    vods.append(it)
                if len(vods) >= 60:
                    return {"list": vods}
        return {"list": vods}

    def categoryContent(self, tid, pg, filter=None, extend=None):
        pg = int(pg) if str(pg).isdigit() else 1
        tid = str(tid)
        if isinstance(extend, str):
            try:
                extend = json.loads(extend) if extend.strip() else {}
            except Exception:
                extend = {}
        extend = extend if isinstance(extend, dict) else {}
        params = {"type": tid, "type1": T1.get(tid, 1), "sort": 1, "sortBy": 1,
                  "pageNum": pg, "pageSize": PAGE_SIZE}
        if extend.get("class"):
            params["v_class"] = extend["class"]
        if extend.get("area"):
            params["area"] = extend["area"]
        if extend.get("year"):
            params["year"] = extend["year"]
        data = self._api("/anonymous/video/list", params) or {}
        lst = self._items(data.get("list"))
        total = int(data.get("totalCount") or 0)
        pc = int(data.get("totalPage") or 0) or ((total + PAGE_SIZE - 1) // PAGE_SIZE if total else pg + 1)
        return {"list": lst, "page": pg, "pagecount": pc, "limit": PAGE_SIZE, "total": total}

    def detailContent(self, ids):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) else str(ids or "")
        data = self._api("/anonymous/video/detail", {"id": vid}) or {}
        eps = sorted(data.get("episodeList") or [], key=lambda e: int(e.get("sort") or 0))
        eps_url = []
        for e in eps:
            name = str(e.get("name") or e.get("sort") or "").replace("#", " ").replace("$", " ").strip()
            eps_url.append("%s$%s-%s" % (name, vid, e.get("nid")))
        vod = {"vod_id": vid, "vod_name": data.get("vodName") or "", "vod_pic": data.get("vodPic") or "",
               "type_name": data.get("typeName") or "", "vod_year": str(data.get("vodYear") or ""),
               "vod_area": data.get("vodArea") or "", "vod_lang": data.get("vodLang") or "",
               "vod_remarks": data.get("vodRemarks") or "", "vod_actor": data.get("vodActor") or "",
               "vod_director": data.get("vodDirector") or "", "vod_class": data.get("vodClass") or "",
               "vod_score": data.get("vodDoubanScore") or data.get("vodScore") or "",
               "vod_content": _strip(data.get("vodContent")) or _strip(data.get("vodBlurb")),
               "vod_play_from": "爱电影", "vod_play_url": "#".join(eps_url)}
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        vid, _, nid = str(id).partition("-")
        data = self._api("/anonymous/v2/video/episode/url", {"clientType": 3, "id": vid, "nid": nid}) or {}
        lst = sorted(data.get("list") or [], key=lambda x: int(x.get("resolution") or 0), reverse=True)
        url = (lst[0].get("url") or "") if lst else ""
        header = {"User-Agent": UA, "Referer": SITE_HOST + "/"}
        if url and self._probe_media(url, header):
            return {"parse": 0, "jx": 0, "playUrl": "", "url": url, "header": header,
                    "format": "application/x-mpegURL"}
        return {"parse": 0, "jx": 0, "playUrl": "", "url": url, "header": header}

    def _probe_media(self, url, header):
        """真直链门禁: Range 抽样验证 m3u8 清单/视频响应, 失败不阻断返回(端点为官方API)"""
        try:
            if self.session is not None:
                r = self.session.get(url, headers=dict(header, **{"Range": "bytes=0-4095"}),
                                     timeout=10, stream=True)
                data, ctype = r.raw.read(4096) or b"", (r.headers.get("Content-Type") or "").lower()
                r.close()
            else:
                req = urllib.request.Request(url, headers=dict(header, **{"Range": "bytes=0-4095"}))
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read(4096) or b""
                    ctype = (resp.headers.get("Content-Type") or "").lower()
            return "#EXTM3U" in data[:64] or "mpegurl" in ctype or "video/" in ctype
        except Exception:
            return False

    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        key = (key or "").strip()
        if not key:
            return {"list": [], "page": pg, "pagecount": max(1, pg), "limit": 20, "total": 0}
        data = self._api("/anonymous/video/searchByWordPageable",
                         {"keyword": key, "pageNum": pg, "pageSize": 20}) or {}
        total = int(data.get("totalCount") or 0)
        pc = int(data.get("totalPage") or 0) or ((total + 19) // 20 if total else max(1, pg))
        return {"list": self._items(data.get("list")), "page": pg, "pagecount": pc,
                "limit": 20, "total": total}

    def localProxy(self, param):
        if isinstance(param, str):
            try:
                param = json.loads(param)
            except Exception:
                param = {}
        param = param if isinstance(param, dict) else {}
        url = param.get("url") or ""
        if not url:
            return [404, "text/plain", b"Not Found", {}]
        try:
            if self.session is not None:
                r = self.session.get(url, headers={"User-Agent": UA, "Referer": SITE_HOST + "/"}, timeout=15)
                return [200, r.headers.get("Content-Type", "application/octet-stream"), r.content, {}]
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": SITE_HOST + "/"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return [200, resp.headers.get("Content-Type", "application/octet-stream"), resp.read(), {}]
        except Exception:
            return [502, "text/plain", b"bad gateway", {}]

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(?:$|[?#])", url or "", re.I))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {}

    def destroy(self):
        return None
