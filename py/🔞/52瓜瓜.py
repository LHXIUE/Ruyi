# -*- coding: utf-8 -*-
"""
52瓜瓜 (52gggg) — TVBox/影视仓 Python Spider
=================================================
站点架构: MacCMS (52gggg 自定义模板)
  - 首页: /index.html
  - 分类页: /vodtype/{id}-{page}.html  (分页格式 /vodtype/{id}-{page}.html)
  - 详情页: /voddetail/{id}.html
  - 播放页: /vodplay/{vid}-{sid}-{nid}.html → player_aaaa JSON (encrypt=1, URL编码)
  - 搜索页: /vodsearch/-------------.html?wd={kw}  (分页: /vodsearch/{kw}----------{page}---.html)
  - 海报: background-image:url(...) 或 data-original 属性
  - 视频卡片: <a class="videoBox" href="/voddetail/{id}.html"> + <span class="title">

【安装】
  {"key":"52gggg","name":"52瓜瓜","type":3,"api":"20260909_52gggg.py","searchable":1,"quickSearch":1,"filterable":1}
"""

import sys
import re
import json
import html
import requests
from urllib.parse import quote, unquote

sys.path.append('..')
try:
    from base.spider import Spider
except Exception:
    class Spider(object):
        def init(self, extend=""):
            pass
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            return requests.get(url, headers=headers, timeout=15, **kw)


HOST = "https://0tsi0tsi.52gggg178.xyz"
HOME_URL = HOST + "/%E5%8B%A4%E5%AD%A6%E8%8B%A6%E7%BB%83/U_wz_m__102.html?https://su21y8s.kaiche197.cc/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": HOST + "/",
}
TIMEOUT = 15

# 子分类列表 (只要子分类, 不要大分类)
SUB_CATS = [
    ("55", "国产精品"),
    ("63", "华语AV"),
    ("58", "黑料吃瓜"),
    ("60", "学生合集"),
    ("57", "乱伦精品"),
    ("65", "探花约炮"),
    ("64", "日本无码"),
    ("61", "主播网红"),
    ("56", "欧美精品"),
    ("62", "动漫禁漫"),
    ("80", "日本有码"),
    ("81", "日本素人"),
    ("12", "强奸乱伦"),
    ("20", "女优明星"),
    ("21", "欧美激情"),
    ("22", "重口激情"),
    ("23", "三级伦理"),
    ("24", "剧情动漫"),
    ("25", "SM调教"),
    ("26", "女同性恋"),
    ("69", "国产自拍"),
    ("70", "日韩无码"),
    ("71", "网曝吃瓜"),
    ("72", "探花约炮"),
    ("73", "偷拍偷窥"),
    ("74", "日韩主播"),
    ("75", "中文字幕"),
    ("76", "主播诱惑"),
    ("77", "传媒剧情"),
    ("78", "抖阴短片"),
    ("83", "AV解说"),
    ("84", "换脸明星"),
    ("85", "VR视角"),
]


