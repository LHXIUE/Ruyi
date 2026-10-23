# -*- coding: utf-8 -*-
# ================= ★写源必加清单（缺则补，逐条落注释）=================
# ①大图片：列表 item 四件套 style={'type':'rect','ratio':1.78} + land=1 + ratio=1.78 + type_name（_item 内已落，分类项给 land/ratio）
# ②二级分类/筛选器：站方分类页实测无筛选参数（/videos?category= / cat= / tag= 全部被忽略，只回第一页）→ 无则不加
# ③搜索：searchContent(key,quick,pg)，关键词 quote()；站方 search 的 page 参数无效（实测 pg1/pg2 同结果）→ pagecount=1
# ================= ★写源必检查清单（交付前逐条核对）=================
# ①翻页：page/pagecount/limit/total 四件齐全，pagecount 真解析（HTML 内 page=N 取 max，禁 999/9999 伪分页），total=pagecount*limit 严格相等
# ②多线路：线路A=源站CDN 的 hlsUrl，线路B=xvideoapi 加速域 /media/hls/...；detail 并发 probe 首集（2.5s 硬上限），死线排后不剔除
# ③播放：playerContent 只回 {'parse':0,'url','header'}，两线路均实测 #EXTM3U 200/206（视频 5/5、短剧 2/2）
# ④分类：NAV 17 类 + 🎬全部视频(/videos 357页) + 📺短剧(/dramas 180页)
# ================= 必加/必检查清单结束 =================
# ★写源前必调·三底座：①记忆库『知识库/影视源开发』及 5 分区检索 ②技能包 SKILL_INDEX v2 分层调度（L0 tvbox-py-v73 → L2 攻坚 → L3 adaptive → L4 交付）③母版 cp 71模板.py 后改 CONFIG ★区与站点逻辑

import re
import json
import gzip
import time
import base64
import urllib.parse
import urllib.request
import concurrent.futures

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        def __init__(self, *a, **k):
            pass

SITE = "https://51xz.vip"
API = "https://xvideoapi.datashubcenter.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
CARD = {"type": "rect", "ratio": 1.78}
CARD_LAND = 1
CARD_RATIO = 1.78
PREFIX = "免费观看影片《"

CATS = [
    ("all", "🎬全部视频"), ("dramas", "📺短剧"),
    ("c0", "真实自拍"), ("c1", "网红女神"), ("c2", "精品国产"), ("c3", "爱好男同"),
    ("c4", "成人短剧"), ("c5", "情感剧场"), ("c6", "古装剧场"), ("c7", "年代农村"),
    ("c8", "穿越重生"), ("c9", "今日吃瓜"), ("c10", "海外吃瓜"), ("c11", "娱乐吃瓜"),
    ("c12", "网红黑料"), ("c13", "日本AV"), ("c14", "国产AV"), ("c15", "欧美AV"), ("c16", "动漫AV"),
]
PATHS = {
    "c0": "真实自拍", "c1": "网红女神", "c2": "国产精品", "c3": "爱好男同-1", "c4": "成年短剧",
    "c5": "情感剧场", "c6": "古装历史", "c7": "年代农村", "c8": "穿越重生", "c9": "今日吃瓜",
    "c10": "海外吃瓜", "c11": "娱乐吃瓜", "c12": "网红黑料", "c13": "日本无码", "c14": "国产av",
    "c15": "欧美av", "c16": "动漫av",
}
NAMES = dict(CATS)


def _clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _nm(t):
    t = _clean(t)
    t = re.sub(r"^免费观看[^《]{0,6}《", "", t)
    if t.startswith(PREFIX):
        t = t[len(PREFIX):]
    if t.endswith("》"):
        t = t[:-1]
    return _clean(t) or "未知"


def _un(h):
    s = h or ""
    for _ in range(4):
        s = re.sub(r'\\+"', '"', s)
        s = s.replace("\\\\", "\\")
    return s


