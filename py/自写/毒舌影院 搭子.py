# -*- coding: utf-8 -*-
"""
xnhrsb_spider.py - TVBox 遮天法爬虫源 for 毒舌影视
https://www.xnhrsb.com (PC 域名, 301 跳移动端) / https://m.xnhrsb.com (移动端, 主通道)

参考源结构（毒舌影视.py）兼容：
  - homeContent 返回 dict: {class:[{type_id,type_name}], list:[{vod_id,vod_name,vod_pic,vod_remarks}]}
  - homeVideoContent 返回 {}
  - categoryContent 返回 dict: {list, page, pagecount, limit, total}
  - detailContent 返回 dict: {list:[{vod_id,vod_name,...,vod_play_from,vod_play_url}]}
  - searchContent 返回 dict: {list, page}
  - playerContent 返回 dict: {parse, url, header}
  - class: 电影/电视剧/综艺/动漫/短剧/豆瓣 共 6 项

功能: init / getName / homeContent / homeVideoContent / categoryContent /
      detailContent / searchContent / playerContent / localProxy /
      getDependence / isVideoFormat / manualVideoCheck / destroy
形态: 遮天法模块级下划线函数 + 类驼峰方法双通道, Py2.7(Jython 2.7)/Py3
      双兼容, HTTP 三兼容(requests -> urllib2 -> urllib.request),
      gzip 透明解压, host 双通道自动切换, 挑战页识别重试。
"""

from __future__ import print_function

import sys
import re
import json
import time

try:  # Py2 下设置默认编码
    reload(sys)
    sys.setdefaultencoding('utf-8')
except Exception:
    pass

# ---------------- HTTP 三兼容 ----------------
try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False

try:
    from urllib.parse import quote
    import urllib.request as _urllib_req
    _HAS_URLLIB = True
except Exception:
    from urllib import quote
    import urllib2 as _urllib_req
    _HAS_URLLIB = True

import gzip

try:
    _UNICODE = unicode  # Py2 / Jython
except NameError:
    _UNICODE = None     # Py3

try:
    from html import unescape as _unescape_html
except Exception:
    try:
        from HTMLParser import HTMLParser as _HP

        def _unescape_html(s):
            return _HP().unescape(s)
    except Exception:
        def _unescape_html(s):
            return s

# ---------------- 站点参数 ----------------
DEFAULT_HOST = "https://m.xnhrsb.com"
DEFAULT_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
              "Mobile/15E148 Safari/604.1")
DEFAULT_TIMEOUT = 15

DEFAULT_CLASS = [
    {"type_id": "1",  "type_name": u"电影"},
    {"type_id": "2",  "type_name": u"电视剧"},
    {"type_id": "3",  "type_name": u"综艺"},
    {"type_id": "4",  "type_name": u"动漫"},
    {"type_id": "5",  "type_name": u"短剧"},
    {"type_id": "duoban", "type_name": u"豆瓣"},
]

_CONF = {
    "host": DEFAULT_HOST,
    "hosts": [DEFAULT_HOST, "https://www.xnhrsb.com"],
    "ua": DEFAULT_UA,
    "timeout": DEFAULT_TIMEOUT,
    "class": DEFAULT_CLASS,
}

_CONFIG_LOCK = time.time()


def _norm_conf(extend):
    """解析 init(extend) 传入的配置：JSON 字符串或 dict。"""
    cfg = {}
    if isinstance(extend, dict):
        cfg = extend
    elif isinstance(extend, (str, bytes)) and hasattr(extend, "strip"):
        s = str(extend).strip()
        if s:
            try:
                cfg = json.loads(s)
            except Exception:
                cfg = {}
    if cfg:
        if cfg.get("host"):
            h = str(cfg["host"]).rstrip("/")
            if h and h not in _CONF["hosts"]:
                _CONF["hosts"].insert(0, h)
            _CONF["host"] = h
        if cfg.get("ua"):
            _CONF["ua"] = str(cfg["ua"])
        if cfg.get("timeout"):
            try:
                _CONF["timeout"] = int(cfg["timeout"])
            except Exception:
                pass
        if isinstance(cfg.get("class"), list) and cfg["class"]:
            _CONF["class"] = cfg["class"]


