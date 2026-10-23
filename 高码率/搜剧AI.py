# -*- coding: utf-8 -*-
"""
@header({
  searchable: 1,
  filterable: 0,
  quickSearch: 1,
  title: '搜剧AI-13',
  lang: 'hipy'
})
"""
# ============================================================
# 搜剧AI (souju13.com) — TVBox / 影视仓 / FongMi 爬虫源（单文件）
# ============================================================
# 站点: https://souju13.com（souju.ai 镜像域，实测 2026-10-15）
# 接口: 纯 SPA + 带签名的 JSON API，与 souju.ai 同协议同密钥：
#   签名: message = "{METHOD}\n{pathname}{search}\n{ts_ms}\n{nonce}"
#         signature = hmac_sha256(API_KEY, message) hex 小写
#   头:   x-ai-movie-timestamp / x-ai-movie-nonce / x-ai-movie-signature
#         x-ai-movie-client-name / x-ai-movie-client-version
#         x-ai-movie-build-version / x-ai-movie-protocol-version
#         x-ai-movie-site-host  ← 本域实测新增头
#   端点:
#     首页   GET /v1/feed/home?scope=public&mode=preview&sections=3&cards=10
#     分类   GET /v1/browse/catalog?kind={...}&page=&limit=20   ← 参数名 kind（实测）
#     搜索   GET /v1/browse/catalog?q={kw}&page=&limit=20
#     详情   GET /v1/catalog/{av_id}
#     解析1  GET /v1/playback/resolve/{token}?view=compact  -> line_options[].url=resolve://ticket
#     解析2  POST /v1/playback/resolve-line?view=compact body{"ticket"} -> line.url 直链
# 播放: 直链带时效签名，实时请求不缓存 ticket；部分内容需登录（resolve-line 401）
#       -> 内置线路降级（最多尝试 N 条，探针预筛）+ Probe 自测（自动挑匿名样本）
#
# 部署(sources.json):
#   {"key":"souju13","name":"搜剧AI","type":3,"api":"./py/py_souju13.py",
#    "searchable":1,"quickSearch":1,"filterable":0}
# 调试:
#   python3 py_souju13.py --selftest            # 全接口自测
#   python3 py_souju13.py home|category|search|detail|play [args]
# ============================================================
import gzip
import hashlib
import hmac
import json
import random
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

# ---------------------- 实测常量 ----------------------
SITE = "https://souju13.com"
API_KEY = "f39d73aa7a6426203cdee1ef17b31d3b7ea8c23f4c59c62a3a8aa0f39ee5e79d"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
BUILD_VER = "aimovie-v2026.10.15.2-danmaku-suggestions-02f82e7bd711-web"
PROTO_VER = "2026-07-05.library-v2.playback-v1"
CLIENT_NAME = "movie-search-frontend"
CLIENT_VERSION = "1.0.0"
SITE_HOST = "souju13.com"

# 分类字典（type_id 即接口 content_kind）
CLASS_LIST = [
    {"type_id": "series", "type_name": "电视剧"},
    {"type_id": "movie", "type_name": "电影"},
    {"type_id": "short_drama", "type_name": "短剧"},
    {"type_id": "anime", "type_name": "动漫"},
    {"type_id": "variety", "type_name": "综艺"},
    {"type_id": "documentary", "type_name": "纪录片"},
    {"type_id": "sports", "type_name": "体育"},
]

# 播放降级配置（通用能力，调试可改）
PLAY_MAX_TRY_LINE = 5      # 最多尝试线路数
PLAY_PROBE_FILTER = True   # 探针预筛：跳过不可匿名播放的线路
TIMEOUT = 20

# 缓存 TTL（ticket/播放直链坚决不缓存）
_CACHE_TTL = {"feed": 300, "browse": 180, "catalog": 600, "resolve_meta": 300}
_CACHE = {}
_DEBUG = "--debug" in sys.argv


def _log(*a):
    if _DEBUG:
        sys.stderr.write("[souju13] " + " ".join(str(x) for x in a) + "\n")


# ---------------------- 缓存 ----------------------
def _cache_get(key):
    item = _CACHE.get(key)
    if item and item[0] > time.time():
        return item[1]
    _CACHE.pop(key, None)
    return None


def _cache_set(key, value, ttl):
    try:
        _CACHE[key] = (time.time() + ttl, value)
        if len(_CACHE) > 300:
            now = time.time()
            for k in [k for k, v in _CACHE.items() if v[0] <= now]:
                _CACHE.pop(k, None)
    except Exception:
        pass