def _mmss(v):
    try:
        n = int(v)
    except Exception:
        return ""
    return "%d:%02d" % (n // 60, n % 60)


class Spider(_BaseSpider):
    def __init__(self):
        self._cache = {}
        self._lock = __import__("threading").RLock()

    def getName(self):
        return "51X"

    def init(self, extend=""):
        with self._lock:
            self._cache.clear()
        return ""

    def _utl(self, u):
        if "://" in u:
            return u
        if u.startswith("/"):
            return SITE + u
        return SITE + "/" + u

    def _get(self, url):
        now = time.time()
        with self._lock:
            c = self._cache.get(url)
            if c and now - c[0] < 300:
                return c[1]
        html = ""
        for _ in range(3):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": UA,
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Accept-Encoding": "gzip",
                    "Referer": SITE + "/"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    raw = r.read()
                if raw[:2] == b"\x1f\x8b":
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                html = raw.decode("utf-8", "ignore")
                if html and "__next_error__" not in html[:400]:
                    break
            except Exception:
                html = ""
            time.sleep(0.4)
        with self._lock:
            self._cache[url] = (now, html)
        return html

    def _rmap(self, s):
        m = {}
        for mt in re.finditer(r'"coverUrl":"([^"]+)"', s):
            st = s.rfind('"id":"cm', 0, mt.start())
            if st < 0:
                continue
            ids = re.match(r'"id":"(cm[a-z0-9]+)"', s[st:st + 60])
            if not ids:
                continue
            tid = ids.group(1)
            seg = s[st:mt.end() + 500]
            if tid in m:
                continue
            hl = re.search(r'"hlsUrl":"([^"]+)"', seg)
            ec = re.search(r'"episodeCount":(\d+)', seg)
            du = re.search(r'"duration":"(\d+)"', seg)
            m[tid] = {"pic": mt.group(1), "hls": hl.group(1) if hl else "",
                      "ec": ec.group(1) if ec else "", "du": du.group(1) if du else "",
                      "k": "drama" if '"kind":"drama"' in seg else "video"}
        return m

    def _cards(self, html, tname=""):
        if not html:
            return []
        s = _un(html)
        mp = self._rmap(s)
        out = []
        seen = set()
        pats = [r'<a class="media-card-link"[^>]*?title="([^"]*)"[^>]*?href="(/[^"]+)"',
                r'<a class="media-card-link"[^>]*?href="(/[^"]+)"[^>]*?title="([^"]*)"']
        for i, p in enumerate(pats):
            for mt in re.finditer(p, html):
                a, b = mt.group(1), mt.group(2)
                href, title = (b, a) if i == 0 else (a, b)
                if not href.startswith("/"):
                    continue
                parts = href.strip("/").split("/")
                if len(parts) < 2:
                    continue
                vid = parts[1]
                if href in seen:
                    continue
                seen.add(href)
                info = mp.get(vid) or {}
                kind = "drama" if parts[0] == "drama" else "video"
                if kind == "drama":
                    rem = ("共%s集" % info["ec"]) if info.get("ec") else "短剧"
                else:
                    rem = _mmss(info.get("du")) or "视频"
                out.append(self._item(vid, parts[2] if len(parts) > 2 else "", kind,
                                      _nm(title), href, info.get("pic", ""),
                                      info.get("hls", ""), rem, tname, info.get("ec", "")))
            if out:
                break
        return out

    def _item(self, vid, slug, kind, name, href, pic, hls, rem, tname, epc):
        d = {"i": vid, "s": slug, "k": kind, "n": name, "pic": pic, "h": hls, "e": epc}
        try:
            vx = "51x" + base64.urlsafe_b64encode(json.dumps(d, ensure_ascii=False).encode("utf-8")).decode("utf-8").rstrip("=")
        except Exception:
            vx = SITE + href
        return {"vod_id": vx, "vod_name": name, "vod_pic": pic, "vod_remarks": rem,
                "type_name": tname or "", "style": dict(CARD), "land": CARD_LAND, "ratio": CARD_RATIO}

    def _unpack(self, v):
        v = str(v or "")
        if v.startswith("51x"):
            b = v[3:]
            b += "=" * (-len(b) % 4)
            try:
                return json.loads(base64.urlsafe_b64decode(b).decode("utf-8"))
            except Exception:
                return {}
        return {}

    def _pgmax(self, html):
        n = [int(x) for x in re.findall(r"page=(\d+)", html or "")]
        return max(n) if n else 1

    def _probe(self, u):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA, "Range": "bytes=0-120"})
            t = time.time()
            with urllib.request.urlopen(req, timeout=2.5) as r:
                b = r.read(64)
            return u if b[:7] == b"#EXTM3U" else ""
        except Exception:
            return ""

    def _sort_lines(self, pairs):
        res = []
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
                fs = [(n, u, ex.submit(self._probe, u)) for n, u in pairs]
                for n, u, f in fs:
                    try:
                        ok = f.result(timeout=3)
                    except Exception:
                        ok = ""
                    res.append((n, u, ok))
        except Exception:
            res = [(n, u, "") for n, u in pairs]
        res.sort(key=lambda x: 0 if x[2] else 1)
        return res

    def homeContent(self, filter=False):
        html = self._get(SITE + "/")
        classes = [{"type_id": k, "type_name": n, "land": CARD_LAND, "ratio": CARD_RATIO} for k, n in CATS]
        vods = self._cards(html, "推荐")
        return {"class": classes, "list": vods, "page": 1, "pagecount": 1,
                "limit": len(vods) or 24, "total": len(vods) or 24}

    def homeVideoContent(self):
        return {"list": self._cards(self._get(SITE + "/"), "推荐")}

    def _ext(self, extend):
        d = {}
        if isinstance(extend, dict):
            d = extend
        elif isinstance(extend, str) and extend.strip().startswith("{"):
            try:
                d = json.loads(extend)
            except Exception:
                d = {}
        return d if isinstance(d, dict) else {}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        ext = self._ext(extend)
        try:
            pg = int(ext.get("page") or ext.get("pg") or ext.get("pageNum") or pg or 1)
        except Exception:
            pg = 1
        pg = max(1, pg)
        tid = str(tid or "all")
        if tid == "all":
            url = SITE + "/videos?page=%d" % pg
            nm = "全部视频"
        elif tid == "dramas":
            url = SITE + "/dramas?page=%d" % pg
            nm = "短剧"
        else:
            p = PATHS.get(tid)
            if not p:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 24}
            url = SITE + "/m/" + urllib.parse.quote(p) + "?page=%d" % pg
            nm = NAMES.get(tid, p)
        html = self._get(url)
        vods = self._cards(html, nm)
        pc = max(1, self._pgmax(html))
        return {"list": vods, "page": pg, "pagecount": pc, "limit": 24, "total": pc * 24}

    def _detail_one(self, ids):
        d = self._unpack(ids)
        if not d or not d.get("i"):
            return None
        kind = d.get("k") or "video"
        vid = d["i"]
        pic = d.get("pic") or ""
        api_hls = API + "/media/hls/%s/index.m3u8" % vid
        if kind == "drama":
            html = self._get(SITE + "/drama/%s/%s" % (vid, d.get("s", "")))
            s = _un(html)
            eps = re.findall(r'"id":"(cm[a-z0-9]+)","lsjEpisodeId":"[^"]*","sort":(\d+),"name":"([^"]*)","hlsUrl":"([^"]+)', s)
            if not eps:
                return None
            eps = sorted(eps, key=lambda x: int(x[1]))
            ea = []
            eb = []
            used = {}
            for idx, (eid, sort, nm, hl) in enumerate(eps, 1):
                lbl = "第%d集" % idx
                if len(lbl) > 18:
                    lbl = lbl[:18]
                if lbl in used:
                    used[lbl] += 1
                    lbl = "%s(%d)" % (lbl, used[lbl])
                else:
                    used[lbl] = 1
                ea.append("%s$%s" % (lbl, hl))
                eb.append("%s$%s" % (lbl, API + "/media/hls/drama/%s/%s/index.m3u8" % (vid, eid)))
            rem = "共%d集" % len(eps)
            pairs = [("线路A·源站CDN", ea), ("线路B·API加速", eb)]
            lines = self._sort_lines([(n, (v[0].split("$")[-1] if v else "")) for n, v in pairs])
            order = {n: v for n, v in pairs}
            names = [n for n, u, ok in lines]
            urls = [order[n] for n in names]
            play_from = "$$$".join(names)
            play_url = "$$$".join(["#".join(v) for v in urls])
        else:
            pic = d.get("pic") or ""
            if not pic:
                pm = re.search(r'og:image" content="([^"]+)"', self._get(SITE + "/video/%s/%s" % (vid, d.get("s", ""))))
                pic = pm.group(1) if pm else ""
            a = d.get("h") or api_hls
            pairs = [("线路A·源站CDN", a), ("线路B·API加速", api_hls)]
            seen = set()
            pr = []
            for n, u in pairs:
                if u and u not in seen:
                    seen.add(u)
                    pr.append((n, u))
            lines = self._sort_lines(pr)
            names = [n for n, u, ok in lines]
            play_from = "$$$".join(names)
            play_url = "$$$".join(["高清$%s" % u for n, u, ok in lines])
            rem = _mmss(d.get("e")) or "视频"
            if len(names) > 1:
                rem = "双线路"
        return {"vod_id": ids, "vod_name": d.get("n") or "未知", "vod_pic": pic if kind == "drama" else pic,
                "vod_play_from": play_from, "vod_play_url": play_url, "vod_remarks": rem,
                "type_name": "", "style": dict(CARD), "land": CARD_LAND, "ratio": CARD_RATIO}

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        out = []
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
                for r in ex.map(self._detail_one, list(ids or [])[:6]):
                    if r:
                        out.append(r)
        except Exception:
            for i in list(ids or [])[:6]:
                r = self._detail_one(i)
                if r:
                    out.append(r)
        return {"list": out, "page": 1, "pagecount": 1, "limit": len(out), "total": len(out)}

    def playerContent(self, flag, id, vipFlags=None):
        u = str(id or "").strip()
        if u.startswith("51x"):
            d = self._unpack(u)
            u = d.get("h") or (API + "/media/hls/%s/index.m3u8" % d.get("i", ""))
        u = u.split("$")[-1].strip()
        if not u.startswith("http"):
            u = self._utl(u)
        return {"parse": 0, "url": u,
                "header": {"User-Agent": UA, "Referer": SITE + "/", "Origin": SITE}}

    def searchContent(self, key, quick=False, pg="1"):
        q = urllib.parse.quote(str(key or ""))
        html = self._get(SITE + "/search?q=" + q)
        vods = self._cards(html, "搜索")
        limit = len(vods) if vods else 24
        return {"list": vods, "page": 1, "pagecount": 1, "limit": limit, "total": limit}
