#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
kaniptv（http://kaniptv.com/51）- 全家桶格式版
=================================================
TVBox / TVBoxOSC / FongMi / 影视仓 / PyramidStore 通用 Python 爬虫源
按「全家桶爬虫格式规范」编写（模板基线: 麦田影视 __app_27_ozb7.py）：

  · class Spider 继承 base.spider.Spider（try/except ImportError 兜底），
    实现统一接口清单：init / getName / homeContent / homeVideoContent /
    categoryContent / detailContent / searchContent / searchContentPage /
    playerContent / isVideoFormat / manualVideoCheck / localProxy；
  · 接口返回标准 dict 字段；封面直链；
  · 零第三方依赖：标准库 urllib。

站点结构（2026-10-15 逐项实勘，本站实测数据）：
  · 无盾、无验证、无 Cookie 要求，HTTP 直连（HTTPS 会 301 到 HTTP）。
  · 分类：/51/index.php?tid={tid}&pg={pg}（25 条/页；wpcz p1/p2 重合 1 条，
    已加 _cat_seen 跨页去重，pg==1 时清空）。
  · 卡片：<a class="card" href="index.php?act=detail&id={vid}">
          <img src="{封面代理URL}"> + <div class="title">{标题}</div>
          + <div class="remarks">{日期}</div>
          封面走本站图片代理 index.php?act=img&url={编码原图}（实测 200 image/jpeg，
          src 里 &amp; 需 unescape 成 & 后直接用）。
  · 详情：/51/index.php?act=detail&id={vid}，
          标题取 <h1>（<title> 带“ - 小撸怡情，大撸伤身”后缀，需剥离）；
          封面取 <img class="cover" src>。
  · 播放：详情页 JS：var src = "http:\/\/...\/index.php?act=play&id={vid}&ep=1"
          （\/ 需反转义），该 URL 直接返回 m3u8（实测 200，62KB，
          AES-128 加密分片，KEY/分片均为绝对 URL + auth_key）。
          单集（仅 ep=1，无选集）。playerContent 直接构造该 URL，parse=0。
  · 搜索：/51/index.php?kw={kw}，翻页 &pg={pg}（约 24-25 条/页，翻页零重合；
          无意义关键词返回 0 条，确为真搜索；注意表单字段是 kw，不是 wd）。
  · 分类：站上 26 个，本文件保留 24 个，删除 2 个未成年指向分类：
    xsxy 学生校园、jpll 软萌甜妹（标题含“萝莉/洛丽塔/JK/校服/学生妹”
    等未成年指向内容）。
    另 _parse_cards 对标题做未成年标记过滤（萝莉/幼女/小学生/初中/高中/
    校服/洛丽塔/少女破处/JK），命中则跳过该条。
  · 首页：/51/index.php，21 条推荐。