# ---------------------- 签名 HTTP ----------------------
def _sign_headers(method, url):
    u = urllib.parse.urlsplit(url)
    path = u.path + (("?" + u.query) if u.query else "")
    ts = str(int(time.time() * 1000))
    nonce = "".join(random.choice("0123456789abcdef") for _ in range(32))
    msg = "{}\n{}\n{}\n{}".format(method.upper(), path, ts, nonce)
    sig = hmac.new(API_KEY.encode("utf-8"),
                   msg.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip",
        "x-ai-movie-timestamp": ts,
        "x-ai-movie-nonce": nonce,
        "x-ai-movie-signature": sig,
        "x-ai-movie-client-name": CLIENT_NAME,
        "x-ai-movie-client-version": CLIENT_VERSION,
        "x-ai-movie-build-version": BUILD_VER,
        "x-ai-movie-protocol-version": PROTO_VER,
        "x-ai-movie-site-host": SITE_HOST,
    }


def _request_json(url, method="GET", body=None, timeout=TIMEOUT):
    """带签名请求，返回 JSON；nonce 一次性，每次重试重新生成。"""
    last_err = None
    for attempt in (0, 1):
        headers = _sign_headers(method, url)
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, headers=headers, method=method, data=data)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = "HTTP {} {}".format(e.code, e.reason)
            _log("{} {} -> {} (try={})".format(method, path_hint(url), last_err, attempt))
        except Exception as e:
            last_err = str(e)
            _log("{} {} -> {} (try={})".format(method, path_hint(url), last_err, attempt))
        if attempt == 0:
            time.sleep(0.4)
    raise RuntimeError(last_err or "request_failed")


def path_hint(url):
    u = urllib.parse.urlsplit(url)
    q = u.query[:60]
    return u.path + (("?" + q) if q else "")


def _build_url(path, **params):
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return SITE + path + (("?" + query) if query else "")


# ---------------------- 端点封装 ----------------------
def _feed_cards():
    key = "feed:home"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    data = _request_json(_build_url("/v1/feed/home", scope="public", mode="preview",
                                    sections=3, cards=10))
    cards, seen = [], set()
    for sec in data.get("sections", []) or []:
        for c in sec.get("cards", []) or []:
            cid = c.get("id")
            if cid and cid not in seen:
                seen.add(cid)
                cards.append(c)
    _cache_set(key, cards, _CACHE_TTL["feed"])
    return cards


def _browse_cards(params):
    cache_key = "browse:" + json.dumps(params, sort_keys=True, ensure_ascii=False)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    data = _request_json(_build_url("/v1/browse/catalog", **params))
    cards = data.get("cards", []) or []
    pag = data.get("pagination", {}) or {}
    out = (cards, pag.get("total"), pag.get("has_more", len(cards) > 0))
    _cache_set(cache_key, out, _CACHE_TTL["browse"])
    return out


def _catalog_detail(vod_id):
    key = "catalog:" + vod_id
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        data = _request_json(_build_url("/v1/catalog/" + urllib.parse.quote(vod_id, safe="")))
    except Exception:
        data = {}
    _cache_set(key, data, _CACHE_TTL["catalog"])
    return data


def _resolve_first(episode_token):
    """第一层：线路元数据（不含 ticket，可缓存）"""
    key = "resolve_meta:" + episode_token
    cached = _cache_get(key)
    if cached is not None:
        return cached
    data = _request_json(_build_url("/v1/playback/resolve/" +
                                    urllib.parse.quote(episode_token, safe=""), view="compact"))
    lines = []
    for line in (data.get("line_options", []) or []):
        lines.append({
            "label": line.get("label") or line.get("play_from") or line.get("id") or "线路",
            "play_from": line.get("play_from") or "",
            "url": line.get("url") or "",
            "default_priority": line.get("default_priority"),
            "preference_weight": line.get("preference_weight") or 0,
        })
    _cache_set(key, lines, _CACHE_TTL["resolve_meta"])
    return lines


def _resolve_line(ticket, timeout=15):
    """第二层：POST resolve-line 拿真实直链（ticket 一次性，绝不缓存）"""
    data = _request_json(_build_url("/v1/playback/resolve-line", view="compact"),
                         method="POST", body={"ticket": ticket}, timeout=timeout)
    line = data.get("line") or {}
    return line.get("url") or ""