class Spider(Spider):

    def init(self, extend=""):
        self.host = HOST
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.verify = False

    def getName(self):
        return "52瓜瓜"

    def isVideoFormat(self, url):
        return any(url.endswith(x) for x in [".m3u8", ".mp4", ".flv"])

    def manualVideoCheck(self):
        return False

    def _get(self, url):
        try:
            r = self.session.get(url, timeout=TIMEOUT)
            return r.content.decode('utf-8', errors='replace')
        except Exception:
            return ""

    def _extract_videos(self, text):
        """从HTML中提取视频列表 (id + 标题 + 海报)
        站点A卡片结构:
          <a class="videoBox" href="/voddetail/{id}.html">
            <div class="videoBox-cover" style="background-image: url(图片URL);">
            <span class="title">标题</span>
        """
        videos = []

        # 提取 videoBox 链接
        links = re.findall(r'href="/voddetail/(\d+)\.html"[^>]*class="videoBox"', text)

        # 提取 cover 图片 (background-image:url)
        covers = re.findall(r'background-image:\s*url\(([^)]+)\)', text)

        # 提取标题
        titles = re.findall(r'<span class="title">([^<]+)</span>', text)

        for i, vid in enumerate(links):
            title = html.unescape(titles[i]).strip() if i < len(titles) else ""
            pic = covers[i] if i < len(covers) else ""
            # 补全图片URL (有些cover没有协议头)
            if pic and not pic.startswith("http"):
                pic = self.host + pic if pic.startswith("/") else "https://" + pic
            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": "",
            })

        return videos

    # ======================== 首页 ========================

    def homeContent(self, filter):
        result = {}
        classes = []
        for tid, name in SUB_CATS:
            classes.append({"type_id": tid, "type_name": name})
        result["class"] = classes

        # 首页视频列表
        text = self._get(HOME_URL)
        result["list"] = self._extract_videos(text)
        return result

    def homeVideoContent(self):
        text = self._get(HOME_URL)
        return {"list": self._extract_videos(text)}

    # ======================== 分类 ========================

    def categoryContent(self, tid, pg=1, filter=0, extend=None):
        page = int(pg) if str(pg).isdigit() else 1
        url = "%s/vodtype/%s-%d.html" % (self.host, tid, page)
        text = self._get(url)
        videos = self._extract_videos(text)

        # 提取总页数 (格式: 共37073条数据,当前1/1545页 或 尾页链接)
        pagecount = 1
        m = re.search(r'/(\d+)/\d+页', text)
        if m:
            pagecount = int(m.group(1))
        else:
            m = re.search(r'vodtype/\d+-(\d+)\.html"[^>]*title="尾页"', text)
            if m:
                pagecount = int(m.group(1))
            elif len(videos) > 0:
                pagecount = 9999

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": len(videos),
        }

    # ======================== 详情 ========================

    def detailContent(self, ids):
        vid = str(ids[0])
        text = self._get(self.host + "/voddetail/%s.html" % vid)
        if not text:
            return {"list": []}

        # 标题: 从 <title> 标签提取 (格式: 标题详情介绍-站点名)
        title = ""
        m = re.search(r'<title>([^<]+)</title>', text)
        if m:
            full_title = html.unescape(m.group(1))
            # 去掉 "详情介绍-" 后面的站点名部分
            if "详情" in full_title:
                title = full_title.split("详情")[0].strip()
            else:
                title = full_title.split("-")[0].strip()

        # 海报: 从 videoBox-cover 或 img 标签提取
        pic = ""
        m = re.search(r'background-image:\s*url\((https?://[^)]+)\)', text)
        if m:
            pic = m.group(1)
        if not pic:
            m = re.search(r'data-original="(https?://[^"]+\.(?:jpg|png|webp))"', text)
            if m:
                pic = m.group(1)
        if not pic:
            all_imgs = re.findall(r'(https?://[^\s"\'<>]+\.(?:jpg|png|webp))', text)
            # 排除模板图片
            for img in all_imgs:
                if 'template' not in img and 'favicon' not in img:
                    pic = img
                    break

        # 播放链接
        plays = re.findall(r'href="/vodplay/(\d+-\d+-\d+)\.html"[^>]*>([^<]+)', text)
        play_url = ""
        seen = set()
        play_names = []
        play_ids = []
        for pid, pname in plays:
            pname = pname.strip()
            if pname and pid not in seen:
                seen.add(pid)
                play_names.append(pname)
                play_ids.append(pid)
        if play_ids:
            # 用#分隔多集, 用$分隔名称和ID
            play_url = "#".join(["播放$" + pid for pid in play_ids])

        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": "",
            "vod_play_from": "52瓜瓜",
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    # ======================== 搜索 ========================

    def searchContent(self, key, quick=0, pg=1):
        """搜索接口"""
        page = int(pg) if pg else 1
        kw = quote(key)
        url = "%s/vodsearch/%s----------%d---.html" % (self.host, kw, page)
        text = self._get(url)
        if not text:
            return {"list": [], "page": page}

        videos = self._extract_videos(text)

        result = {"list": videos, "page": page}
        if page == 1:
            pagecount = 1
            m = re.search(r'/(\d+)/\d+页', text)
            if m:
                pagecount = int(m.group(1))
            elif len(videos) > 0:
                pagecount = 9999
            result["pagecount"] = pagecount

        return result

    def searchContentPage(self, key, quick, page):
        return self.searchContent(key, quick, page)

    # ======================== 播放 ========================

    def playerContent(self, flag, id, vipFlags=0):
        # id 格式: vid-sid-nid
        pid = str(id)
        url = "%s/vodplay/%s.html" % (self.host, pid)
        text = self._get(url)
        if not text:
            return {"parse": 0, "url": "", "header": ""}

        # 提取 player_aaaa JSON
        m = re.search(r'var player_aaaa\s*=\s*(\{[^}]+\})', text)
        if not m:
            return {"parse": 0, "url": "", "header": ""}

        try:
            data = json.loads(m.group(1))
            raw_url = data.get("url", "")
            encrypt = data.get("encrypt", 0)

            if encrypt == 1:
                # URL编码, 需要unquote
                m3u8_url = unquote(raw_url)
            elif encrypt == 0:
                m3u8_url = raw_url
            else:
                m3u8_url = raw_url

            if m3u8_url:
                return {
                    "parse": 0,
                    "url": m3u8_url,
                    "header": json.dumps({
                        "User-Agent": UA,
                        "Referer": self.host + "/",
                    }),
                }
        except Exception:
            pass

        return {"parse": 0, "url": "", "header": ""}


