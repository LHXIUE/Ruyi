# coding: utf-8
# 蜜桃源｜基于实际网站结构重写
# 核心发现：API已关闭，首页双重base64加密，必须走静态HTML解析
import re
import json
import base64
import urllib.parse
from base.spider import Spider as BaseSpider

class Spider(BaseSpider):
    def __init__(self):
        self.host = "http://cl2.xbl2.pro"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"{self.host}/",
        }
        self.classes = [
            {"type_id": "5",  "type_name": "国产精选"},
            {"type_id": "3",  "type_name": "黑料吃瓜"},
            {"type_id": "4",  "type_name": "厂牌原创"},
            {"type_id": "6",  "type_name": "明星换脸"},
            {"type_id": "7",  "type_name": "AV解说"},
            {"type_id": "8",  "type_name": "禁漫精选"},
            {"type_id": "28", "type_name": "国产大片"},
            {"type_id": "87", "type_name": "日韩大片"},
            {"type_id": "31", "type_name": "欧美大片"},
            {"type_id": "32", "type_name": "网红直播"},
            {"type_id": "33", "type_name": "探花约炮"},
            {"type_id": "88", "type_name": "SM调教"},
            {"type_id": "34", "type_name": "三级伦理"},
            {"type_id": "35", "type_name": "萝莉开苞"},
            {"type_id": "10", "type_name": "父女"},
            {"type_id": "11", "type_name": "母子"},
            {"type_id": "12", "type_name": "兄妹"},
            {"type_id": "13", "type_name": "学生"},
            {"type_id": "14", "type_name": "嫂子"},
            {"type_id": "15", "type_name": "姐夫"},
            {"type_id": "16", "type_name": "师生"},
            {"type_id": "17", "type_name": "全家"},
            {"type_id": "79", "type_name": "真实缅北"},
            {"type_id": "80", "type_name": "恶心恐怖"},
            {"type_id": "81", "type_name": "黄金圣水"},
            {"type_id": "82", "type_name": "校园霸凌"},
            {"type_id": "83", "type_name": "战场实录"},
            {"type_id": "84", "type_name": "人兽乱交"},
            {"type_id": "85", "type_name": "灵异视频"},
            {"type_id": "86", "type_name": "N号房"},
        ]
        self.filters = {}

    def getName(self):
        return "蜜桃源"

    def getDependence(self):
        return []

    def init(self, extend=""):
        self.extend = extend

    # ====================== 核心工具：请求并解密页面 ======================
    def _fetch_decoded(self, url):
        try:
            resp = self.fetch(url, headers=self.headers, timeout=15000)
            if not resp or not hasattr(resp, "text"):
                return None
            html = resp.text
            matches = re.findall(r"var str = '([^']+)'", html)
            if matches and len(matches[0]) > 1000:
                try:
                    first = base64.b64decode(matches[0]).decode('utf-8')
                    second = base64.b64decode(first).decode('utf-8')
                    return second
                except Exception:
                    pass
            return html
        except Exception:
            return None

    def _fix_url(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.host + url
        if not url.startswith("http"):
            return f"{self.host}/{url.lstrip('/')}"
        return url

    # ====================== 首页分类 ======================
    def homeContent(self, filter):
        return {"class": self.classes, "filters": self.filters if filter else {}}

    def getHomeContent(self, filter):
        return self.homeContent(filter)

    def homeVideoContent(self):
        return self.categoryContent("5", "1", False, {})

    # ====================== 分类列表 ======================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
            page = max(page, 1)
        except:
            page = 1
        if page == 1:
            url = f"{self.host}/index.php/vod/type/id/{tid}.html"
        else:
            url = f"{self.host}/index.php/vod/type/id/{tid}/page/{page}.html"
        html = self._fetch_decoded(url)
        videos = []
        pagecount = page
        if html:
            pattern = r'<li class="content-item"[^>]*>.*?<a[^>]*href="(/index\.php/vod/detail/id/(\d+)\.html)"[^>]*title="([^"]*)"[^>]*>(.*?)</a>.*?</li>'
            items = re.findall(pattern, html, re.DOTALL)
            for href, vid, title, inner in items:
                title = title.strip()
                imgs = re.findall(r'<img[^>]*src="([^"]*)"', inner)
                real_pic = ""
                for img in imgs:
                    if "faiusr.com" not in img and ".gif" not in img:
                        real_pic = img
                        break
                if not real_pic and imgs:
                    real_pic = imgs[-1]
                real_pic = self._fix_url(real_pic)
                videos.append({
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": real_pic,
                    "vod_remarks": ""
                })
            page_links = re.findall(r'href="/index\.php/vod/type/id/\d+/page/(\d+)\.html"', html)
            if page_links:
                max_page = max([int(p) for p in page_links])
                pagecount = max(page, max_page)
        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20
        }

    # ====================== 详情页 ======================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        if "|$|" in vod_id:
            parts = vod_id.split("|$|")
            vod_id = parts[0]
        url = f"{self.host}/index.php/vod/detail/id/{vod_id}.html"
        html = self._fetch_decoded(url)
        if not html:
            return {"list": []}
        title = ""
        title_match = re.search(r'<title>([^<]*)</title>', html)
        if title_match:
            title = title_match.group(1).split('-')[0].strip()
            title = re.sub(r'详情介绍$', '', title).strip()
        pic = ""
        img_match = re.search(r'<img[^>]*src="(https?://aisearch\.cdn\.bcebos\.com/[^"]*)"', html)
        if img_match:
            pic = img_match.group(1)
        play_links = re.findall(
            r'href="(/index\.php/vod/play/id/\d+/sid/(\d+)/nid/(\d+)\.html)"[^>]*>([^<]*)</a>',
            html
        )
        sources = {}
        for href, sid, nid, name in play_links:
            sid = int(sid)
            if sid not in sources:
                sources[sid] = []
            sources[sid].append({
                "name": name.strip() or f"第{nid}集",
                "url": f"{self.host}{href}"
            })
        source_names = []
        source_urls = []
        for sid in sorted(sources.keys()):
            source_names.append(f"线路{sid}")
            episodes = sources[sid]
            ep_str = "#".join([f"{ep['name']}${ep['url']}" for ep in episodes])
            source_urls.append(ep_str)
        vod_info = {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": "",
            "vod_content": title,
            "vod_play_from": "$$$".join(source_names) if source_names else "蜜桃源",
            "vod_play_url": "$$$".join(source_urls) if source_urls else ""
        }
        return {"list": [vod_info]}

    # ====================== 搜索 ======================
    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg)
            page = max(page, 1)
        except:
            page = 1
        encoded_key = urllib.parse.quote(key)
        if page == 1:
            url = f"{self.host}/index.php/vod/search.html?wd={encoded_key}"
        else:
            url = f"{self.host}/index.php/vod/search/page/{page}.html?wd={encoded_key}"
        html = self._fetch_decoded(url)
        videos = []
        if html:
            pattern = r'<li class="content-item"[^>]*>.*?<a[^>]*href="(/index\.php/vod/detail/id/(\d+)\.html)"[^>]*title="([^"]*)"[^>]*>(.*?)</a>.*?</li>'
            items = re.findall(pattern, html, re.DOTALL)
            for href, vid, title, inner in items:
                title = title.strip()
                imgs = re.findall(r'<img[^>]*src="([^"]*)"', inner)
                real_pic = ""
                for img in imgs:
                    if "faiusr.com" not in img and ".gif" not in img:
                        real_pic = img
                        break
                if not real_pic and imgs:
                    real_pic = imgs[-1]
                real_pic = self._fix_url(real_pic)
                videos.append({
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": real_pic,
                    "vod_remarks": ""
                })
        return {"list": videos, "page": page}

    # ====================== 播放器解析 ======================
    def playerContent(self, flag, id, vipFlags):
        play_url = id
        if not play_url.startswith("http"):
            play_url = self._fix_url(play_url)
        if play_url.endswith((".m3u8", ".mp4", ".ts", ".flv")):
            return {"parse": 0, "url": play_url, "header": self.headers}
        html = self._fetch_decoded(play_url)
        if not html:
            return {"parse": 1, "url": play_url, "header": self.headers}
        player_match = re.search(r'var player_aaaa=({.*?})</script>', html)
        if player_match:
            try:
                player_data = json.loads(player_match.group(1))
                real_url = player_data.get("url", "").replace(chr(92) + "/", "/")
                if real_url and real_url.endswith((".m3u8", ".mp4", ".ts", ".flv")):
                    return {"parse": 0, "url": real_url, "header": self.headers}
            except Exception:
                pass
        media = re.search(r'(https?://[^\s"\'\;]+\.(?:m3u8|mp4|ts|flv))', html)
        if media:
            return {"parse": 0, "url": media.group(1), "header": self.headers}
        iframe = re.search(r'<iframe[^>]+src="([^"]+)"', html)
        if iframe:
            iframe_src = self._fix_url(iframe.group(1))
            return {"parse": 1, "url": iframe_src, "header": self.headers}
        return {"parse": 1, "url": play_url, "header": self.headers}

    def isVideoFormat(self, url):
        return url.endswith((".m3u8", ".mp4", ".ts", ".flv"))

    def destroy(self):
        pass