# ============================================================
# 通用能力：Probe 探针 + 线路降级
# ============================================================
def _probe_ticket(ticket, timeout=8):
    """Probe 探针：探测 ticket 能否匿名解析，返回 (ok, code, err)"""
    try:
        url = _build_url("/v1/playback/resolve-line", view="compact")
        data = _request_json(url, method="POST", body={"ticket": ticket}, timeout=timeout)
        real = ((data.get("line") or {}).get("url") or "").strip()
        return (bool(real), 200, "ok" if real else "empty_url")
    except urllib.error.HTTPError as e:
        return (False, e.code, "http_%s:%s" % (e.code, e.reason))
    except Exception as e:
        return (False, None, str(e))


def _sort_line_candidates(lines, flag):
    """线路排序：flag 精确匹配 > default_priority > preference_weight"""
    def _rank(line):
        label = line.get("label") or line.get("play_from") or ""
        hit = 1 if (flag and (label == flag or line.get("play_from") == flag)) else 0
        return (hit, 1 if line.get("default_priority") else 0,
                float(line.get("preference_weight") or 0))
    return sorted(lines, key=_rank, reverse=True)


def _downgrade_play_resolve(lines, flag):
    """线路降级主逻辑：探针预筛 + 逐线尝试，返回 (result, last_err)"""
    candidates = _sort_line_candidates(lines, flag)
    last_err = ""
    for line in candidates[:PLAY_MAX_TRY_LINE]:
        raw_url = line.get("url") or ""
        if raw_url.startswith("resolve://"):
            ticket = raw_url[len("resolve://"):]
        else:
            ticket = raw_url
        if not ticket:
            continue
        if PLAY_PROBE_FILTER:
            ok, code, msg = _probe_ticket(ticket, timeout=6)
            if not ok:
                last_err = msg
                _log("[probe skip] 线路:%s code=%s msg=%s" % (line.get("label"), code, msg))
                continue
        try:
            real = _resolve_line(ticket)
            if real:
                return ({"parse": 0, "url": real,
                         "header": {"User-Agent": UA, "Referer": SITE + "/"}}, "")
        except Exception as e:
            last_err = str(e)
            _log("[downgrade fail] 线路:%s err=%s" % (line.get("label"), e))
    return ({"parse": 1, "url": "",
             "header": {"User-Agent": UA, "Referer": SITE + "/"}}, last_err)


# ---------------------- 数据转换 ----------------------
def _as_str(v):
    return "" if v is None else str(v)


def _card_to_vod(card):
    vod = {
        "vod_id": card.get("id") or card.get("detail_url") or "",
        "vod_name": card.get("title") or "",
        "vod_pic": card.get("poster_url") or card.get("backdrop_url") or "",
        "vod_remarks": card.get("remarks") or "",
        "vod_year": _as_str(card.get("year")),
        "vod_area": card.get("area") or "",
        "vod_lang": card.get("language") or "",
        "vod_actor": " / ".join(card.get("actors", []) or []),
        "vod_director": " / ".join(card.get("directors", []) or []),
    }
    if not vod["vod_remarks"]:
        kind = card.get("content_kind") or ""
        label = next((c["type_name"] for c in CLASS_LIST if c["type_id"] == kind), kind)
        vod["vod_remarks"] = label
    return vod


def _episodes_to_play_url(episodes):
    parts = []
    for ep in episodes or []:
        title = (ep.get("title") or "").strip()
        if not title:
            num = ep.get("number") or ep.get("sequence_index") or len(parts) + 1
            title = "第{}集".format(num)
        token = ep.get("token") or ""
        if token:
            parts.append("{}${}".format(title, token))
    return "#".join(parts)


# ---------------------- TVBox 六接口 ----------------------
def home_content(filter_=False):
    return {"class": [dict(c) for c in CLASS_LIST],
            "list": [_card_to_vod(c) for c in _feed_cards()[:60]]}