# ======================== 测试 ========================

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings('ignore')
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    s = Spider()
    s.init()

    print("=== 52瓜瓜 Spider 测试 ===\n")

    # 1. 首页
    home = s.homeContent(True)
    classes = home.get("class", [])
    print("首页分类(子分类): %d 个" % len(classes))
    for c in classes[:5]:
        print("  %s: %s" % (c["type_id"], c["type_name"]))
    print("  ...")
    home_list = home.get("list", [])
    print("首页视频: %d 条" % len(home_list))
    if home_list:
        print("  标题: %s" % home_list[0]["vod_name"][:60])
        print("  海报: %s" % home_list[0]["vod_pic"][:80])

    # 2. 分类
    print()
    cat = s.categoryContent("55", "1", 0, {})
    cat_list = cat.get("list", [])
    print("分类(国产精品) 第1页: %d 条" % len(cat_list))
    print("  pagecount: %s" % cat.get("pagecount"))
    if cat_list:
        print("  标题: %s" % cat_list[0]["vod_name"][:60])
        print("  海报: %s" % cat_list[0]["vod_pic"][:80])

    cat2 = s.categoryContent("55", "2", 0, {})
    print("分类(国产精品) 第2页: %d 条" % len(cat2.get("list", [])))

    # 3. 详情
    if home_list:
        vid = home_list[0]["vod_id"]
    elif cat_list:
        vid = cat_list[0]["vod_id"]
    else:
        vid = "304078"
    detail = s.detailContent([vid])
    detail_data = detail.get("list", [{}])[0] if isinstance(detail, dict) else {}
    print()
    print("视频详情 (id=%s):" % vid)
    print("  标题: %s" % detail_data.get("vod_name", "")[:60])
    print("  海报: %s" % detail_data.get("vod_pic", "")[:80])
    print("  播放: %s" % detail_data.get("vod_play_url", "")[:80])

    # 4. 搜索
    search = s.searchContent("麻豆", False)
    print()
    print("搜索'麻豆' 第1页: %d 条" % len(search.get("list", []) if isinstance(search, dict) else search))
    search_list = search.get("list", []) if isinstance(search, dict) else search
    if search_list:
        print("  标题: %s" % search_list[0]["vod_name"][:60])
        print("  海报: %s" % search_list[0]["vod_pic"][:80])

    # 5. 播放
    play_url = detail_data.get("vod_play_url", "")
    pid = ""
    if play_url and "$" in play_url:
        pid = play_url.split("$")[1].split("#")[0]
    if not pid:
        pid = "304078-1-1"
    play = s.playerContent("", pid, "")
    print()
    print("播放 (id=%s):" % pid)
    print("  parse: %s" % play.get("parse"))
    print("  url: %s" % play.get("url", "")[:100])

    # 6. 可访问性验证
    print()
    print("=== 可访问性验证 ===")
    if home_list:
        img_url = home_list[0]["vod_pic"]
        if img_url:
            r = requests.get(img_url, headers={"User-Agent": UA}, verify=False, timeout=10)
            print("海报: %d %s %s bytes" % (r.status_code, r.headers.get("content-type", ""), r.headers.get("content-length", "?")))

    m3u8_url = play.get("url", "")
    if m3u8_url:
        r = requests.get(m3u8_url, headers={"User-Agent": UA}, verify=False, timeout=15)
        print("m3u8: %d, %d bytes" % (r.status_code, len(r.content)))
        lines = r.text.strip().split("\n")
        ts_lines = [l for l in lines if l and not l.startswith("#")]
        if ts_lines:
            print("  TS分片数: %d" % len(ts_lines))
            print("  TS[0]: %s" % ts_lines[0][:60])
            print("  TS[0]绝对URL: %s" % ts_lines[0].startswith("http"))

    print("\n=== 测试完成 ===")
