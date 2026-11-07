# -*- coding: utf-8 -*-
"""
全球追更（追更 + 榜单）—— TVBox T4 源
==================================================

由「全球追更」HTML 单文件应用（WebHome 页）1:1 移植而来，分类结构与原页面完全一致：

追更页（首页 Tab）
    平台：国内聚合 / Netflix / HBO Max / Disney+ / Apple TV+ / AmazonPrime / Hulu / Paramount+
    排序：追更模式 / 今日播出 / 最新上线 / 综合热度
    类型：电视剧集 / 电影作品 / 动漫动画 / 综艺节目
    数据源：TMDB discover（与原页面同一套接口、同一套参数）

榜单页（榜单 Tab）
    平台：豆瓣 / IMDb / Rotten Tomatoes / Metacritic / Letterboxd / TMDB / Trakt /
          Netflix / HBO Max / Disney+ / Prime Video / Apple TV+
    榜单：每个平台下的全部榜单（RateFuse 榜单 + 流媒体平台 TMDB 热门榜）
    数据源：https://ratefuse.cn/api/charts/public + TMDB discover(watch_providers)

详情页资源线路（对应原页面「资源」标签页）
    盘搜 / 觅搜   —— 网盘资源（夸克、阿里、百度、UC、天翼、迅雷、123、115、移动等）
    山楂         —— 带票根的直链线路（蓝光4K / 4K / 1080P ...）
    小鸡看看     —— JD4K / ZJ4K / CO4K ... 直链线路

使用（影视仓 / 羊壳 / 海阔 / 蜂蜜壳 / 鱼壳）：
    把本文件放到壳的 spider 目录，或做成 .py 链接后按 type:4 引用。

独立客户端（WebHomeTV / OK影视 / PickTV）：
    删除 `from base.spider import Spider` 一行，并把 `class Spider(Spider)` 改成 `class Spider:`。

账号说明：山楂线路的账号来自原始 HTML 文件内嵌的账号，可通过 init 扩展参数覆盖：
    extend = {"shanzha_user": "...", "shanzha_pass": "...", "shanzha_device": "..."}
"""

import base64
import hashlib
import json
import re
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor, wait

import requests

try:  # 盘搜站证书过期时会刷警告，壳里无需看到
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

from base.spider import Spider

# ==========================================================================
# 配置（与 HTML 单文件内的常量保持一致）
# ==========================================================================

TMDB_API = "https://api.tmdb.org/3"
TMDB_KEY = "2894d9a1baf7812b451de03c801b0281"
TMDB_IMG = "https://images.tmdb.org/t/p/w500"
TMDB_IMG_MID = "https://images.tmdb.org/t/p/w500"
TMDB_IMG_BIG = "https://images.tmdb.org/t/p/w500"

CHARTS_API = "https://ratefuse.cn/api/charts/public"

PAN_BASE = "https://so.252035.xyz"
MIPAN_BASE = "https://www.mipan.so"

SHANZHA_BASE = "http://43.248.128.122:578"
SHANZHA_USER = "sukeke"
SHANZHA_PASS = "sukeke.1"
SHANZHA_DEVICE = "de94cd65-a825-4972-adf9-7dbece13e9f1"

XJ_HOST = "https://xjggg.top"
XJ_FINGER = "20325CC2D4A95E4088BB202A4F66B4E792060ED84F5E3F0E8B41D2DE0AE3A279"
XJ_APP_ID = "com.xmoebr.bdx"
XJ_VERSION = "105"
XJ_MAT2 = "43ee12ffa18b7c0889999fd80ccf64804d390b079073f3d80d9b547548a2f40b"
XJ_MASK = "e40b53b233d3c80d2721cc1efba48e55ac6939c208285d6c06a092fe4020"

UA_MOBILE = ("Mozilla/5.0 (Linux; Android 12) okhttp/3.12.1")
UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# 追更页平台（network 为 TMDB network_id，可多个）
GZ_PLATFORMS = [
    {"id": "domestic", "name": "国内聚合", "network": "2007|1419|1330|1605|1631"},
    {"id": "netflix", "name": "Netflix", "network": "213"},
    {"id": "hbo", "name": "HBO Max", "network": "49"},
    {"id": "disney", "name": "Disney+", "network": "2739"},
    {"id": "appletv", "name": "Apple TV+", "network": "2552"},
    {"id": "amazon", "name": "Amazon Prime", "network": "1024"},
    {"id": "hulu", "name": "Hulu", "network": "453"},
    {"id": "paramount", "name": "Paramount+", "network": "4330"},
]

GZ_SORTS = [
    {"n": "📅 追更模式", "v": "next_episode"},
    {"n": "📆 今日播出", "v": "daily_airing"},
    {"n": "🆕 最新上线", "v": "first_air_date.desc"},
    {"n": "⭐ 综合热度", "v": "popularity.desc"},
]

GZ_TYPES = [
    {"n": "🎥 电视剧集", "v": "tv"},
    {"n": "🎬 电影作品", "v": "movie"},
    {"n": "🌸 动漫动画", "v": "anime"},
    {"n": "🎤 综艺节目", "v": "variety"},
]

# 榜单页里「流媒体平台榜单」的 provider_id（TMDB provider_id）
STREAMING_PROVIDERS = [
    {"name": "Netflix", "id": 8},
    {"name": "HBO Max", "id": 1899},
    {"name": "Disney+", "id": 337},
    {"name": "Prime Video", "id": 9},
    {"name": "Apple TV+", "id": 350},
]

PLATFORMS_ORDER = ["豆瓣", "IMDb", "Rotten Tomatoes", "Metacritic", "Letterboxd", "TMDB",
                    "Trakt", "Netflix", "HBO Max", "Disney+", "Prime Video", "Apple TV+"]

PAN_DISK_TYPES = [
    ["quark", "夸克"], ["aliyun", "阿里"], ["baidu", "百度"], ["uc", "UC"],
    ["tianyi", "天翼"], ["xunlei", "迅雷"], ["123", "123"], ["115", "115"],
    ["mobile", "移动"], ["pikpak", "PikPak"], ["guangya", "光鸭"],
    ["magnet", "磁力"], ["ed2k", "电驴"],
]
PAN_DISK_NAME = dict(PAN_DISK_TYPES)