def category_content(tid, pg="1", filter_=False):
    """分类过滤参数实测为 kind（content_kind 无效，假阳性）"""
    try:
        page = max(1, int(pg))
    except Exception:
        page = 1
    cards, total, has_more = _browse_cards({"kind": tid, "page": page, "limit": 20})
    lst = [_card_to_vod(c) for c in cards]
    total = total if isinstance(total, int) and total > 0 else page * 20 + (20 if has_more else 0)
    return {"list": lst, "page": page, "pagecount": max(1, (total + 19) // 20), "total": total}


def detail_content(ids):
    vod_id = ""
    if isinstance(ids, (list, tuple)):
        vod_id = ids[0] if ids else ""
    else:
        vod_id = ids or ""
    if isinstance(vod_id, str) and vod_id.startswith("/v1/catalog/"):
        vod_id = vod_id.rsplit("/", 1)[-1]
    if not vod_id:
        return {"list": []}

    d = _catalog_detail(vod_id)
    if not d or not d.get("episodes"):
        return {"list": []}

    episodes = d.get("episodes") or []
    play_url = _episodes_to_play_url(episodes)

    # 多线路：用第一集线路标签作为播放源；失败回退单线路
    first_token = next((e.get("token") for e in episodes if e.get("token")), None)
    lines = []
    try:
        if first_token:
            lines = _resolve_first(first_token)
    except Exception:
        lines = []
    flags = []
    for line in lines:
        label = line.get("label") or line.get("play_from") or "线路"
        if label not in flags:
            flags.append(label)
    if not flags:
        flags = ["souju"]

    vod = {
        "vod_id": vod_id,
        "vod_name": d.get("title") or "",
        "vod_pic": d.get("poster_url") or "",
        "vod_year": _as_str(d.get("year")),
        "vod_area": d.get("area") or "",
        "vod_lang": d.get("language") or "",
        "vod_remarks": d.get("remarks") or "",
        "vod_actor": " / ".join(d.get("actors", []) or []),
        "vod_director": " / ".join(d.get("directors", []) or []),
        "vod_content": (d.get("description") or "").strip() or d.get("remarks") or "",
        "vod_play_from": "$$$".join(flags),
        "vod_play_url": "$$$".join([play_url] * len(flags)),
    }
    return {"list": [vod]}


def search_content(key, quick=False, pg="1"):
    try:
        page = max(1, int(pg))
    except Exception:
        page = 1
    key = (key or "").strip()
    if not key:
        return {"list": []}
    cards, total, has_more = _browse_cards({"q": key, "page": page, "limit": 20})
    lst = [_card_to_vod(c) for c in cards]
    total = total if isinstance(total, int) and total > 0 else page * 20 + (20 if has_more else 0)
    return {"list": lst, "page": page, "pagecount": max(1, (total + 19) // 20), "total": total}


def play_parse(flag, id_, flags=None):
    """播放解析：token -> 第一层线路 -> 降级逐线尝试（Probe 预筛）"""
    token = (id_ or "").strip()
    if not token:
        return {"parse": 1, "url": "", "header": {"User-Agent": UA, "Referer": SITE + "/"}}
    if flag is None:
        flag = ""
    try:
        lines = _resolve_first(token)
    except Exception as e:
        _log("[play resolve fail]", e)
        return {"parse": 1, "url": "", "header": {"User-Agent": UA, "Referer": SITE + "/"}}
    if not lines:
        return {"parse": 1, "url": "", "header": {"User-Agent": UA, "Referer": SITE + "/"}}
    result, last_err = _downgrade_play_resolve(lines, flag)
    if last_err:
        _log("[play all line fail]", last_err)
    return result


def local_proxy(param):
    """播放直链为公网 https，无需本地代理。"""
    return None


# ---------------------- 双导出（py-drpy / hipy 规范，同 xmf.py） ----------------------
def home_vod_content():
    try:
        return {"list": home_content().get("list", [])}
    except Exception:
        return {"list": []}


exports = {
    "homeContent": home_content,
    "homeVideoContent": home_vod_content,
    "categoryContent": category_content,
    "detailContent": detail_content,
    "searchContent": search_content,
    "playerContent": play_parse,
    "playContent": play_parse,
    "localProxy": local_proxy,
}

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider(object):
        pass


class Spider(_BaseSpider):
    def getName(self):
        return "搜剧AI-13"

    def init(self, extend=""):
        return ""

    def destroy(self):
        return ""

    def isVideoFormat(self, url):
        try:
            u = str(url or "").lower()
            return u.startswith("http://") or u.startswith("https://")
        except Exception:
            return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return local_proxy(param)

    def homeContent(self, filter=False):
        try:
            return home_content(filter)
        except Exception:
            return {"class": [], "list": []}

    def homeVideoContent(self):
        try:
            return {"list": home_content().get("list", [])}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg="1", filter=False, extend={}):
        try:
            return category_content(tid, pg, filter)
        except Exception:
            return {"list": [], "page": int(pg or 1), "pagecount": 1, "total": 0}

    def detailContent(self, ids):
        try:
            return detail_content(ids)
        except Exception:
            return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            return search_content(key, quick, pg)
        except Exception:
            return {"list": []}

    def playerContent(self, flag, id_=None, vipFlags=None):
        try:
            return play_parse(flag, id_, vipFlags)
        except Exception:
            return {"parse": 1, "url": "", "header": {"User-Agent": UA, "Referer": SITE + "/"}}


# ---------------------- 自测（防假阳性 + Probe 挑匿名样本） ----------------------
def _pick_anon_sample_vid(max_probe=6):
    """自动挑选一条探针通过（可匿名播放）的影片 id，跳过需登录内容。
    限制探测数量避免自测超时；优先 feed 前部卡片。
    注意：probe 用的是第一层线路的 ticket（resolve:// 去掉前缀），
    不是 episode token（episode token 不是播放标识，会 400）。"""
    feed = _feed_cards()
    tried = 0
    for card in feed:
        vid = card.get("id")
        if not vid:
            continue
        if card.get("content_kind") in ("variety",):
            continue
        tried += 1
        if tried > max_probe:
            break
        d = _catalog_detail(vid)
        eps = d.get("episodes") or []
        tok = next((e.get("token") for e in eps if e.get("token")), None)
        if not tok:
            continue
        try:
            lines = _resolve_first(tok)
        except Exception:
            continue
        for line in lines:
            raw = line.get("url") or ""
            ticket = raw[len("resolve://"):] if raw.startswith("resolve://") else raw
            if not ticket:
                continue
            ok, _, _ = _probe_ticket(ticket)
            if ok:
                return vid
    return None


def _selftest():
    results = []

    def check(name, fn):
        try:
            r = fn()
            ok = bool(r)  # 兼容返回字符串/真值的校验函数，杜绝假 FAIL
        except Exception as e:
            ok = False
            r = "EXC: %s" % e
        results.append((name, ok, r))
        print("[{}] {}".format("PASS" if ok else "FAIL", name))

    def is_vod(v):
        return bool(isinstance(v, dict) and v.get("vod_id") and v.get("vod_name"))

    def t_home():
        r = home_content()
        return bool(r.get("class")) and bool(r.get("list")) and is_vod(r["list"][0])
    check("homeContent: class+list 非空", t_home)

    def t_category():
        r = category_content("series", "1")
        if not r.get("list") or not is_vod(r["list"][0]):
            return False
        cards, _, _ = _browse_cards({"kind": "series", "page": 1, "limit": 20})
        return bool(cards) and cards[0].get("content_kind") == "series"
    check("categoryContent(series) 列表+过滤生效", t_category)

    def t_search():
        r = search_content("流浪地球")
        return bool(r.get("list")) and is_vod(r["list"][0])
    check("searchContent('流浪地球') 命中结果", t_search)

    def t_detail():
        cards, _, _ = _browse_cards({"kind": "series", "page": 1, "limit": 20})
        if not cards:
            return False
        r = detail_content(cards[0].get("id"))
        if not r.get("list"):
            return False
        v = r["list"][0]
        return bool(v.get("vod_play_from")) and bool(v.get("vod_play_url")) and "$" in v.get("vod_play_url", "")
    check("detailContent 生成多集播放串", t_detail)

    def t_play():
        vid = _pick_anon_sample_vid()
        if not vid:
            return False
        d = _catalog_detail(vid)
        eps = d.get("episodes") or []
        tok = next((e.get("token") for e in eps if e.get("token")), None)
        if not tok:
            return False
        r = play_parse("souju", tok)
        return r.get("parse") == 0 and str(r.get("url") or "").startswith("http")
    check("playContent 拿到真实播放直链(匿名样本)", t_play)

    failed = [n for n, ok, _ in results if not ok]
    print("\n自测结果: {}/{} 通过".format(len(results) - len(failed), len(results)))
    if failed:
        print("失败项: {}".format(", ".join(failed)))
        return 1
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if "--debug" not in sys.argv:
        _DEBUG = False
    if len(sys.argv) > 1:
        cmd, args = sys.argv[1], sys.argv[2:]
        if cmd == "home":
            print(json.dumps(home_content(), ensure_ascii=False)[:4000])
        elif cmd == "cat":
            print(json.dumps(category_content(args[0] if args else "series",
                                              args[1] if len(args) > 1 else "1"),
                             ensure_ascii=False)[:4000])
        elif cmd == "detail":
            print(json.dumps(detail_content(args), ensure_ascii=False)[:3000])
        elif cmd == "search":
            print(json.dumps(search_content(args[0] if args else ""), ensure_ascii=False)[:3000])
        elif cmd == "play":
            print(json.dumps(play_parse("", args[0] if args else ""), ensure_ascii=False)[:2000])
        else:
            print("用法: python3 py_souju13.py --selftest [--debug] | home | cat <tid> | detail <id> | search <kw> | play <id>")
    else:
        print("用法: python3 py_souju13.py --selftest [--debug] | home | cat <tid> | detail <id> | search <kw> | play <id>")