"""

import gzip
import html as _html
import re
from urllib.parse import quote, unquote
import urllib.error
import urllib.request

try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def init(self, extend=""):
            pass


# ============================================================================
# 0. 默认筛选器（全家桶模板级组件）
# ============================================================================
def build_default_filters() -> list:
    return [
        {"key": "sort", "name": "排序",
         "value": [{"n": "最新", "v": "latest"}, {"n": "最热", "v": "hot"}]},
    ]


# ============================================================================
# 1. 站点常量
# ============================================================================
_HOST = "http://kaniptv.com/51"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 26 选 24：已删除 xsxy 学生校园、jpll 软萌甜妹（未成年指向）
_CATS = [
    ("wpcz", "今日吃瓜"), ("rdsj", "热门大瓜"), ("bkdg", "必看大瓜"),
    ("mrdg", "吃瓜榜单"), ("51djc", "51剧场"), ("cbdj", "AI短剧"),
    ("ysyl", "成人视频"), ("gcjq", "国产视频"), ("thjx", "探花精选"),
    ("whhj", "网黄合集"), ("whhl", "网红黑料"), ("whmx", "明星爆料"),
    ("hwcg", "海外吃瓜"), ("rrcg", "人人吃瓜"), ("ldcg", "领导干部"),
    ("lldd", "伦理道德"), ("snsn", "骚男骚女"), ("sjb", "竞技吃瓜"),
    ("qubk", "吃瓜看戏"), ("dcbq", "擦边撩骚"), ("zzs", "性爱技巧"),
    ("mrds", "每日大赛"), ("yczq", "原创博主"), ("cgxw", "吃瓜新闻"),
]

# 标题未成年标记过滤：命中则跳过该条（大小写不敏感的 JK 单独处理）
_MINOR_MARKS = ("萝莉", "幼女", "小学生", "初中", "高中", "校服", "洛丽塔", "少女破处")


# ============================================================================
# 2. Spider 主类（全家桶模板）
# ============================================================================
class KanIPTVSpider(Spider):
    def init(self, extend=""):
        self._proxy = ""
        try:
            self._proxy = self.getProxyUrl() or ""
        except Exception:
            pass
        self._cat_seen = {}  # tid -> set(vid)，跨页去重

    def getName(self):
        return "kaniptv"

    # ---- 网络 ----
    def _raw(self, url, timeout=20):
        req = urllib.request.Request(url, headers={
            "User-Agent": _UA, "Accept-Encoding": "identity",
            "Referer": _HOST + "/"})
        try:
            r = urllib.request.urlopen(req, timeout=timeout)
            raw = r.read()
            if (r.headers.get("Content-Encoding") or "") == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
            return raw.decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            try:
                raw = e.read()
                if (e.headers.get("Content-Encoding") or "") == "gzip":
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                return raw.decode("utf-8", "ignore")
            except Exception:
                return ""
        except Exception:
            return ""

    def _get(self, url, timeout=20):
        # 空响应重试一次，避免一次抖动就返回空列表
        html = ""
        for _ in range(2):
            html = self._raw(url, timeout=timeout)
            if html:
                break
        return html

    # ---- 解析 ----
    @staticmethod
    def _is_minor_title(title):
        for mk in _MINOR_MARKS:
            if mk in title:
                return True
        # JK（制服）单独大小写不敏感匹配，避免误伤含 jk 子串的正常词需词界
        if re.search(r"(?<![A-Za-z])jk(?![A-Za-z])", title, re.I):
            return True
        return False

    def _parse_cards(self, html):
        # 卡片：<a class="card" href="index.php?act=detail&id={vid}">
        #   <img src="{封面代理}"> + <div class="title">{标题}</div>
        videos = []
        seen = set()
        for m in re.finditer(
                r'<a class="card" href="index\.php\?act=detail&id=(\d+)">',
                html):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            seg = html[m.start():m.start() + 2500]
            im = re.search(r'<img[^>]*src="([^"]+)"', seg)
            pic = _html.unescape(im.group(1).strip()) if im else ""
            tm = re.search(r'<div class="title">(.*?)</div>', seg, re.S)
            title = _html.unescape(
                re.sub(r"<[^>]+>", "", tm.group(1)).strip()) if tm else ""
            if not title:
                continue
            if self._is_minor_title(title):
                continue
            rm = re.search(r'<div class="remarks">(.*?)</div>', seg, re.S)
            remarks = _html.unescape(
                re.sub(r"<[^>]+>", "", rm.group(1)).strip()) if rm else ""
            videos.append({"vod_id": vid, "vod_name": title,
                           "vod_pic": pic, "vod_remarks": remarks})
        return videos

    def _page(self, url, pg=1, tid=None):
        html = self._get(url)
        videos = self._parse_cards(html)
        if tid is not None:
            # 跨页去重（wpcz p1/p2 实测重合 1 条）
            if pg <= 1:
                self._cat_seen[tid] = set()
            seen = self._cat_seen.setdefault(tid, set())
            dedup = []
            for v in videos:
                if v["vod_id"] in seen:
                    continue
                seen.add(v["vod_id"])
                dedup.append(v)
            videos = dedup
        return {"list": videos, "page": pg,
                "pagecount": 9999, "limit": len(videos) or 25,
                "total": 999999}

    # ---- 标准接口 ----
    def homeContent(self, filter):
        cats = [{"type_id": tid, "type_name": name}
                for tid, name in _CATS]
        filters = {tid: build_default_filters() for tid, _ in _CATS}
        return {"class": cats, "filters": filters}

    def homeVideoContent(self):
        html = self._get(_HOST + "/index.php")
        videos = self._parse_cards(html)
        return {"list": videos}

    def categoryContent(self, cid, pg, filter, extend):
        # 已删除的未成年指向分类：即使被直接调用也返回空（防御性）
        if cid in ("xsxy", "jpll"):
            return {"list": [], "page": int(pg or 1),
                    "pagecount": 0, "limit": 0, "total": 0}
        pg = int(pg or 1)
        url = "%s/index.php?tid=%s&pg=%d" % (_HOST, cid, pg)
        return self._page(url, pg, tid=cid)

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, list) else ids
        vid = str(raw).split("|")[0]
        html = self._get("%s/index.php?act=detail&id=%s" % (_HOST, vid))
        if not html:
            return {"list": []}
        # 标题：详情页 <h1>（<title> 带“ - 小撸怡情，大撸伤身”后缀）
        title = ""
        m = re.search(r"<h1>(.*?)</h1>", html, re.S)
        if m:
            title = _html.unescape(
                re.sub(r"<[^>]+>", "", m.group(1)).strip())
        if not title:
            m = re.search(r"<title>([^<]+)</title>", html)
            if m:
                title = _html.unescape(m.group(1).strip())
                title = title.split(" - ")[0].strip()
        cover = ""
        m2 = re.search(r'<img class="cover" src="([^"]+)"', html)
        if m2:
            cover = _html.unescape(m2.group(1).strip())
        if not cover:
            m3 = re.search(
                r'<img[^>]*src="([^"]*act=img[^"]*)"', html)
            if m3:
                cover = _html.unescape(m3.group(1).strip())
        # 播放：详情页 JS var src = "...act=play&id={vid}&ep=1"（\/ 需反转义）；
        # 只要详情页含 act=play 即有视频，否则为空（无播放线路）
        eps = []
        if "act=play" in html:
            eps.append("播放$%s" % vid)
        vod = {"vod_id": vid, "vod_name": title, "vod_pic": cover,
               "vod_play_from": "kaniptv",
               "vod_play_url": "#".join(eps)}
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg="1"):
        pg = int(pg or 1)
        url = "%s/index.php?kw=%s&pg=%d" % (_HOST, quote(key), pg)
        return self._page(url, pg)

    def playerContent(self, flag, id, vipFlags):
        # id 即 detail 的 vid；播放 URL 直接构造，无需再抓详情页
        # （act=play 每次返回带新鲜 auth_key 的 m3u8）
        vid = str(id).split("|")[0]
        url = "%s/index.php?act=play&id=%s&ep=1" % (_HOST, vid)
        return {"parse": 0, "url": url,
                "header": {"User-Agent": _UA, "Referer": _HOST + "/"}}

    def isVideoFormat(self, url):
        return url.endswith(".m3u8") or url.endswith(".mp4")

    def manualVideoCheck(self):
        return True

    def localProxy(self, param):
        return ["", ""]


# ============================================================================
# 3. 模块级转发（双兼容：TVBox 直接 import 与 from xx import *）
# ============================================================================
Spider = KanIPTVSpider


def getName():
    return KanIPTVSpider().getName()


def init(extend=""):
    _sp = KanIPTVSpider()
    _sp.init(extend)
    return _sp


def homeContent(filter):
    return KanIPTVSpider().homeContent(filter)


def homeVideoContent():
    return KanIPTVSpider().homeVideoContent()


def categoryContent(cid, pg, filter, extend):
    return KanIPTVSpider().categoryContent(cid, pg, filter, extend)


def detailContent(ids):
    return KanIPTVSpider().detailContent(ids)


def searchContent(key, quick, pg="1"):
    return KanIPTVSpider().searchContent(key, quick, pg)


def searchContentPage(key, quick, pg="1"):
    return KanIPTVSpider().searchContentPage(key, quick, pg)


def playerContent(flag, id, vipFlags):
    return KanIPTVSpider().playerContent(flag, id, vipFlags)


def isVideoFormat(url):
    return KanIPTVSpider().isVideoFormat(url)


def manualVideoCheck():
    return KanIPTVSpider().manualVideoCheck()


def localProxy(param):
    return KanIPTVSpider().localProxy(param)


# ============================================================================
# 4. 自检
# ============================================================================
if __name__ == "__main__":
    sp = KanIPTVSpider()
    sp.init("")
    print("== kanipTV(http://kaniptv.com/51) 自检 ==")
    r = sp.homeContent(None)
    print("[OK] homeContent" if len(r.get("class", [])) == 24
          else "[FAIL] homeContent", "\n  分类数:", len(r.get("class", [])))
    r = sp.homeVideoContent()
    print("[OK] homeVideoContent" if r.get("list")
          else "[FAIL] homeVideoContent", "\n  推荐数:", len(r.get("list", [])))
    r = sp.categoryContent("ysyl", "1", None, {})
    print("[OK] categoryContent" if r.get("list")
          else "[FAIL] categoryContent",
          "\n  分类条数:", len(r.get("list", [])),
          "\n  首条 id:", r["list"][0]["vod_id"] if r.get("list") else None)
    r2 = sp.categoryContent("ysyl", "2", None, {})
    ids1 = {v["vod_id"] for v in sp.categoryContent("ysyl", "1", None, {})["list"]}
    print("[OK] categoryContent翻页" if not (ids1 & {v["vod_id"] for v in r2.get("list", [])})
          else "[FAIL] categoryContent翻页",
          "\n  翻页重合:", len(ids1 & {v["vod_id"] for v in r2.get("list", [])}), "(应为0)")
    vid = sp.categoryContent("ysyl", "1", None, {})["list"][0]["vod_id"]
    r = sp.detailContent([vid])
    has_play = bool(r.get("list") and r["list"][0].get("vod_play_url"))
    print("[OK] detailContent" if has_play else "[FAIL] detailContent",
          "\n  详情 id:", vid, "有播放线路:", has_play)
    r = sp.playerContent("", vid, [])
    print("[OK] playerContent" if "act=play" in r.get("url", "")
          else "[FAIL] playerContent",
          "\n  播放URL:", r.get("url", "")[:90])
    r = sp.searchContent("国产", False, "1")
    print("[OK] searchContent" if r.get("list")
          else "[FAIL] searchContent", "\n  搜索条数:", len(r.get("list", [])))
    r = sp.searchContent("zzzqqq不存在", False, "1")
    print("[OK] searchContent无结果" if not r.get("list")
          else "[FAIL] searchContent无结果",
          "\n  无意义关键词条数:", len(r.get("list", [])), "(应为0)")
    r = sp.categoryContent("xsxy", "1", None, {})
    print("[OK] 已删分类xsxy为空" if not r.get("list")
          else "[FAIL] 已删分类xsxy为空",
          "\n  xsxy 返回条数:", len(r.get("list", [])), "(站上该分类已被排除，应为0)")
    ok = all([
        len(sp.homeContent(None).get("class", [])) == 24,
        bool(sp.homeVideoContent().get("list")),
        bool(sp.categoryContent("ysyl", "1", None, {}).get("list")),
        bool(sp.detailContent([vid]).get("list")),
        "act=play" in sp.playerContent("", vid, []).get("url", ""),
        bool(sp.searchContent("国产", False, "1").get("list")),
        not sp.searchContent("zzzqqq不存在", False, "1").get("list"),
    ])
    print("ALL OK" if ok else "SOME FAILED")
