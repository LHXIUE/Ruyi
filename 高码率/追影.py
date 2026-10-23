# -*- coding: utf-8 -*-
# 遮天法 v3.1+ · 追影网 (zhuiying1.cc) 独立爬虫源v0
# 严格遵循绝对铁律 · 洞天境
# 完全自包含，无需任何外部依赖
# TVBox 标准入口：get_spider()

import sys
sys.path.append('..') 
from base.spider import Spider
import re
from urllib.parse import quote

# ==================== 道基 (源站根基) ====================
BASE_URL = "https://zhuiying1.cc"

class Spider(Spider):
    # ==================== 第一秘：铭刻道印 ====================
    def init(self, extend=""):
        self.name = "追影_遮天法"
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": BASE_URL + "/"
        }

    # ==================== 修复：补充 getName 方法 ====================
    def getName(self):
        return "追影_遮天法"

    # ==================== 修复：补充 isVideoFormat 方法 ====================
    def isVideoFormat(self, url):
        video_exts = ['.m3u8', '.mp4', '.flv', '.mkv', '.avi', '.ts', '.mpg']
        return any(ext in url.lower() for ext in video_exts)

    # ==================== 洗髓伐脉 (清理 Script 和 Style) ====================
    def _clean_html(self, html):
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<[^>]+>', '', html)
        return html.strip()

    # ==================== 第二秘：斗字秘 (幻化分类) ====================
    def homeContent(self, filter):
        result = {}
        cate = {
            "电影": "dianying",
            "电视剧": "dianshiju",
            "综艺": "zongyi",
            "动漫": "dongman",
            "短剧": "duanju"
        }
        classes = []
        for k, v in cate.items():
            classes.append({'type_name': k, 'type_id': v})
        result['class'] = classes
        if filter:
            result['filters'] = self.config['filter']
        return result

    # ==================== 第三秘：皆字秘 (多重解析大阵) ====================
    def _decode_secret(self, html):
        videos = []
        thumb_blocks = re.findall(r'class="hero-thumb[^"]*"([^>]*)>', html, re.DOTALL)
        for block in thumb_blocks:
            title = re.search(r'data-title="([^"]*)"', block)
            detail = re.search(r'data-detail="/video/([^"]*)\.html"', block)
            bg = re.search(r'data-bg="([^"]*)"', block)
            if title and detail and bg:
                videos.append({
                    "vod_id": detail.group(1),
                    "vod_name": title.group(1),
                    "vod_pic": bg.group(1),
                    "vod_remarks": ""
                })
        if videos: return videos

        hot_pattern = r'<a[^>]*class="hotsearch_hot_item"[^>]*href="/video/([^"]*)\.html"[^>]*title="([^"]*)"[^>]*>.*?<img[^>]*src="([^"]*)"'
        hot_items = re.findall(hot_pattern, html, re.DOTALL)
        for vid, title, pic in hot_items:
            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": "热门"
            })
        if videos: return videos

        card_pattern = r'<a[^>]*href="/video/([a-zA-Z0-9]+)\.html"[^>]*title="([^"]*)"[^>]*>.*?<img[^>]*src="([^"]*)"'
        cards = re.findall(card_pattern, html, re.DOTALL)
        for vid, title, pic in cards:
            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": ""
            })
        return videos

    # ==================== 第四秘：行字秘 ====================
    def homeVideoContent(self):
        try:
            url = BASE_URL + '/vodtype/dianshiju.html'
            rsp = self.fetch(url, headers=self.header)
            vlist = self._decode_secret(rsp.text)
            return {'list': vlist}
        except:
            return {'list': []}

    # ==================== 第五秘：破界秘 ====================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            url = BASE_URL + '/vodtype/' + tid
            if pg != '1':
                url += '-pg-' + pg
            url += '.html'
            rsp = self.fetch(url, headers=self.header)
            vlist = self._decode_secret(rsp.text)
            return {
                'list': vlist,
                'page': pg,
                'pagecount': 9999,
                'limit': 30,
                'total': 999999
            }
        except:
            return {'list': []}

    # ==================== 第六秘：兵字秘 (详情灵根) ====================
    def detailContent(self, array):
        try:
            tid = array[0]
            url = BASE_URL + '/video/' + tid + '.html'
            rsp = self.fetch(url, headers=self.header)
            html = rsp.text

            title = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            title = title.group(1).strip() if title else re.search(r'<title>([^<]+)</title>', html).group(1).split('-')[0]

            pic = re.search(r'<img[^>]*class="[^"]*(?:pic|poster|thumb)[^"]*"[^>]*src="([^"]*)"', html)
            pic = pic.group(1) if pic else ""

            desc = ""
            m = re.search(r'<div[^>]*class="[^"]*(?:desc|content)[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            if m:
                desc = self._clean_html(m.group(1))
            
            if not desc:
                m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html, re.IGNORECASE)
                if m:
                    desc = m.group(1).strip()

            play_from, play_url = [], []
            list_blocks = re.findall(r'<div[^>]*class="[^"]*(?:play-list|playlist)[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            for block in list_blocks:
                links = re.findall(r'<a[^>]*href="(/play/([a-zA-Z0-9]+)-(\d+)-(\d+)\.html)"[^>]*>([^<]+)</a>', block)
                if links:
                    eps = [ep_name + '$' + href for href, vid, src_idx, ep_idx, ep_name in links]
                    play_from.append("线路" + src_idx)
                    play_url.append('#'.join(eps))

            if not play_from:
                all_plays = re.findall(r'<a[^>]*href="(/play/([a-zA-Z0-9]+)-(\d+)-(\d+)\.html)"[^>]*>([^<]+)</a>', html)
                if all_plays:
                    sources = {}
                    for href, vid, src_idx, ep_idx, ep_name in all_plays:
                        src_name = "线路" + src_idx
                        if src_name not in sources: sources[src_name] = []
                        sources[src_name].append(ep_name + '$' + href)
                    for src_name, eps in sources.items():
                        play_from.append(src_name)
                        play_url.append('#'.join(eps))

            vod = {
                "vod_id": tid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_content": desc,
                "vod_play_from": '$$$'.join(play_from) if play_from else "默认",
                "vod_play_url": '$$$'.join(play_url) if play_url else ""
            }
            return {'list': [vod]}
        except Exception as e:
            print("兵字秘解析出错:", e)
            return {'list': []}

    # ==================== 第七秘：探查秘 (修好 TVBox 参数兼容) ====================
    def searchContent(self, key, quick, pg="1"):
        try:
            url = BASE_URL + '/vod/search/wd/' + quote(key)
            rsp = self.fetch(url, headers=self.header)
            html = rsp.text
            videos = []

            # 方式一：专门针对"搜索页"的结构进行提取
            search_items = re.findall(r'<div[^>]*class="[^"]*(?:search-item|vod-item|search-list)[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            
            for item in search_items:
                vid = re.search(r'href="/video/([a-zA-Z0-9]+)\.html"', item)
                title = re.search(r'title="([^"]*)"', item)
                pic = re.search(r'src="([^"]*)"', item)
                if vid and title and pic:
                    videos.append({
                        "vod_id": vid.group(1),
                        "vod_name": title.group(1),
                        "vod_pic": pic.group(1),
                        "vod_remarks": ""
                    })

            # 方式二：兜底
            if not videos:
                cards = re.findall(r'<a[^>]*href="/video/([a-zA-Z0-9]+)\.html"[^>]*title="([^"]*)"[^>]*>.*?<img[^>]*src="([^"]*)"', html, re.DOTALL)
                for vid, title, pic in cards:
                    videos.append({
                        "vod_id": vid,
                        "vod_name": title,
                        "vod_pic": pic,
                        "vod_remarks": ""
                    })

            return {'list': videos}
        except Exception as e:
            print("探查秘出错:", e)
            return {'list': []}

    # ==================== 第八秘：破阵秘 ====================
    def playerContent(self, flag, id, vipFlags):
        try:
            url = id if id.startswith('http') else BASE_URL + id
            if '.m3u8' in url or '.mp4' in url:
                return {"parse": 0, "url": url}

            rsp = self.fetch(url, headers=self.header)
            html = rsp.text

            iframe = re.search(r'<iframe[^>]*src="([^"]*)"', html)
            if iframe:
                real = iframe.group(1)
                if real.startswith('//'): real = 'https:' + real
                return {"parse": 0 if any(x in real for x in ['.m3u8','.mp4','.flv']) else 1, "url": real}

            vid_src = re.search(r'<video[^>]*src="([^"]*)"', html) or \
                      re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', html) or \
                      re.search(r'["\'](https?://[^"\']+\.mp4[^"\']*)["\']', html)
            
            if vid_src:
                return {"parse": 0, "url": vid_src.group(1)}
            
            return {"parse": 1, "url": url}
        except:
            return {"parse": 1, "url": id}

    # ==================== 铭文阵法 ====================
    config = {
        "player": {},
        "filter": {
            "dianying": [{"key":"year","name":"年份","value":[{"n":"全部","v":""},{"n":"2026","v":"2026"},{"n":"2025","v":"2025"}]}],
            "dianshiju": [{"key":"year","name":"年份","value":[{"n":"全部","v":""},{"n":"2026","v":"2026"},{"n":"2025","v":"2025"}]}],
            "zongyi": [{"key":"year","name":"年份","value":[{"n":"全部","v":""},{"n":"2026","v":"2026"},{"n":"2025","v":"2025"}]}],
            "dongman": [{"key":"year","name":"年份","value":[{"n":"全部","v":""},{"n":"2026","v":"2026"},{"n":"2025","v":"2025"}]}],
            "duanju": [{"key":"year","name":"年份","value":[{"n":"全部","v":""},{"n":"2026","v":"2026"},{"n":"2025","v":"2025"}]}]
        }
    }