#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
野马视频 / yemahk.xyz - PyramidStore 插件
目标: 适配 https://www.yemahk.xyz
特性: 自动过验证(Cookie)、双重Base64标题解码、M3U8加速、子分类筛选
"""

import requests
import re
import base64
import json
import sys
import os
import time
from urllib.parse import quote, urljoin, unquote

# 兼容本地调试与 PyramidStore 环境
sys.path.append('../../')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def init(self, extend=""):
            pass


_CACHE_FILE = "野马视频site.txt"


def decode_title(text: str) -> str:
    """解码双重 base64 编码的标题"""
    if not text or not isinstance(text, str):
        return ""
    text = text.strip()
    if not text:
        return ""
    try:
        d1 = base64.b64decode(text).decode('utf-8')
        d2 = base64.b64decode(d1).decode('utf-8')
        return d2
    except Exception:
        try:
            return base64.b64decode(text).decode('utf-8')
        except Exception:
            return text


class Spider(Spider):
    """PyramidStore 标准爬虫插件"""

    def __init__(self):
        self.siteUrl = "https://www.yemahk.xyz"
        self.userAgent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        self.timeout = 15
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.userAgent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self._ensure_verified_cookie()

    def _ensure_verified_cookie(self):
        """设置网站验证 cookie，绕过'确认进入'页面"""
        try:
            from urllib.parse import urlparse
            domain = urlparse(self.siteUrl).hostname
            self.session.cookies.set("verified", "true", domain=domain, path="/")
        except Exception as e:
            print(f"[WARN] 设置 cookie 失败: {e}")

    def _get_headers(self, referer=None):
        """获取带 Referer 的请求头"""
        return {
            "User-Agent": self.userAgent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": referer or self.siteUrl,
        }

    def _fetch_with_fallback(self, url, headers=None, retries=2):
        """
        带备用请求头的请求方法。
        若被验证页拦截，自动切换请求头重试。
        """
        if headers is None:
            headers = self._get_headers()

        for attempt in range(retries):
            try:
                resp = self.session.get(url, headers=headers, timeout=self.timeout)
                resp.raise_for_status()

                # 检查是否被验证页面拦截
                if "确认进入" in resp.text and "verified" in resp.text and attempt < retries - 1:
                    print(f"[WARN] 遇到验证页面，尝试备用请求头 (attempt {attempt + 1})")
                    headers["Accept"] = "*/*"
                    headers["Cache-Control"] = "no-cache"
                    headers["Pragma"] = "no-cache"
                    time.sleep(0.5)
                    continue
                return resp
            except requests.exceptions.RequestException as e:
                if attempt < retries - 1:
                    print(f"[WARN] 请求失败，重试 {attempt + 1}: {url}")
                    time.sleep(1)
                else:
                    print(f"[ERROR] fetch {url} failed: {e}")
                    return None
        return None

    def init(self, extend=""):
        """插件初始化(框架回调)"""
        if extend and isinstance(extend, str):
            if extend.startswith("http"):
                self.siteUrl = extend.rstrip('/')
                self._ensure_verified_cookie()

        # 验证网址可用性
        self._resolve_site_url()

    def _resolve_site_url(self):
        """验证并解析站点网址，支持缓存"""
        cached_url = ""
        try:
            if os.path.exists(_CACHE_FILE):
                with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                    cached_url = f.read().strip()
        except Exception:
            pass

        if cached_url:
            self.siteUrl = cached_url
            self._ensure_verified_cookie()

        try:
            resp = self._fetch_with_fallback(self.siteUrl)
            if resp:
                if "确认进入" in resp.text:
                    print("[WARN] 验证页面未绕过，尝试刷新 cookie")
                    self._ensure_verified_cookie()
                    resp2 = self._fetch_with_fallback(self.siteUrl)
                    if resp2 and "确认进入" not in resp2.text:
                        print(f"[INFO] 网址验证通过: {self.siteUrl}")
                        self._save_cache()
                    else:
                        print(f"[WARN] 无法绕过验证页面，请检查域名")
                else:
                    print(f"[INFO] 网址验证通过: {self.siteUrl}")
                    self._save_cache()
        except Exception as e:
            print(f"[WARN] 网址验证异常: {e}")

    def _save_cache(self):
        try:
            with open(_CACHE_FILE, "w", encoding="utf-8") as f:
                f.write(self.siteUrl)
        except Exception as e:
            print(f"[WARN] 缓存写入失败: {e}")

    def getName(self):
        return "野马视频"

    def fetch(self, url, headers=None):
        """统一请求方法(兼容模板接口)"""
        return self._fetch_with_fallback(url, headers)

    def _extract_videos(self, html: str) -> list:
        """从列表 HTML 中提取视频条目"""
        videos = []
        seen_ids = set()

        # 模式1: 提取带缩略图的 <a> 块
        # <a href="/video.php?classid=39&id=xxx"><img data-lazy-src="/img/..." alt="BASE64"></a>
        img_pattern = (
            r'<a[^>]*href=["\']([^"\'>]*video\.php\?classid=(\d+)&id=(\d+))["\'][^>]*>'
            r'.*?'
            r'<img[^>]*(?:data-lazy-src|src)=["\']([^"\'>]+)["\'][^>]*'
            r'(?:alt=["\']([^"\'>]*)["\'])?'
            r'[^>]*>'
            r'.*?</a>'
        )
        img_items = re.findall(img_pattern, html, re.DOTALL | re.IGNORECASE)

        for item in img_items:
            href, classid, vid, img, alt = item
            vid_str = f"{classid}-{vid}"
            if vid_str in seen_ids:
                continue
            seen_ids.add(vid_str)

            img_url = img if img.startswith('http') else urljoin(self.siteUrl, img)
            title = decode_title(alt.strip()) if alt else ""

            videos.append({
                "vod_id": vid_str,
                "vod_name": title,
                "vod_pic": img_url,
                "vod_remarks": "",
            })

        # 模式2: 补充纯文本链接的标题（用于无 alt 或 alt 为空的情况）
        text_pattern = r'<a[^>]*href=["\']([^"\'>]*video\.php\?classid=(\d+)&id=(\d+))["\'][^>]*>([^<]+)</a>'
        text_items = re.findall(text_pattern, html, re.IGNORECASE)

        for item in text_items:
            href, classid, vid, text = item
            vid_str = f"{classid}-{vid}"
            text = text.strip()
            if not text:
                continue

            found = False
            for v in videos:
                if v["vod_id"] == vid_str:
                    found = True
                    if not v["vod_name"]:
                        v["vod_name"] = decode_title(text)
                    break

            if not found:
                videos.append({
                    "vod_id": vid_str,
                    "vod_name": decode_title(text),
                    "vod_pic": "",
                    "vod_remarks": "",
                })

        return videos

    def _extract_pagecount(self, html: str) -> int:
        """从分页链接中提取总页数"""
        page_matches = re.findall(r'[?&]page=(\d+)', html)
        if page_matches:
            return max(int(p) for p in page_matches)
        text_match = re.search(r'共\s*(\d+)\s*页', html)
        if text_match:
            return int(text_match.group(1))
        return 1

    def _get_m3u8_from_detail(self, html: str) -> str:
        """从详情页提取 m3u8 地址"""
        m3u8_matches = re.findall(r'(https?://[^\s"\'>]+?\.m3u8[^\s"\'>]*)', html)
        if m3u8_matches:
            return m3u8_matches[0]
        return ""

    def _get_accelerated_url(self, m3u8_url: str) -> str:
        """通过加速接口获取带签名的播放地址"""
        if not m3u8_url:
            return ""
        try:
            api_url = f"{self.siteUrl}/jiasu_m3u8.php?m3u8={quote(m3u8_url)}&cdn=auto&t={int(time.time() * 1000)}"
            resp = self.fetch(api_url)
            if resp:
                data = resp.json()
                play_url = data.get("play_url", m3u8_url)
                # 修复加速接口可能返回的畸形 URL
                play_url = play_url.replace("https://auto/https/", "https://")
                play_url = play_url.replace("https://auto/http/", "http://")
                return play_url
        except Exception as e:
            print(f"[ERROR] 加速接口失败: {e}")
        return m3u8_url

    # ==================== TVBox 标准接口 ====================

    def homeContent(self, filter):
        result = {"class": [], "filters": {}}

        classes = [
            {"type_id": "39", "type_name": "番号视频"},
            {"type_id": "40", "type_name": "国产视频"},
            {"type_id": "41", "type_name": "有码番号"},
        ]

        filters_map = {
            "39": [
                {
                    "key": "fenlei",
                    "name": "子分类",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "中文字幕", "v": "中文字幕"},
                        {"n": "巨乳美乳", "v": "巨乳美乳"},
                        {"n": "强姦乱伦", "v": "强姦乱伦"},
                        {"n": "制服丝袜", "v": "制服丝袜"},
                        {"n": "萝莉少女", "v": "萝莉少女"},
                        {"n": "精品素人", "v": "精品素人"},
                        {"n": "亚洲有码", "v": "亚洲有码"},
                        {"n": "亚洲无码", "v": "亚洲无码"},
                        {"n": "女同性恋", "v": "女同性恋"},
                    ]
                }
            ],
            "40": [
                {
                    "key": "fenlei",
                    "name": "子分类",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "国产自拍", "v": "国产自拍"},
                        {"n": "国产传媒", "v": "国产传媒"},
                        {"n": "AV解说", "v": "AV解说"},
                        {"n": "国产乱伦", "v": "国产乱伦"},
                        {"n": "网红主播", "v": "网红主播"},
                        {"n": "探花约炮", "v": "探花约炮"},
                        {"n": "ai换脸", "v": "ai换脸"},
                        {"n": "伦理三级", "v": "伦理三级"},
                        {"n": "欧美精品", "v": "欧美精品"},
                        {"n": "成人动漫", "v": "成人动漫"},
                    ]
                }
            ],
            "41": []
        }

        result['class'] = classes
        if filter:
            result['filters'] = filters_map
        return result

    def homeVideoContent(self):
        result = {"list": []}
        resp = self.fetch(self.siteUrl)
        if not resp:
            return result

        videos = self._extract_videos(resp.text)
        result["list"] = videos[:12]
        return result

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 0, "limit": 20, "total": 0}

        url = f"{self.siteUrl}/list.php?classid={tid}&page={pg}"
        if extend and isinstance(extend, dict):
            fenlei = extend.get("fenlei", "")
            if fenlei:
                url += f"&fenlei={quote(fenlei)}"

        resp = self.fetch(url)
        if not resp:
            return result

        html = resp.text
        videos = self._extract_videos(html)
        pagecount = self._extract_pagecount(html)

        result.update({
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20,
        })
        return result

    def detailContent(self, ids):
        result = {"list": []}
        if not ids:
            return result

        video_id = ids[0] if isinstance(ids, list) else ids
        if '-' in video_id:
            classid, vid = video_id.split('-', 1)
        else:
            classid, vid = "39", video_id

        url = f"{self.siteUrl}/video.php?classid={classid}&id={vid}"
        resp = self.fetch(url)
        if not resp:
            return result

        html = resp.text

        # 提取标题: <title>BASE64标题 - BASE64站点名</title>
        title = ""
        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        if title_match:
            title_text = title_match.group(1)
            parts = title_text.split(' - ')
            if parts:
                title = decode_title(parts[0])

        # 提取图片（取第一个视频截图）
        pic = ""
        img_matches = re.findall(r'<img[^>]*src=["\']([^"\'>]+)["\'][^>]*>', html)
        for img in img_matches:
            if '/img/' in img and not any(x in img for x in ['skin', 'sucai', 'gifjiazai', 'yema']):
                pic = img if img.startswith('http') else urljoin(self.siteUrl, img)
                break

        # 提取 m3u8 并走加速接口获取签名 URL
        m3u8 = self._get_m3u8_from_detail(html)
        play_url = self._get_accelerated_url(m3u8) if m3u8 else ""

        # 提取描述
        desc = ""
        desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\'>]+)["\']', html, re.IGNORECASE)
        if desc_match:
            desc = desc_match.group(1)

        # 提取日期作为备注
        remarks = ""
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', html)
        if date_match:
            remarks = date_match.group(1)

        vod = {
            "vod_id": video_id,
            "vod_name": title or f"视频{vid}",
            "vod_pic": pic,
            "vod_remarks": remarks,
            "vod_year": "",
            "vod_area": "",
            "vod_actor": "",
            "vod_director": "",
            "vod_content": desc,
            "vod_play_from": "默认",
            "vod_play_url": f"播放${play_url}" if play_url else "",
        }

        result["list"] = [vod]
        return result

    def searchContent(self, key, quick, pg=1):
        result = {"list": []}
        url = f"{self.siteUrl}/fontsearch.php?query={quote(key)}&classid=39&orderby=newstime"
        if pg > 1:
            url += f"&page={pg}"

        resp = self.fetch(url)
        if not resp:
            return result

        videos = self._extract_videos(resp.text)
        result["list"] = videos
        return result

    def searchContentPage(self, key, quick, pg=1):
        return self.searchContent(key, quick, pg)

    def playerContent(self, flag, id, vipFlags):
        result = {}
        if not id:
            return result

        headers = {
            "User-Agent": self.userAgent,
            "Referer": self.siteUrl,
        }

        if self.isVideoFormat(id):
            result["parse"] = 0
            result["url"] = id
            result["header"] = headers
        else:
            play_url = id if id.startswith("http") else urljoin(self.siteUrl, id)
            result["parse"] = 0
            result["url"] = play_url
            result["header"] = headers
        return result

    def isVideoFormat(self, url):
        if not url or not isinstance(url, str):
            return False
        if not url.startswith("http"):
            return False
        fmt = ['.mp4', '.m3u8', '.ts', '.mkv', '.avi', '.webm', '.flv']
        for f in fmt:
            if url.lower().find(f) > -1:
                return True
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        """本地代理(处理封面/m3u8等)"""
        action = param.get('action')
        if action == 'proxy':
            url = param.get('url')
            if not url:
                return None
            headers = {
                "User-Agent": self.userAgent,
                "Referer": self.siteUrl,
            }
            try:
                if param.get('type') == 'cover':
                    r = requests.get(url, headers=headers, timeout=10)
                    if r.status_code == 200 and r.content:
                        return [200, r.headers.get('Content-Type', 'image/jpeg'), r.content]
                    return [404, "text/plain", "cover not found"]
                elif param.get('type') == 'm3u8':
                    content = requests.get(url, headers=headers, timeout=10).text
                    return [200, "application/vnd.apple.mpegurl", content]
                elif param.get('type') == 'media':
                    r = requests.get(url, headers=headers, stream=True, timeout=10)
                    return [206, "application/octet-stream", r.content]
                else:
                    content = requests.get(url, headers=headers, timeout=10).text
                    return [200, "text/plain", content]
            except Exception as e:
                print(f"[ERROR] localProxy failed: {e}")
                return [500, "text/plain", str(e)]
        return None


# ==================== 本地模拟 TVBox 测试入口 ====================

def test():
    """模拟 TVBox 环境联网测试所有接口"""
    print("=" * 70)
    print("野马视频 TVBox 爬虫 - 联网测试")
    print("=" * 70)

    spider = Spider()
    spider.init()

    # 1. 首页分类
    print("\n--- [1/7] homeContent ---")
    home = spider.homeContent(filter=True)
    print(f"分类数: {len(home.get('class', []))}")
    for c in home.get('class', []):
        print(f"  {c['type_id']}: {c['type_name']}")
    print(f"筛选器键: {list(home.get('filters', {}).keys())}")

    # 2. 首页视频
    print("\n--- [2/7] homeVideoContent ---")
    home_videos = spider.homeVideoContent()
    hv_list = home_videos.get('list', [])
    print(f"首页视频数量: {len(hv_list)}")
    for v in hv_list[:3]:
        name = v['vod_name'][:40] + "..." if len(v['vod_name']) > 40 else v['vod_name']
        print(f"  [{v['vod_id']}] {name}")
        print(f"      图片: {v['vod_pic'][:60]}...")

    # 3. 分类列表 (第1页)
    print("\n--- [3/7] categoryContent (tid=39, pg=1) ---")
    cat = spider.categoryContent(tid="39", pg=1, filter=True, extend={})
    cat_list = cat.get('list', [])
    print(f"视频数量: {len(cat_list)}, 当前页: {cat.get('page')}, 总页数: {cat.get('pagecount')}")
    for v in cat_list[:3]:
        name = v['vod_name'][:40] + "..." if len(v['vod_name']) > 40 else v['vod_name']
        print(f"  [{v['vod_id']}] {name}")

    # 4. 子分类筛选
    print("\n--- [4/7] categoryContent + fenlei=中文字幕 ---")
    cat2 = spider.categoryContent(tid="39", pg=1, filter=True, extend={"fenlei": "中文字幕"})
    cat2_list = cat2.get('list', [])
    print(f"子分类视频数量: {len(cat2_list)}")
    for v in cat2_list[:2]:
        name = v['vod_name'][:40] + "..." if len(v['vod_name']) > 40 else v['vod_name']
        print(f"  [{v['vod_id']}] {name}")

    # 5. 详情页
    print("\n--- [5/7] detailContent ---")
    if cat_list:
        test_id = cat_list[0]['vod_id']
        print(f"测试视频ID: {test_id}")
        detail = spider.detailContent([test_id])
        d_list = detail.get('list', [])
        if d_list:
            d = d_list[0]
            print(f"  标题: {d['vod_name']}")
            print(f"  图片: {d['vod_pic'][:60]}...")
            print(f"  备注: {d['vod_remarks']}")
            print(f"  播放地址: {d['vod_play_url'][:80]}...")

            # 6. 播放器
            print("\n--- [6/7] playerContent ---")
            play_url = d.get('vod_play_url', '').split('$')[-1]
            if play_url:
                player = spider.playerContent("默认", play_url, "")
                print(f"  parse: {player.get('parse')}")
                print(f"  url: {player.get('url')[:80]}...")
                print(f"  header Referer: {player.get('header', {}).get('Referer', '')}")
            else:
                print("  [SKIP] 无播放地址")
        else:
            print("  [ERROR] 详情页无数据")
    else:
        print("  [SKIP] 分类无数据，跳过详情测试")

    # 7. 搜索
    print("\n--- [7/7] searchContent ---")
    search = spider.searchContent("护士", quick=False, pg=1)
    s_list = search.get('list', [])
    print(f"搜索结果数量: {len(s_list)}")
    for v in s_list[:3]:
        name = v['vod_name'][:40] + "..." if len(v['vod_name']) > 40 else v['vod_name']
        print(f"  [{v['vod_id']}] {name}")

    print("\n" + "=" * 70)
    print("全部测试完成，若以上各项均有数据输出，则插件可正常使用")
    print("=" * 70)


if __name__ == '__main__':
    test()