# ---------------- 基础工具 ----------------
def _as_unicode(s):
    if isinstance(s, _UNICODE if _UNICODE else str):
        return s
    if isinstance(s, bytes):
        try:
            return s.decode("utf-8", "replace")
        except Exception:
            return str(s)
    return s


def _as_bytes(s):
    if _UNICODE is not None and isinstance(s, _UNICODE):
        return s.encode("utf-8")
    return s


def _abs(url):
    if not url:
        return ""
    url = _as_unicode(url).strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    host = _CONF["host"]
    if url.startswith("//"):
        return "https:" + url
    return host + (url if url.startswith("/") else "/" + url)


def _strip_tags(s):
    if not s:
        return ""
    return re.sub(r"<[^>]+>", "", s)


def _clean(t):
    t = _unescape_html(t)
    return re.sub(r"\s+", " ", t).strip()


def _gunzip(data):
    if not data:
        return ""
    try:
        return gzip.decompress(data)
    except Exception:
        pass
    try:
        import io
        bio = io.BytesIO(data)
        return gzip.GzipFile(fileobj=bio).read()
    except Exception:
        return ""


def _decode_bytes(data):
    if not data:
        return ""
    if data[:2] == b"\x1f\x8b":
        data = _gunzip(data)
        if not data:
            return ""
    try:
        return data.decode("utf-8", "replace")
    except Exception:
        try:
            return data.decode("gb18030", "replace")
        except Exception:
            return ""