PAN_QUALITY_KEYWORDS = [
    "4k", "8k", "2160p", "1080p", "hdr", "hdr10", "hdr10+", "dolby vision", "dovi",
    "杜比视界", "杜比全景声", "atmos", "dolby atmos", "杜比", "remux", "bluray",
    "blu-ray", "blueray", "蓝光原盘", "原盘", "uhd", "webdl", "web-dl", "bdrip",
    "x265", "h265", "hevc", "x264", "h264", "60帧", "60fps", "高码率", "无水印",
    "国语", "粤语", "国粤", "中字", "双语",
]

PAGE_LIMIT = 20          # 追更列表每页条数（与原页面一致）
CHART_PAGE = 30          # 榜单每页条数
PAN_LINE_LIMIT = 80      # 单条网盘线路最多保留的资源数


# ==========================================================================
# 小工具
# ==========================================================================

def b64e(text):
    if isinstance(text, str):
        text = text.encode("utf-8")
    return base64.urlsafe_b64encode(text).decode("ascii").rstrip("=")


def b64d(text):
    if not text:
        return ""
    text = str(text)
    pad = "=" * ((4 - len(text) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(text + pad).decode("utf-8", "replace")
    except Exception:
        return ""


def quote(text):
    return urllib.parse.quote(str(text or ""), safe="")


def today_str():
    now = time.localtime()
    return "%04d-%02d-%02d" % (now.tm_year, now.tm_mon, now.tm_mday)


def quality_score(text):
    t = str(text or "").lower()
    score = 0
    for kw in PAN_QUALITY_KEYWORDS:
        if kw in t:
            score += 1
    return score


def quality_badges(text):
    t = str(text or "")
    tags = []
    if re.search(r"dolby\s*vision|杜比|\bDV\b", t, re.I):
        tags.append("杜比视界")
    if re.search(r"HDR", t, re.I):
        tags.append("HDR")
    if re.search(r"4K|2160p", t, re.I):
        tags.append("4K")
    if re.search(r"1080p", t, re.I):
        tags.append("1080P")
    if re.search(r"高码", t):
        tags.append("高码")
    if re.search(r"60\s*fps|60帧", t, re.I):
        tags.append("60FPS")
    return tags


# ==========================================================================
# Spider
# ==========================================================================

class Spider(Spider):

    # ---------- 生命周期 ----------
    def init(self, extend=""):
        self.extend = self._norm_extend(extend)
        self.tmdb_key = self.extend.get("tmdb_key") or TMDB_KEY
        self.sz_user = self.extend.get("shanzha_user") or SHANZHA_USER
        self.sz_pass = self.extend.get("shanzha_pass") or SHANZHA_PASS
        self.sz_device = self.extend.get("shanzha_device") or SHANZHA_DEVICE

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA_MOBILE,
            "Accept": "application/json, text/plain, */*",
        })
        proxy = self.extend.get("proxy") or ""
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

        # 盘搜站证书经常过期，单独一个不校验证书的 session
        self.pan_session = requests.Session()
        self.pan_session.headers.update({"User-Agent": UA_PC})
        self.pan_session.verify = False
        proxy2 = self.extend.get("proxy") or ""
        if proxy2:
            self.pan_session.proxies = {"http": proxy2, "https": proxy2}

        self._charts = None
        self._charts_time = 0.0
        self._sz_token = ""
        self._sz_session = ""
        self._sz_time = 0.0
        self._xj_device = str(uuid.uuid4())

    def getName(self):
        return "全球追更"

    # ---------- 内部工具 ----------
    def _norm_extend(self, extend):
        if isinstance(extend, dict):
            return dict(extend)
        if isinstance(extend, (list, tuple)):
            return {}
        text = str(extend or "").strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except Exception:
            return {}
        if isinstance(data, dict):
            return data
        return {}

    def _norm_ids(self, ids):
        if ids is None:
            return []
        if isinstance(ids, (list, tuple, set)):
            return [str(x) for x in ids if str(x or "").strip()]
        text = str(ids).strip()
        if not text:
            return []
        if "," in text:
            return [x.strip() for x in text.split(",") if x.strip()]
        return [text]

    def _json(self, url, method="GET", payload=None, headers=None, timeout=20, session=None):
        sess = session or self.session
        hdr = dict(headers or {})
        try:
            if method == "POST":
                resp = sess.post(url, headers=hdr, json=payload, timeout=timeout)
            else:
                if payload:
                    url = url + ("&" if "?" in url else "?") + "&".join(
                        "%s=%s" % (k, quote(v)) for k, v in payload.items())
                resp = sess.get(url, headers=hdr, timeout=timeout)
            return resp.json()
        except Exception:
            return None

    def _text(self, url, method="GET", payload=None, headers=None, timeout=20, session=None):
        sess = session or self.session
        hdr = dict(headers or {})
        try:
            if method == "POST":
                resp = sess.post(url, headers=hdr, data=payload, timeout=timeout)
            else:
                resp = sess.get(url, headers=hdr, params=payload, timeout=timeout)
            return resp.text or ""
        except Exception:
            return ""

    def _tmdb(self, path, params=None):
        query = {"api_key": self.tmdb_key, "language": "zh-CN"}
        query.update(params or {})
        url = TMDB_API + path + "?" + "&".join(
            "%s=%s" % (k, quote(v)) for k, v in query.items())
        data = self._json(url, timeout=18)
        if not isinstance(data, dict):
            return {}
        return data

    def _gather(self, tasks, timeout=30):
        """并发跑一批 (key, func)，返回 {key: result}；单个失败不影响整体，超时也不拖死整页。"""
        out = {}
        if not tasks:
            return out
        pool = ThreadPoolExecutor(max_workers=min(6, len(tasks)))
        try:
            futures = {pool.submit(func): key for key, func in tasks}
            done, pending = wait(list(futures.keys()), timeout=timeout)
            for fut in done:
                key = futures[fut]
                try:
                    out[key] = fut.result()
                except Exception:
                    out[key] = None
            for fut in pending:
                fut.cancel()
        except Exception:
            pass
        finally:
            try:
                pool.shutdown(wait=False)
            except Exception:
                pass
        return out

    # ---------- 榜单数据 ----------
    def _chart_key(self, chart):
        if not isinstance(chart, dict):
            return ""
        for field in ("chart_id", "id", "key", "chart_name"):
            value = chart.get(field)
            if value:
                return str(value)
        return ""

    def _provider_charts(self):
        """流媒体平台榜单：在美国区按 TMDB 热度取前 20（与原页面同算法）。"""
        charts = []

        def build(prov, media):
            data = self._tmdb("/discover/" + media, {
                "page": 1, "sort_by": "popularity.desc",
                "watch_region": "US", "with_watch_providers": prov["id"],
                "with_watch_monetization_types": "flatrate",
            })
            results = data.get("results") or []
            entries = []
            for idx, it in enumerate(results[:20]):
                entries.append({
                    "tmdb_id": it.get("id") or "",
                    "rank": idx + 1,
                    "title": it.get("name") or it.get("title") or "",
                    "poster": (TMDB_IMG + it["poster_path"]) if it.get("poster_path") else "",
                    "backdrop": (TMDB_IMG_BIG + it["backdrop_path"]) if it.get("backdrop_path") else "",
                    "media_type": media,
                })
            if not entries:
                return None
            return {
                "chart_id": "provider-%s-%s" % (prov["id"], media),
                "platform": prov["name"],
                "chart_name": "%s %s热门 · TMDB" % (prov["name"], "剧集" if media == "tv" else "电影"),
                "media_type": media,
                "entries": entries,
                "visible": True,
                "sort_order": 0 if media == "tv" else 1,
            }

        tasks = []
        for prov in STREAMING_PROVIDERS:
            for media in ("tv", "movie"):
                tasks.append(("%s|%s" % (prov["id"], media),
                              (lambda p=prov, m=media: build(p, m))))
        results = self._gather(tasks)
        for prov in STREAMING_PROVIDERS:
            for media in ("tv", "movie"):
                chart = results.get("%s|%s" % (prov["id"], media))
                if chart:
                    charts.append(chart)
        return charts

    def _get_charts(self, force=False):
        """取全部榜单：RateFuse 榜单 + 流媒体平台 TMDB 榜单。"""
        now = time.time()
        if not force and self._charts and (now - self._charts_time) < 600:
            return self._charts
        cached = None
        try:
            cached = self.getCache("gz_charts")
        except Exception:
            cached = None
        if not force and cached:
            try:
                data = json.loads(cached)
                if isinstance(data, list) and data:
                    self._charts = data
                    self._charts_time = now
                    return data
            except Exception:
                cached = None

        tasks = [
            ("ratefuse", self._fetch_ratefuse),
            ("provider", self._provider_charts),
        ]
        results = self._gather(tasks)
        charts = results.get("ratefuse") or []
        if not isinstance(charts, list):
            charts = []
        charts = [c for c in charts if isinstance(c, dict) and c.get("visible") is not False]
        charts += results.get("provider") or []
        if charts:
            self._charts = charts
            self._charts_time = now
            try:
                self.setCache("gz_charts", json.dumps(charts))
            except Exception:
                pass
        return self._charts or []

    def _fetch_ratefuse(self):
        url = CHARTS_API
        try:
            resp = self.session.get(url, timeout=20)
            data = resp.json()
        except Exception:
            return []
        if isinstance(data, dict):
            data = data.get("data") or data.get("charts") or []
        return data if isinstance(data, list) else []

    def _chart_short(self, platform, chart_name):
        """榜单短名：去掉与平台重复的前缀（豆瓣·豆瓣 电影 Top 250 -> 电影 Top 250）。"""
        plat = str(platform or "").strip()
        name = str(chart_name or "").strip() or "未命名榜单"
        if plat and name.lower().startswith(plat.lower()):
            name = name[len(plat):].strip(" ·-—:：、")
        return name

    def _chart_platforms(self, charts):
        found = []
        for chart in charts:
            plat = chart.get("platform")
            if plat and plat not in found:
                found.append(plat)
        ordered = [p for p in PLATFORMS_ORDER if p in found]
        ordered += [p for p in found if p not in PLATFORMS_ORDER]
        return ordered

    # ---------- 首页 ----------
    def homeContent(self, filter=None):
        classes = []
        filters = {}

        # 追更页：平台为分类，排序/类型为筛选（与 HTML 的三行筛选条一一对应）
        for plat in GZ_PLATFORMS:
            tid = "gz:" + plat["id"]
            classes.append({"type_id": tid, "type_name": plat["name"]})
            filters[tid] = [
                {
                    "key": "排序", "name": "排序",
                    "value": [{"n": s["n"], "v": s["v"]} for s in GZ_SORTS],
                },
                {
                    "key": "类型", "name": "类型",
                    "value": [{"n": t["n"], "v": t["v"]} for t in GZ_TYPES],
                },
            ]

        # 榜单页：平台为一级分类，具体榜单在「榜单」筛选行里（二级菜单，
        # 对应 HTML 榜单 Tab 的「平台行 + 榜单行」两级 Tab）
        charts = self._get_charts()
        for plat in self._chart_platforms(charts):
            tid = "chart:" + plat
            classes.append({"type_id": tid, "type_name": plat + "榜单"})
            items = [{"n": "全部", "v": ""}]
            for chart in charts:
                if chart.get("platform") != plat:
                    continue
                items.append({
                    "n": self._chart_short(plat, chart.get("chart_name") or "未命名榜单"),
                    "v": self._chart_key(chart),
                })
            if len(items) > 1:
                filters[tid] = [
                    {"key": "榜单", "name": "榜单", "value": items},
                ]

        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        """首页推荐：与原页面默认视图一致（国内聚合 + 追更模式 + 电视剧集）。"""
        result = self._category_gz("domestic", 1, {"排序": GZ_SORTS[0]["v"], "类型": GZ_TYPES[0]["v"]})
        return {"list": result.get("list") or []}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        tid = str(tid or "")
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        ext = self._norm_extend(extend)
        if isinstance(filter, dict):
            ext.update(filter)
        if tid.startswith("gz:"):
            return self._category_gz(tid[3:], page, ext)
        if tid.startswith("chart:"):
            return self._category_chart(tid[6:], page, ext)
        return {"list": [], "page": page, "pagecount": page, "limit": 0, "total": 0}

    def _category_gz(self, platform_id, page, ext):
        plat = None
        for item in GZ_PLATFORMS:
            if item["id"] == platform_id:
                plat = item
                break
        if plat is None:
            return {"list": [], "page": page, "pagecount": page, "limit": 0, "total": 0}

        sort = ext.get("排序") or ext.get("sort") or GZ_SORTS[0]["v"]
        gtype = ext.get("类型") or ext.get("type") or GZ_TYPES[0]["v"]
        media = "movie" if gtype == "movie" else "tv"

        base = {"page": page,
                "sort_by": "popularity.desc" if sort in ("daily_airing", "next_episode") else sort}
        if gtype == "anime":
            base["with_genres"] = "16"
        if gtype == "variety":
            base["with_genres"] = "10764|10767"
        if sort == "daily_airing":
            today = today_str()
            if media == "tv":
                base["air_date.gte"] = today
                base["air_date.lte"] = today
            else:
                base["primary_release_date.gte"] = today
                base["primary_release_date.lte"] = today

        endpoint = "/discover/movie" if media == "movie" else "/discover/tv"
        items = []
        total_pages = 0
        for net in plat["network"].split("|"):
            params = dict(base)
            params["with_networks"] = net
            data = self._tmdb(endpoint, params)
            if not data:
                continue
            try:
                total_pages = max(total_pages, int(data.get("total_pages") or 0))
            except Exception:
                pass
            items += data.get("results") or []

        seen = set()
        fresh = []
        for it in items:
            vid = str(it.get("id") or "")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            fresh.append(it)

        if sort == "first_air_date.desc":
            fresh.sort(key=lambda x: str(x.get("first_air_date") or x.get("release_date") or ""),
                       reverse=True)
        else:
            fresh.sort(key=lambda x: -(x.get("popularity") or 0))

        page_items = fresh[:PAGE_LIMIT]
        vods = [self._vod_of(it, media) for it in page_items]
        pages = min(total_pages, 50) if total_pages else page
        if page >= pages:
            pages = page
        return {"list": vods, "page": page, "pagecount": pages,
                "limit": PAGE_LIMIT, "total": len(vods)}

    def _category_chart(self, tid, page, ext):
        """榜单分类（二级菜单）：tid 形如 "平台" 或 "平台|榜单key"。

        筛选 extend["榜单"] 为空 -> 合并该平台全部榜单；
        为榜单 key -> 只出该榜单。
        """
        charts = self._get_charts()
        wanted_platform = ""
        wanted_key = ""
        want = ext.get("榜单")
        if want is None:
            want = ext.get("chart") or ""
        want = str(want)
        if want.startswith("chart:"):
            want = want[6:]
        if want:
            if "|" in want:
                wanted_platform, wanted_key = want.split("|", 1)
            else:
                wanted_key = want
        if "|" in tid:
            plat, key = tid.split("|", 1)
            wanted_platform = wanted_platform or plat
            wanted_key = wanted_key or key
        else:
            wanted_platform = wanted_platform or tid

        plat_charts = [c for c in charts if c.get("platform") == wanted_platform]
        if not plat_charts:
            return {"list": [], "page": page, "pagecount": page, "limit": 0, "total": 0}

        target = None
        if wanted_key:
            for chart in plat_charts:
                if self._chart_key(chart) == wanted_key:
                    target = chart
                    break
        if target is None:
            # 选了「全部」或 key 失效：合并该平台所有榜单，片名去重
            rows = []
            seen = set()
            for chart in plat_charts:
                entries = list(chart.get("entries") or [])
                entries.sort(key=lambda e: e.get("rank") or 0)
                for entry in entries:
                    title = entry.get("title") or ""
                    if not title or title in seen:
                        continue
                    seen.add(title)
                    rows.append((entry, chart))
            total = len(rows)
            start = (page - 1) * CHART_PAGE
            chunk = rows[start:start + CHART_PAGE]
            vods = []
            for entry, chart in chunk:
                vods.append(self._chart_vod(entry, chart, wanted_platform, True))
            pages = max(1, (total + CHART_PAGE - 1) // CHART_PAGE)
            return {"list": vods, "page": page, "pagecount": pages,
                    "limit": CHART_PAGE, "total": len(vods)}

        entries = list(target.get("entries") or [])
        entries.sort(key=lambda e: e.get("rank") or 0)
        start = (page - 1) * CHART_PAGE
        chunk = entries[start:start + CHART_PAGE]
        vods = [self._chart_vod(entry, target, wanted_platform, False) for entry in chunk]
        pages = max(1, (len(entries) + CHART_PAGE - 1) // CHART_PAGE)
        return {"list": vods, "page": page, "pagecount": pages,
                "limit": CHART_PAGE, "total": len(vods)}

    def _chart_vod(self, entry, chart, platform="", show_chart=False):
        title = entry.get("title") or ""
        media = entry.get("media_type") or chart.get("media_type") or "movie"
        if media == "both":
            media = "movie"
        tmid = entry.get("tmdb_id") or ""
        rank = entry.get("rank")
        remark = "第%s名" % rank if rank else ""
        if show_chart and chart is not None:
            chart_name = self._chart_short(platform, chart.get("chart_name") or "")
            if chart_name and chart_name != "未命名榜单":
                remark = ("%s · %s" % (chart_name, remark)).strip(" ·")
        return {
            "vod_id": "tmdb|%s|%s" % (media, tmid),
            "vod_name": title,
            "vod_pic": entry.get("poster") or "",
            "vod_remarks": remark,
        }

    # ---------- 详情 ----------
    def _vod_of(self, item, media):
        title = item.get("name") or item.get("title") or ""
        poster = ""
        if item.get("poster_path"):
            poster = TMDB_IMG_MID + item["poster_path"]
        remarks = ""
        rate = item.get("vote_average")
        if rate:
            remarks = "⭐%s" % (round(float(rate) * 10) / 10)
        date = item.get("first_air_date") or item.get("release_date") or ""
        if date:
            remarks = (remarks + " · " if remarks else "") + date
        return {
            "vod_id": "tmdb|%s|%s" % (media, item.get("id") or ""),
            "vod_name": title,
            "vod_pic": poster,
            "vod_remarks": remarks,
        }

    def detailContent(self, ids):
        id_list = self._norm_ids(ids)
        if not id_list:
            return {"list": []}
        vid = id_list[0]

        if vid.startswith("pan|"):
            return {"list": [self._pan_only_detail(b64d(vid[4:]))]}

        media = "tv"
        tmid = ""
        if vid.startswith("tmdb|"):
            parts = vid.split("|")
            if len(parts) >= 3:
                media = parts[1] or "tv"
                tmid = parts[2]
        elif vid.startswith("tv:") or vid.startswith("movie:"):
            media, tmid = vid.split(":", 1)
        elif vid.isdigit():
            tmid = vid

        if not tmid:
            return {"list": []}

        detail = self._tmdb("/" + media + "/" + tmid, {
            "append_to_response": "credits,aggregate_credits,recommendations,images,alternative_titles,external_ids,content_ratings",
        })
        if not detail:
            return {"list": []}

        title = detail.get("name") or detail.get("title") or detail.get("original_name") or ""
        poster = ""
        if detail.get("poster_path"):
            poster = TMDB_IMG_MID + detail["poster_path"]

        overview = detail.get("overview") or ""
        genres = [g.get("name") for g in (detail.get("genres") or []) if g.get("name")]
        info = []
        if genres:
            info.append("/".join(genres))
        date = detail.get("first_air_date") or detail.get("release_date") or ""
        if date:
            info.append(str(date)[:4])
        if media == "tv":
            seasons = detail.get("number_of_seasons")
            episodes = detail.get("number_of_episodes")
            if seasons:
                info.append("%s季" % seasons)
            if episodes:
                info.append("%s集" % episodes)
        else:
            runtime = detail.get("runtime")
            if runtime:
                info.append("%s分钟" % runtime)
        rate = detail.get("vote_average")
        if rate:
            info.append("评分%s" % (round(float(rate) * 10) / 10))
        status = detail.get("status")
        if status:
            info.append(status)
        actors = [a.get("name") for a in (detail.get("credits") or {}).get("cast", [])[:6] if a.get("name")]
        if actors:
            info.append("主演 " + "、".join(actors))

        content = overview
        if info:
            content = ("【%s】\n%s" % (" · ".join(info), overview)) if overview else \
                      ("【%s】" % " · ".join(info))

        # 资源线路：盘搜 / 觅搜 / 山楂 / 小鸡看看（并发拉取）
        tasks = [
            ("pan", lambda: self._pan_search(title)),
            ("mipan", lambda: self._mipan_search(title)),
            ("shanzha", lambda: self._shanzha_lines(title)),
            ("xiaoji", lambda: self._xiaoji_lines(title)),
        ]
        res = self._gather(tasks, timeout=26)

        lines = []   # [(线路名, [剧集名, 剧集id], 备注)]
        pan_items = res.get("pan") or []
        if pan_items:
            eps = []
            for item in pan_items[:PAN_LINE_LIMIT]:
                eps.append([self._pan_ep_name(item), self._pan_id(item)])
            lines.append(("盘搜", eps, "%d个网盘资源" % len(eps)))

        mipan_items = res.get("mipan") or []
        if mipan_items:
            eps = []
            for item in mipan_items[:PAN_LINE_LIMIT]:
                eps.append([self._pan_ep_name(item), self._pan_id(item)])
            lines.append(("觅搜", eps, "%d个网盘资源" % len(eps)))

        sz_lines = res.get("shanzha") or []
        for line_name, eps in sz_lines:
            if eps:
                lines.append(("山楂·" + line_name, eps, "直链"))

        xj_lines = res.get("xiaoji") or []
        for line_name, eps in xj_lines:
            if eps:
                lines.append(("小鸡·" + line_name, eps, "直链"))

        play_from = "$$$".join([x[0] for x in lines])
        play_url = "$$$".join(["#".join(["%s$%s" % (e[0], e[1]) for e in x[1]]) for x in lines])

        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": poster,
            "vod_content": content,
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def _pan_only_detail(self, title):
        items = self._pan_search(title)
        eps = []
        for item in items[:PAN_LINE_LIMIT]:
            eps.append([self._pan_ep_name(item), self._pan_id(item)])
        play_url = "#".join(["%s$%s" % (e[0], e[1]) for e in eps])
        return {
            "vod_id": "pan|" + b64e(title),
            "vod_name": title,
            "vod_pic": "",
            "vod_content": "网盘资源（%d 条）" % len(eps),
            "vod_play_from": "盘搜",
            "vod_play_url": play_url,
        }

    def _pan_ep_name(self, item):
        """网盘资源条目名：网盘类型 + 画质标签 + 标题。"""
        remark = item.get("disk_name") or item.get("disk_type") or "网盘"
        tags = quality_badges(item.get("title") or "")
        if tags:
            remark = remark + " " + "/".join(tags[:2])
        title = (item.get("title") or "").strip()
        if title:
            return (remark + " " + title)[:48]
        return remark

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg="1"):
        key = str(key or "").strip()
        if not key:
            return {"list": []}
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1

        # 片库(TMDB) 与 网盘资源 并行拉，TMDB 无结果时也能找到可下载资源
        tasks = [
            ("tmdb", lambda: self._tmdb("/search/multi",
                                        {"query": key, "include_adult": "false", "page": page})),
            ("pan", lambda: self._pan_search(key, timeout=15, attempts=1)),
        ]
        res = self._gather(tasks, timeout=20)

        data = res.get("tmdb") or {}
        results = []
        for it in (data.get("results") or []) if data else []:
            if it.get("media_type") not in ("tv", "movie"):
                continue
            if not it.get("poster_path"):
                continue
            results.append(it)
        results.sort(key=lambda x: -(x.get("popularity") or 0))
        vods = [self._vod_of(it, it.get("media_type") or "movie") for it in results[:30]]

        for item in (res.get("pan") or [])[:12]:
            vods.append({
                "vod_id": "pan|" + b64e(item.get("title") or key),
                "vod_name": (item.get("title") or key)[:40],
                "vod_pic": "",
                "vod_remarks": "网盘·%s" % (item.get("disk_name") or item.get("disk_type") or ""),
            })
        return {"list": vods, "page": page}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags=None):
        play_id = str(id or "").strip()
        if not play_id:
            return {"parse": 1, "url": "", "jx": 0}

        if play_id.startswith("http"):
            return {"parse": 1, "url": play_id, "jx": 0}

        parts = play_id.split("|")
        kind = parts[0] if parts else ""

        if kind == "pan":
            try:
                payload = json.loads(b64d(parts[2])) if len(parts) > 2 else {}
            except Exception:
                payload = {}
            url = payload.get("url") or ""
            pwd = payload.get("password") or ""
            disk = b64d(parts[1]) if len(parts) > 1 else ""
            if url and pwd:
                url = self._add_pan_password(url, pwd, disk)
            if not url:
                return {"parse": 1, "url": "", "jx": 0}
            return {"parse": 1, "url": url, "jx": 0}

        if kind == "sz":
            tk = b64d(parts[1]) if len(parts) > 1 else ""
            if not tk:
                return {"parse": 1, "url": "", "jx": 0}
            try:
                direct = self._shanzha_resolve(tk)
            except Exception:
                direct = ""
            if not direct:
                return {"parse": 1, "url": "", "jx": 0}
            header = {"User-Agent": UA_MOBILE, "Referer": "https://www.google.com/"}
            return self._play_or_sniff(direct, header)

        if kind == "xj":
            frm = b64d(parts[1]) if len(parts) > 1 else ""
            blob = b64d(parts[2]) if len(parts) > 2 else ""
            if not blob:
                return {"parse": 1, "url": "", "jx": 0}
            try:
                direct = self._xiaoji_resolve(frm, blob)
            except Exception:
                direct = ""
            if not direct:
                return {"parse": 1, "url": "", "jx": 0}
            header = {"User-Agent": "okhttp/4.9.0"}
            return self._play_or_sniff(direct, header)

        return {"parse": 1, "url": play_id, "jx": 0}

    def _add_pan_password(self, url, password, disk_type=""):
        """网盘提取码拼到链接上（115 用 password，其余用 pwd；磁力/电驴不加）。"""
        target = str(url or "").strip()
        code = str(password or "").strip()
        if not target or not code:
            return target
        if re.search(r"[?&#](pwd|password|passcode|code)=", target, re.I):
            return target
        if re.match(r"^(magnet:|ed2k://)", target, re.I):
            return target
        param = "password" if str(disk_type).lower() == "115" else "pwd"
        sep = "&" if "?" in target else "?"
        return target + sep + param + "=" + quote(code)

    def _play_or_sniff(self, url, header):
        """直链门禁：确认是真媒体（m3u8 / 视频流）才用 parse:0，否则交给壳解析。"""
        media = self._probe_media(url, header)
        if media:
            return {"parse": 0, "url": url, "header": header, "jx": 0}
        return {"parse": 1, "url": url, "header": header, "jx": 0}

    def _probe_media(self, url, header=None):
        """抽测播放地址：m3u8 必须含 #EXTM3U，mp4 要有正确 magic / content-type。"""
        try:
            hdr = {"User-Agent": UA_MOBILE}
            if header:
                hdr.update(header)
            resp = self.session.get(url, headers=hdr, timeout=20)
            text = resp.text or ""
            ctype = (resp.headers.get("content-type") or "").lower()
            if "#EXTM3U" in text[:2000]:
                return True
            if "video/" in ctype or "audio/" in ctype or "mpegurl" in ctype:
                return True
            if text[:16].find("ftyp") >= 0:
                return True
        except Exception:
            return False
        return False

    # ---------- 本地代理（部分壳需要） ----------
    def localProxy(self, param):
        url = ""
        if isinstance(param, dict):
            url = param.get("url") or param.get("uri") or ""
        else:
            url = str(param or "")
        if not url.startswith("http"):
            return [404, "text/plain", b"", {}]
        try:
            resp = self.session.get(url, headers={"User-Agent": UA_PC}, timeout=20)
            body = resp.content or b""
            ctype = resp.headers.get("content-type") or "application/octet-stream"
            return [200, ctype, body, dict(resp.headers)]
        except Exception:
            return [404, "text/plain", b"", {}]

    # ==========================================================================
    # 盘搜 / 觅搜
    # ==========================================================================
    def _normalize_disk_type(self, value):
        val = str(value or "").strip().lower()
        if val in ("ali", "alipan"):
            return "aliyun"
        if val == "others":
            return "other"
        if val == "123pan":
            return "123"
        if val in ("139", "caiyun"):
            return "mobile"
        if val == "pikpakdrive":
            return "pikpak"
        if val == "guangyapan":
            return "guangya"
        if val in ("bt", "magnetlink"):
            return "magnet"
        return val

    def _clean_keyword(self, text):
        out = re.sub(r"[《》\[\]【】]", "", str(text or ""))
        out = re.sub(r"[(（].*?[)）]", "", out)
        return re.sub(r"\s+", " ", out).strip()

    def _pan_id(self, item):
        payload = json.dumps({
            "url": item.get("url") or "",
            "password": item.get("password") or "",
            "type": item.get("disk_type") or "",
        }, ensure_ascii=False)
        return "pan|%s|%s" % (b64e(item.get("disk_type") or ""), b64e(payload))

    def _normalize_pan(self, merged, keyword):
        seen = set()
        out = []
        for disk_type, links in (merged or {}).items():
            if not isinstance(links, list):
                continue
            norm_type = self._normalize_disk_type(disk_type)
            for link in links:
                if not isinstance(link, dict):
                    continue
                url = str(link.get("url") or link.get("link") or link.get("href") or "").strip()
                if not url:
                    continue
                key = norm_type + "|" + url
                if key in seen:
                    continue
                seen.add(key)
                note = str(link.get("note") or "").split("\n")[0].strip()
                title = note or str(link.get("title") or link.get("name") or keyword or "网盘资源")
                out.append({
                    "url": url,
                    "password": str(link.get("password") or link.get("pass") or "").strip(),
                    "title": title,
                    "disk_type": norm_type,
                    "disk_name": PAN_DISK_NAME.get(norm_type, norm_type or "网盘"),
                    "source": str(link.get("source") or link.get("channel") or ""),
                    "datetime": str(link.get("datetime") or link.get("time") or ""),
                })
        out.sort(key=lambda x: -quality_score(x["title"]))
        return out

    def _pan_search(self, keyword, timeout=13, attempts=2):
        keyword = str(keyword or "").strip()
        if not keyword:
            return []
        payload = {
            "kw": self._clean_keyword(keyword) or keyword,
            "res": "merge",
            "src": "all",
            "cloud_types": [x[0] for x in PAN_DISK_TYPES],
        }
        url = PAN_BASE.rstrip("/") + "/api/search"
        # 盘搜偶尔超时/限流，按原页面策略重试一次
        for attempt in range(attempts):
            try:
                resp = self.pan_session.post(url, json=payload, timeout=timeout)
                body = resp.json()
            except Exception:
                body = None
            if isinstance(body, dict):
                data = body.get("data") if isinstance(body.get("data"), dict) else body
                merged = data.get("merged_by_type") or {}
                items = self._normalize_pan(merged, keyword)
                if items:
                    return items
            if attempt + 1 < attempts:
                time.sleep(0.7)
        return []

    def _mipan_search(self, keyword):
        keyword = str(keyword or "").strip()
        if not keyword:
            return []
        try:
            resp = self.session.get(MIPAN_BASE + "/api/token",
                                    headers={"Accept": "application/json",
                                             "Referer": MIPAN_BASE + "/"},
                                    timeout=10)
            token = (resp.json() or {}).get("token") or ""
        except Exception:
            token = ""
        if not token:
            return []
        headers = {"Content-Type": "application/json",
                   "X-Mipan-Token": token,
                   "Referer": MIPAN_BASE + "/"}
        try:
            resp = self.session.post(MIPAN_BASE + "/api/search", headers=headers,
                                     json={"kw": keyword}, timeout=18)
            body = resp.json()
        except Exception:
            return []
        if not isinstance(body, dict):
            return []
        root = body.get("data") if isinstance(body.get("data"), (dict, list)) else body
        merged = {}
        if isinstance(root, list):
            for x in root:
                self._push_pan(merged, x)
        elif isinstance(root, dict):
            for x in root.get("results") or []:
                if isinstance(x, dict) and isinstance(x.get("links"), list):
                    for link in x["links"]:
                        merged_item = dict(x)
                        merged_item.update(link or {})
                        self._push_pan(merged, merged_item, (link or {}).get("type"))
                else:
                    self._push_pan(merged, x)
            by_type = root.get("merged_by_type")
            if isinstance(by_type, dict):
                for disk_type, links in by_type.items():
                    for x in links or []:
                        self._push_pan(merged, x, disk_type)
        items = self._normalize_pan(merged, keyword)
        allowed = set(x[0] for x in PAN_DISK_TYPES)
        return [x for x in items if x["disk_type"] in allowed]

    def _push_pan(self, merged, obj, type_hint=None):
        if not isinstance(obj, dict):
            return
        url = obj.get("url") or obj.get("link") or obj.get("share_url") or ""
        if not url:
            return
        disk_type = self._normalize_disk_type(
            obj.get("type") or obj.get("disk_type") or type_hint or "other")
        merged.setdefault(disk_type, []).append({
            "url": url,
            "password": str(obj.get("password") or obj.get("pass") or ""),
            "note": obj.get("note") or obj.get("title") or obj.get("name") or "",
            "source": obj.get("source") or "",
        })

    # ==========================================================================
    # 山楂
    # ==========================================================================
    def _sz_login(self):
        now = time.time()
        if self._sz_token and self._sz_session and (now - self._sz_time) < 1800:
            return True
        headers = {"Content-Type": "application/json", "User-Agent": UA_MOBILE}
        payload = {"Username": self.sz_user, "Password": self.sz_pass,
                   "device_id": self.sz_device}
        body = self._json(SHANZHA_BASE + "/api/v1/user/login", "POST", payload, headers, 15)
        if not isinstance(body, dict) or body.get("code") != 1:
            return False
        token = ((body.get("data") or {}).get("token")) or ""
        if not token:
            return False
        self._sz_token = token

        headers["Authorization"] = "Bearer " + token
        chal = self._json(SHANZHA_BASE + "/api/v1/security/challenge", "GET", None, headers, 15)
        if not isinstance(chal, dict) or chal.get("code") != 1:
            return False
        cdata = chal.get("data") or {}
        init_payload = {
            "challenge": cdata.get("challenge"),
            "challenge_id": cdata.get("challenge_id"),
            "device_id": self.sz_device,
            "token": token,
            "client_token": "",
            "timestamp": int(time.time()),
            "nonce": uuid.uuid4().hex,
            "username": self.sz_user,
            "password": self.sz_pass,
            "sign": "s", "signature": "s", "app_id": "1", "app_key": "1",
            "app_version": "1.0", "version": "1", "platform": "android",
            "device": "android", "version_code": 1, "uid": "1", "source_id": "1",
            "site_id": "1", "type": "1",
        }
        init = self._json(SHANZHA_BASE + "/api/v1/security/init", "POST", init_payload, headers, 15)
        if not isinstance(init, dict) or init.get("code") != 1:
            return False
        session_id = ((init.get("data") or {}).get("session_id")) or ""
        if not session_id:
            return False
        self._sz_session = session_id
        self._sz_time = now
        return True

    def _sz_json(self, method, path, payload=None):
        headers = {"Content-Type": "application/json", "User-Agent": UA_MOBILE}
        if self._sz_token:
            headers["Authorization"] = "Bearer " + self._sz_token
        if self._sz_session:
            headers["X-Session-Id"] = self._sz_session
        url = path if path.startswith("http") else SHANZHA_BASE + path
        return self._json(url, method, payload, headers, 15)

    def _shanzha_lines(self, keyword):
        keyword = str(keyword or "").strip()
        if not keyword or not self._sz_login():
            return []
        body = self._sz_json("GET", "/api/v1/search?wd=%s&page=1" % quote(keyword))
        if not isinstance(body, dict) or body.get("code") != 1:
            return []
        hits = ((body.get("data") or {}).get("hits")) or []
        if not hits:
            return []
        vod_id = hits[0].get("vod_id")
        detail = self._sz_json("GET", "/api/v1/video/detail?id=%s" % quote(str(vod_id)))
        if not isinstance(detail, dict) or detail.get("code") != 1:
            return []
        vod_info = (detail.get("data") or {}).get("vod_info") or {}
        raw_lines = vod_info.get("vod_url_with_player") or []
        lines = []
        for line in raw_lines:
            name = str(line.get("name") or line.get("code") or "山楂")
            eps = []
            for seg in str(line.get("url") or "").split("#"):
                seg = seg.strip()
                if not seg:
                    continue
                ep_name = seg
                ticket = ""
                if "$" in seg:
                    ep_name, ticket = seg.split("$", 1)
                if not ep_name or not ticket:
                    continue
                eps.append([ep_name, "sz|%s" % b64e(ticket)])
            if eps:
                lines.append((name, eps))
        lines.sort(key=lambda x: self._sz_priority(x[0]))
        return lines[:4]

    def _sz_priority(self, name):
        text = str(name or "")
        if "蓝光4K" in text or ("蓝光" in text and "4K" in text):
            return 0
        if "4K" in text:
            return 1
        if "蓝光" in text:
            return 2
        return 3

    def _shanzha_resolve(self, ticket):
        if not self._sz_login():
            return ""
        body = self._sz_json("POST", "/api/v1/vod/ticket", {"token": ticket})
        if not isinstance(body, dict) or body.get("code") != 1:
            return ""
        tk = (body.get("data") or {}).get("ticket") or ""
        if not tk:
            return ""
        seg = tk.split(".")[0]
        raw = b64d(seg)
        if not raw:
            return ""
        try:
            payload = json.loads(raw)
        except Exception:
            return ""
        data = payload.get("data") or {}
        api = str(data.get("parse_api") or "")
        du = str(data.get("url") or "")
        if not api or not du:
            return ""
        if api.startswith("/"):
            target = SHANZHA_BASE + api + quote(du)
        elif "{md5}" in api:
            target = api.replace("{md5}", du)
        elif "url=" in api:
            target = api + quote(du)
        else:
            target = api + du
        text = self._text(target, "GET", None,
                          {"Referer": "https://www.google.com/", "User-Agent": UA_MOBILE}, 30)
        if not text:
            return ""
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return str(obj.get("url") or "")
        except Exception:
            pass
        text = text.strip()
        if text.startswith("http"):
            return text
        return ""

    # ==========================================================================
    # 小鸡看看
    # ==========================================================================
    def _xj_sk(self):
        material = (b"GG_NATIVE_MATERIAL_V1"
                    + bytes.fromhex(XJ_FINGER.lower())
                    + bytes.fromhex(XJ_MAT2)
                    + b"\x00\x00\x00\x00")
        digest = hashlib.sha256(material).digest()
        mask = bytes.fromhex(XJ_MASK)
        return bytes(digest[i] ^ mask[i] for i in range(30))

    def _xj_nonce(self):
        head = hashlib.sha256(self._xj_device.encode("utf-8")).hexdigest()[:8].upper()
        seed = hashlib.sha256((self._xj_device + str(time.time())).encode("utf-8")).hexdigest()
        tail = "".join(str(int(seed[i * 2:i * 2 + 2], 16) % 10) for i in range(8))
        return head + tail

    def _xj_headers(self):
        ts = str(int(time.time() * 1000))
        nonce = self._xj_nonce()
        payload = (("finger=SF-" + XJ_FINGER + "&id=" + XJ_APP_ID + "&nonce=" + nonce + "&sk=")
                   .encode("utf-8") + self._xj_sk()
                   + ("&time=" + ts + "&v=" + XJ_VERSION).encode("utf-8"))
        sign = hashlib.sha256(payload).hexdigest().upper()
        return {
            "x-device-id": self._xj_device,
            "x-device-brand": "Xiaomi",
            "x-device-model": "Xiaomi 15 Pro",
            "x-update-id": "embedded",
            "User-Agent": "okhttp/4.9.0",
            "x-aid": XJ_APP_ID,
            "x-ave": XJ_VERSION,
            "x-time": ts,
            "x-nonc": nonce,
            "x-sign": sign,
        }

    def _xj_api(self, path, params=None):
        url = XJ_HOST + path
        if params:
            url += "?" + "&".join("%s=%s" % (k, quote(v)) for k, v in params.items())
        body = self._json(url, "GET", None, self._xj_headers(), 15)
        if not isinstance(body, dict):
            return {}
        if body.get("code") not in (200, 1):
            return {}
        return body

    def _xiaoji_lines(self, keyword):
        keyword = str(keyword or "").strip()
        if not keyword:
            return []
        search = self._xj_api("/api.php/app/search/index", {"wd": keyword, "page": 1})
        items = search.get("data") or []
        if not isinstance(items, list) or not items:
            return []
        vod_id = items[0].get("vod_id")
        if vod_id is None:
            return []
        playback = self._xj_api("/api.php/app/vod/playback_v2", {"vod_id": vod_id})
        pb = playback.get("data") or {}
        sources = pb.get("sources") or []
        if not sources:
            detail = self._xj_api("/api.php/app/vod/detail_v2", {"vod_id": vod_id})
            ddata = detail.get("data") or {}
            selected = (ddata.get("playback") or {}).get("selected_source")
            if selected:
                sources = [{"from": selected.get("from"), "display_name": selected.get("from"),
                            "episodes": selected.get("episodes") or []}]
        lines = []
        for source in sources:
            if not isinstance(source, dict):
                continue
            name = str(source.get("display_name") or source.get("from") or "")
            if not name:
                continue
            frm = str(source.get("from") or "")
            eps = []
            for ep in source.get("episodes") or []:
                if not isinstance(ep, dict):
                    continue
                blob = str(ep.get("url") or "")
                if not blob:
                    continue
                ep_name = str(ep.get("title") or ("第%s集" % ep.get("position")))
                eps.append([ep_name, "xj|%s|%s" % (b64e(frm), b64e(blob))])
            if eps:
                lines.append((name, eps))
        lines.sort(key=lambda x: self._xj_priority(x[0]))
        # 只保留能真正解出直链的线路（部分线路后端解码会失效）
        alive = []
        for name, eps in lines[:6]:
            if not eps:
                continue
            probe = eps[0][1].split("|")
            if len(probe) < 3:
                continue
            frm = b64d(probe[1])
            blob = b64d(probe[2])
            if not blob:
                continue
            try:
                direct = self._xiaoji_resolve(frm, blob)
            except Exception:
                direct = ""
            if direct:
                alive.append((name, eps))
            if len(alive) >= 3:
                break
        return alive

    def _xj_priority(self, name):
        text = str(name or "").upper()
        if "JD4K" in text or "ZJ4K" in text or "CO4K" in text:
            return 0
        if "4K" in text:
            return 1
        if "蓝光" in text:
            return 2
        return 3

    def _xiaoji_resolve(self, frm, blob):
        for attempt in range(3):
            body = self._xj_api("/api.php/app/decode/url/", {"url": blob, "vodFrom": frm})
            data = body.get("data")
            if isinstance(data, str) and data.startswith("http"):
                return data
            if attempt < 2:
                time.sleep(0.4)
        return ""