# ---------------- 网络层 ----------------
def _raw_get(url, headers=None, timeout=None):
    if timeout is None:
        timeout = _CONF["timeout"]
    hdrs = {
        "User-Agent": _CONF["ua"],
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,*/*;q=0.8"),
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": _CONF["host"] + "/",
        "Connection": "keep-alive",
    }
    if headers:
        hdrs.update(headers)
    if _HAS_REQUESTS:
        try:
            r = requests.get(url, headers=hdrs, timeout=timeout, verify=False)
            return _decode_bytes(r.content), r.status_code
        except Exception:
            pass
    if _HAS_URLLIB:
        try:
            req = _urllib_req.Request(_as_bytes(url), headers=hdrs)
            resp = _urllib_req.urlopen(req, timeout=timeout)
            raw = resp.read()
            try:
                code = resp.getcode()
            except Exception:
                code = 200
            return _decode_bytes(raw), code
        except Exception:
            return "", 0
    return "", 0


def _next_host():
    h = _CONF["host"]
    for c in _CONF["hosts"]:
        if c != h:
            return c
    return ""


def _swap_host(url, host):
    for c in _CONF["hosts"]:
        if url.startswith(c):
            return host + url[len(c):]
    return url


def _challenge_like(html):
    if not html:
        return True
    low = html[:600].lower()
    if "<html" not in low and "<!doctype" not in low:
        return True
    seg = html[:30000]
    if ("paly_list_btn" in seg or "bt_tit" in seg or "dsshiyitp" in seg
            or "player_" in seg or "dsshiyidt" in seg or "mrb" in seg
            or "dytit" in seg):
        return False
    if len(html) < 5000:
        return True
    markers = ("challenge", "captcha", "sec-cpt", "verify",
               "access denied", "turnstile", "js-sdk")
    for k in markers:
        if k in low:
            return True
    return False


def _http_get(path_or_url, headers=None, timeout=None):
    u = _as_unicode(path_or_url)
    if not (u.startswith("http://") or u.startswith("https://")):
        u = _abs(u)
    html, status = _raw_get(u, headers, timeout)
    if status != 0 and status < 400:
        return html, status
    alt = _next_host()
    if alt:
        html2, status2 = _raw_get(_swap_host(u, alt), headers, timeout)
        if status2 != 0 and status2 < 400:
            _CONF["host"] = alt
            return html2, status2
    return html, status


def _get_html(path):
    html, status = _http_get(path)
    if not html or status == 0:
        return "", "站点请求失败（网络不通或被拦截），请检查网络"
    if status >= 400:
        return "", "站点返回状态码 %d" % status
    if _challenge_like(html):
        alt = _next_host()
        if alt:
            html2, st2 = _http_get(_swap_host(_abs(path), alt))
            if html2 and st2 != 0 and st2 < 400 and not _challenge_like(html2):
                _CONF["host"] = alt
                return html2, ""
        return "", "站点返回防护占位页，请更换网络或稍后再试"
    low = html[:600].lower()
    if "<html" not in low and "<!doctype" not in low:
        return "", "站点返回非 HTML 内容，可能已被防护拦截"
    return html, ""


# ---------------- 列表项解析 ----------------
def _parse_items(html):
    out = []
    for block in re.findall(r"<li>(.*?)</li>", html, re.S):
        m = re.search(r'href="(/dsshiyidt/(\d+)\.html)"', block)
        if not m:
            continue
        vid = m.group(2)
        name = ""
        m2 = re.search(r'<h3[^>]*class="[^"]*dytit[^"]*"[^>]*>\s*'
                       r'<a[^>]*>(.*?)</a>', block, re.S)
        if m2:
            name = _clean(m2.group(1))
        if not name:
            m2 = re.search(r'<img[^>]+alt="([^"]+)"', block)
            if m2:
                name = m2.group(1).strip()
        if not name:
            continue
        pic = ""
        m2 = re.search(r'data-original="(/upload/[^"]+)"', block)
        if not m2:
            m2 = re.search(r'data-original="(https?://[^"]+)"', block)
        if not m2:
            m2 = re.search(r'<img[^>]+src="(/upload/[^"]+)"', block)
        if m2:
            pic = _abs(m2.group(1))
        remarks = ""
        m2 = re.search(r'<span class="qb">([^<]*)</span>', block)
        if m2:
            remarks = m2.group(1).strip()
        out.append({"vod_id": vid, "vod_name": name, "vod_pic": pic,
                    "vod_remarks": remarks})
    return out


# ---------------- 首页区块解析 ----------------
_SECTION_MAP = {
    u"近日更新": u"最近更新",
    u"最新电影": u"电影",
    u"最新电视剧": u"电视剧",
    u"最新综艺": u"综艺",
    u"最新动漫": u"动漫",
    u"最新短剧": u"短剧",
}


def _parse_home(html):
    """解析首页各 bt_tit 区块。"""
    skip = (u"每周推荐", u"友情链接")
    sections = []
    for msec in re.finditer(r'<div class="bt_tit[^"]*"[^>]*>(.*?)</div>',
                            html, re.S):
        tm = re.search(r'<a[^>]*>([^<]+)</a>', msec.group(1))
        if not tm:
            continue
        raw_name = _clean(tm.group(1))
        if not raw_name or raw_name in skip:
            continue
        name = _SECTION_MAP.get(raw_name, raw_name)
        seg = html[msec.end():]
        um = re.search(r'<ul[^>]*>(.*?)</ul>', seg, re.S)
        if not um:
            continue
        items = _parse_items("<ul>" + um.group(1) + "</ul>")
        if not items:
            continue
        sections.append({"list_name": name, "list": items})
    return sections


def _parse_home_recent(html):
    """取「近日更新」区块的视频列表。"""
    for sec in _parse_home(html):
        if sec.get("list_name") == u"最近更新":
            return sec.get("list") or []
    return []


# ---------------- 详情页解析 ----------------
def _parse_detail(did, html):
    name = ""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if m:
        name = _clean(_strip_tags(m.group(1)))
    if not name:
        m = re.search(r"<title>([^<]+?)</title>", html, re.S)
        if m:
            name = m.group(1).strip().split("-")[0].strip()

    pic = ""
    m = re.search(r'<div class="dyimg[^"]*"[^>]*>\s*<img[^>]+'
                  r'(?:data-original|src)="([^"]+)"', html, re.S)
    if m:
        pic = _abs(m.group(1))
    if not pic:
        m = re.search(r'data-original="(/upload/[^"]+)"', html)
        if m:
            pic = _abs(m.group(1))
    if not pic:
        m = re.search(r'<img[^>]+src="(/upload/[^"]+)"', html)
        if m:
            pic = _abs(m.group(1))

    infos = {}
    for li in re.findall(r"<li>(.*?)</li>", html, re.S):
        mm = re.match(r"\s*([^：<>]{1,8})：\s*(.*)", li, re.S)
        if not mm:
            continue
        key = mm.group(1).strip()
        val = _clean(_strip_tags(mm.group(2)))
        if not key or not val or key in infos:
            continue
        infos[key] = val

    vod = {
        "vod_id": did,
        "vod_name": name,
        "vod_pic": pic,
        "type_name": infos.get(u"类型", ""),
        "vod_year": infos.get(u"年份", ""),
        "vod_area": infos.get(u"地区", ""),
        "vod_remarks": infos.get(u"更新", infos.get(u"状态", "")),
        "vod_actor": infos.get(u"主演", ""),
        "vod_director": infos.get(u"导演", ""),
        "vod_content": infos.get(u"简介", ""),
        "vod_play_from": "",
        "vod_play_url": "",
    }

    tabs = []
    skip_tab_kw = (u"影片介绍", u"猜您还喜欢", u"相关推荐", u"评论")
    for tm in re.finditer(r'<div class="ypxingq_t[^"]*"[^>]*>(.*?)</div>',
                          html, re.S):
        txt = _clean(_strip_tags(tm.group(1)))
        if txt and not any(k in txt for k in skip_tab_kw):
            tabs.append(txt)

    lists = []
    # 播放列表容器可能是 <ul> 或 <div class="paly_list_btn">
    for ul in re.finditer(
            r'<(?:ul|div)\s+class="paly_list_btn[^"]*"[^>]*>(.*?)</(?:ul|div)>',
            html, re.S):
        seg = ul.group(1)
        items = []
        for ma in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                              seg, re.S):
            title = _clean(_strip_tags(ma.group(2)))
            href = _abs(ma.group(1))
            if not title or not href:
                continue
            items.append("%s$%s" % (title, href))
        if items:
            lists.append("#".join(items))

    vod["vod_play_from"] = "$$$".join(tabs)
    vod["vod_play_url"] = "$$$".join(lists)
    return vod


# ---------------- 搜索 ----------------
def _quote(key):
    if isinstance(key, bytes):
        try:
            key = key.decode("utf-8")
        except Exception:
            pass
    try:
        return quote(key.encode("utf-8"))
    except Exception:
        return quote(key)


def _suggest_search(key):
    q = _quote(key)
    html, status = _http_get("/ajax/suggest?wd=%s&mid=1" % q)
    if not html or not html.strip().startswith("{"):
        return []
    try:
        j = json.loads(html)
    except Exception:
        return []
    out = []
    for it in (j.get("list") or []):
        vid = it.get("id")
        nm = it.get("name")
        if not vid or not nm:
            continue
        out.append({"vod_id": str(vid), "vod_name": str(nm),
                    "vod_pic": _abs(str(it.get("pic") or "")),
                    "vod_remarks": ""})
    return out


def _html_search(key):
    q = _quote(key)
    html, status = _http_get("/dsshiyisc/-------------.html?wd=%s" % q)
    if not html:
        return []
    return _parse_items(html)


# ============================================================
#  遮天法 Spider 接口（模块级函数全形态）
# ============================================================
def init(extend=""):
    _norm_conf(extend)
    return ""


def getName():
    return "xnhrsb_dushi"


def getDependence():
    return ""


def isVideoFormat(url):
    return False


def manualVideoCheck():
    return False


def destroy():
    pass


def homeContent(filter=False):
    html, tip = _get_html("/")
    if not html:
        return {"class": _CONF["class"], "list": [], "msg": tip}
    vlist = _parse_home_recent(html)
    if not vlist:
        vlist = _parse_items(html)
    return {"class": _CONF["class"], "list": vlist}


def homeVideoContent():
    return {}


def categoryContent(tid, pg, filter=False, extend=""):
    try:
        pg = int(pg)
    except Exception:
        pg = 1
    if pg <= 1:
        path = "/dsshiyitp/%s.html" % tid
    else:
        path = "/dsshiyitp/%s-%d.html" % (tid, pg)
    html, tip = _get_html(path)
    if not html:
        return {"list": [], "page": pg, "pagecount": 9999,
                "limit": 90, "total": 999999}
    vlist = _parse_items(html)
    return {"list": vlist, "page": pg, "pagecount": 9999,
            "limit": 90, "total": 999999}


def detailContent(arr):
    did = arr[0] if isinstance(arr, list) and arr else arr
    did = str(did)
    m = re.search(r"(\d+)", did)
    did = m.group(1) if m else did
    html, tip = _get_html("/dsshiyidt/%s.html" % did)
    if not html:
        return {"list": [], "msg": tip}
    vod = _parse_detail(did, html)
    out = {"list": [vod]}
    if not vod.get("vod_play_from"):
        out["msg"] = "详情未解析到播放源，站点可能改版或线路抽风"
    return out


def searchContent(key, quick=False, pg="1"):
    if not key:
        return {"list": [], "page": pg}
    vlist = _suggest_search(key)
    if not vlist:
        vlist = _html_search(key)
    return {"list": vlist, "page": pg}


def playerContent(flag, id=None, vipFlags=None):
    # 兼容旧调用：playerContent(ids) — 单参数当作 id
    if id is None:
        id = flag
        flag = ""
    # 将 vid-sid-nid 格式转成播放页路径
    pid = str(id) if id else ""
    if pid and not pid.startswith("http") and not pid.startswith("/"):
        if re.match(r"^\d+-\d+-\d+$", pid):
            pid = "/dsshiyipy/%s.html" % pid
    play_url = _abs(pid)
    if not play_url:
        return {"parse": 0, "url": "", "header": {"User-Agent": _CONF["ua"]}}
    if ".m3u8" in play_url:
        return {"parse": 0, "url": play_url,
                "header": {"User-Agent": _CONF["ua"]}}
    html, status = _http_get(play_url)
    if html:
        m = re.search(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', html)
        if m:
            real = m.group(1).replace("\\/", "/")
            return {"parse": 0, "url": real,
                    "header": {"User-Agent": _CONF["ua"]}}
    return {"parse": 0, "url": play_url,
            "header": {"User-Agent": _CONF["ua"]}}


def localProxy(param):
    return None


# ---------------- 类式通道（壳端通常走这里） ----------------
class Spider(object):
    def __init__(self):
        self.init("")

    def init(self, extend=""):
        return init(extend)

    def getName(self):
        return getName()

    def getDependence(self):
        return getDependence()

    def isVideoFormat(self, url):
        return isVideoFormat(url)

    def manualVideoCheck(self):
        return manualVideoCheck()

    def destroy(self):
        return destroy()

    def homeContent(self, filter=False):
        return homeContent(filter)

    def homeVideoContent(self):
        return homeVideoContent()

    def categoryContent(self, tid, pg, filter=False, extend=""):
        return categoryContent(tid, pg, filter, extend)

    def detailContent(self, arr):
        return detailContent(arr)

    def searchContent(self, key, quick=False, pg="1"):
        return searchContent(key, quick, pg)

    def playerContent(self, flag, id=None, vipFlags=None):
        return playerContent(flag, id, vipFlags)

    def localProxy(self, param):
        return localProxy(param)


# ---------------- 自检 ----------------
if __name__ == "__main__":
    print("接口自检:")
    print("  getName      :", getName())
    hc = homeContent(False)
    print("  homeContent  : class=%d list=%d" %
          (len(hc.get("class", [])), len(hc.get("list", []))))
    cc = categoryContent("1", 1)
    print("  category     : list=%d 首条=%s" %
          (len(cc.get("list", [])),
           (cc.get("list") or [{}])[0].get("vod_name", "")))
    sc = searchContent(u"仙逆")
    print("  searchContent: list=%d" % len(sc.get("list", [])))
    dc = detailContent(["282069"])
    d = (dc.get("list") or [{}])[0]
    print("  detail       : name=%s from=%s" %
          (d.get("vod_name", ""), (d.get("vod_play_from", "") or "")[:60]))
    pc = playerContent("", "282069-1-1")
    print("  playerContent: url=%s" % (pc.get("url", "")[:80]))
    # 类通道一致性
    s = Spider()
    hc2 = s.homeContent(False)
    assert len(hc2.get("class", [])) == 6 and len(hc2.get("list", [])) > 0
    print("  类通道 homeContent 一致: OK")
