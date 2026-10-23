# -*- coding: utf-8 -*-
"""@猪猪
OnlyTarts (onlytarts.com) Python Spider
兼容 FongMi/TV (T3) 与 WebHomeTV / PeekPro (T4)


1.  JSON 提取引擎（支持嵌套大括号、JSON.parse、多种变量名）
2. 跟随 302 重定向获取真实 MP4 地址
3. 增强 playerContent 返回格式兼容性
4. 添加 4 层视频 URL 提取兜底
5. 完善请求头（Referer/Origin/Accept）
"""
import sys
import re
import json
import time
import html as html_module

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as rq
    class Spider:
        _session = rq.Session()
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = self._session.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


class Spider(Spider):
    HOST = 'https://onlytarts.com'

    def getName(self):
        return "OnlyTarts"

    def init(self, extend=''):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.host = self.HOST
        self.header = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': self.host + '/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
        }
        self._play_cache = {}

    def _fetch_html(self, url, timeout=15):
        """获取页面 HTML"""
        try:
            rsp = self.fetch(url, headers=self.header, timeout=timeout)
            try:
                rsp.encoding = 'utf-8'
            except Exception:
                pass
            text = rsp.text or ''
            if len(text) < 100:
                print(f"[OnlyTarts] Warning: short response {len(text)} bytes from {url}")
            return text
        except Exception as e:
            print(f"[OnlyTarts] fetch error: {url} -> {e}")
            return ''

    # ==================== JSON 提取引擎 ====================

    def _extract_json_object(self, html, marker):
        """
        从 HTML 中提取 marker 后的完整 JSON 对象。
        支持：window.xxx = {...}  和  window.xxx = JSON.parse('...')
        """
        idx = html.find(marker)
        if idx == -1:
            return None
        pos = idx + len(marker)

        # 跳过空白
        while pos < len(html) and html[pos] in ' \t\n\r=':
            pos += 1

        # 情况 A: 直接跟 JSON 对象
        if pos < len(html) and html[pos] == '{':
            return self._parse_braced_json(html, pos)

        # 情况 B: JSON.parse('...') 或 JSON.parse("...")
        if html[pos:pos+10] == 'JSON.parse':
            # 找到左括号
            while pos < len(html) and html[pos] != '(':
                pos += 1
            pos += 1
            # 跳过空白
            while pos < len(html) and html[pos] in ' \t\n\r':
                pos += 1
            if pos >= len(html):
                return None
            quote = html[pos]
            if quote not in '"\'':
                return None
            pos += 1
            # 提取字符串内容（处理转义）
            chunks = []
            escape = False
            while pos < len(html):
                ch = html[pos]
                if escape:
                    chunks.append(ch)
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == quote:
                    break
                else:
                    chunks.append(ch)
                pos += 1
            json_str = ''.join(chunks)
            # 处理 \/ 转义
            json_str = json_str.replace('\\/', '/')
            try:
                return json.loads(json_str)
            except Exception as e:
                print(f"[OnlyTarts] JSON.parse parse error: {e}")
                return None

        return None

    def _parse_braced_json(self, html, start):
        """大括号匹配算法提取完整 JSON"""
        brace = 0
        in_str = False
        esc = False
        buf = []
        for i in range(start, len(html)):
            ch = html[i]
            if esc:
                buf.append(ch)
                esc = False
                continue
            if ch == '\\':
                buf.append(ch)
                esc = True
                continue
            if ch == '"':
                buf.append(ch)
                in_str = not in_str
                continue
            if in_str:
                buf.append(ch)
                continue
            if ch == '{':
                brace += 1
                buf.append(ch)
            elif ch == '}':
                brace -= 1
                buf.append(ch)
                if brace == 0:
                    json_str = ''.join(buf)
                    json_str = json_str.replace('\\/', '/')
                    try:
                        return json.loads(json_str)
                    except Exception as e:
                        print(f"[OnlyTarts] braced JSON parse error: {e}")
                        return None
            else:
                buf.append(ch)
        return None

    def _extract_initials(self, html):
        """从页面提取 window.initials / __INITIAL_STATE__ 等"""
        markers = [
            'window.initials',
            'window.__INITIAL_STATE__',
            'window.__DATA__',
            'window.__APP__',
            'window.__INITIALS__',
        ]
        for mk in markers:
            # 尝试 = 后各种空白
            for sep in [' = ', '=', ' =', '= ']:
                data = self._extract_json_object(html, mk + sep)
                if data is not None:
                    print(f"[OnlyTarts] Found data via {mk}{sep}")
                    return data
        return None

    # ==================== 视频列表解析 ====================

    def _parse_videos(self, html):
        """从 HTML 中解析视频列表"""
        videos = []
        card_pattern = r'<div class="video-card__item(?:-big)?[^"]*"[^>]*>(.*?)(?=<div class="video-card__item|<div class="pagination|$)'
        cards = re.findall(card_pattern, html, re.DOTALL)

        for card in cards:
            href_m = re.search(r'href="(https://onlytarts\.com/video/[^"]+)"', card)
            if not href_m:
                continue
            href = href_m.group(1)
            if href.endswith('/video') or href.endswith('/video/best'):
                continue
            slug = href.rsplit('/', 1)[-1] if '/' in href else href

            img_m = re.search(r'src="(https://static\.onlytarts\.com/poster/[^"]+)"', card)
            pic = img_m.group(1) if img_m else ''
            if pic:
                pic = re.sub(r'/poster/(\d+)/\d+/', r'/poster/\1/600/', pic)

            alt_m = re.search(r'alt="([^"]+)"', card)
            title = alt_m.group(1) if alt_m else slug

            dur_m = re.search(r'(\d{1,2}:\d{2})', card)
            duration = dur_m.group(1) if dur_m else ''

            videos.append({
                'vod_id': slug,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': duration,
            })

        return videos

    def _get_pagecount(self, html):
        pages = re.findall(r'page=(\d+)', html)
        if pages:
            return max(int(p) for p in pages)
        return 1

    # ==================== 标准接口 ====================

    def homeContent(self, filter):
        classes = [
            {'type_id': 'video', 'type_name': 'Newest'},
            {'type_id': 'video/best', 'type_name': 'Best'},
        ]
        html = self._fetch_html(self.host + '/tag')
        tags = re.findall(r'href="https://onlytarts\.com/tag/([^"]+)"[^>]*>([^<]+)<', html)
        for tag_slug, tag_name in tags:
            tag_name = tag_name.strip()
            if tag_name and tag_slug:
                classes.append({'type_id': 'tag/' + tag_slug, 'type_name': tag_name})
        return {'class': classes}

    def homeVideoContent(self):
        result = {'list': []}
        try:
            html = self._fetch_html(self.host + '/video')
            result['list'] = self._parse_videos(html)
        except Exception:
            pass
        return result

    def categoryContent(self, tid, pg, filter, ext):
        page = int(pg) if pg else 1
        if page < 1:
            page = 1
        url = f'{self.host}/{tid}?page={page}'
        html = self._fetch_html(url)
        videos = self._parse_videos(html)
        page_count = self._get_pagecount(html)
        return {
            'list': videos,
            'page': page,
            'pagecount': page_count,
            'limit': len(videos),
            'total': page_count * 12,
        }

    def detailContent(self, ids):
        slug = str(ids[0]) if ids else ''
        if not slug:
            return {}

        url = f'{self.host}/video/{slug}'
        html = self._fetch_html(url)
        if not html:
            print(f"[OnlyTarts] detailContent: empty HTML for {slug}")
            return {}

        # 标题
        title_m = re.search(r'<title>([^<]+)</title>', html)
        title = title_m.group(1).split(' - ')[0] if title_m else slug
        title = re.sub(r'\s*Porn:.*', '', title, flags=re.I).strip()

        # 封面
        poster_m = re.search(r'"poster":"([^"]+)"', html)
        if not poster_m:
            poster_m = re.search(r'poster="(https://static\.onlytarts\.com/poster/[^"]+)"', html)
        pic = poster_m.group(1).replace('\\/', '/') if poster_m else ''
        if pic:
            pic = re.sub(r'/poster/(\d+)/\d+/', r'/poster/\1/1200/', pic)

        # 时长
        dur_m = re.search(r'"duration":"?(\d+)"?', html)
        duration = ''
        if dur_m:
            secs = int(dur_m.group(1))
            duration = f'{secs // 60}:{secs % 60:02d}'

        # 标签
        tags = re.findall(r'href="https://onlytarts\.com/tag/[^"]+"[^>]*>([^<]+)<', html)
        tag_str = ', '.join(set(t.strip() for t in tags if t.strip()))[:200]

        # 提取播放链接（同时预热缓存）
        mp4_url = self._extract_play_url(html, slug)
        if mp4_url:
            print(f"[OnlyTarts] detailContent preloaded: {mp4_url[:80]}...")
        else:
            print(f"[OnlyTarts] detailContent: failed to preload MP4 for {slug}")

        vod = {
            'vod_id': slug,
            'vod_name': title,
            'vod_pic': pic,
            'vod_remarks': duration,
            'vod_tags': tag_str,
            'vod_play_from': 'OnlyTarts',
            'vod_play_url': '播放$' + slug,
        }
        return {'list': [vod]}

    # ==================== 播放链接提取（4层兜底） ====================

    def _extract_play_url(self, html, slug):
        """主提取方法：4 层兜底"""
        # 0. 缓存
        if slug in self._play_cache:
            print(f"[OnlyTarts] Cache hit for {slug}")
            return self._play_cache[slug]

        mp4_url = ''

        # 第 1 层：window.initials / __INITIAL_STATE__ 等
        if not mp4_url:
            mp4_url = self._extract_from_initials(html)
            if mp4_url:
                print(f"[OnlyTarts] Layer 1 success (initials)")

        # 第 2 层：所有 script 标签中的 video/sources/url 模式
        if not mp4_url:
            mp4_url = self._extract_from_scripts(html)
            if mp4_url:
                print(f"[OnlyTarts] Layer 2 success (scripts)")

        # 第 3 层：video 标签 / noscript
        if not mp4_url:
            mp4_url = self._extract_from_video_tag(html)
            if mp4_url:
                print(f"[OnlyTarts] Layer 3 success (video tag)")

        # 第 4 层：全局正则暴力搜索
        if not mp4_url:
            mp4_url = self._extract_from_global(html)
            if mp4_url:
                print(f"[OnlyTarts] Layer 4 success (global search)")

        # 清理 URL
        if mp4_url:
            mp4_url = mp4_url.strip().rstrip('"').rstrip("'").rstrip(',')
            mp4_url = html_module.unescape(mp4_url)
            mp4_url = mp4_url.replace('\\/', '/')
            # 跟随重定向获取真实地址（TVBox 播放器通常无法处理 302）
            mp4_url = self._resolve_redirect(mp4_url)
            self._play_cache[slug] = mp4_url
            print(f"[OnlyTarts] Final MP4: {mp4_url[:100]}...")

        return mp4_url

    def _extract_from_initials(self, html):
        """从 window.initials 等提取"""
        data = self._extract_initials(html)
        if not data:
            return ''

        # 尝试多种可能的 JSON 路径
        paths = [
            lambda d: d.get('video', {}).get('sources', []),
            lambda d: d.get('sources', []),
            lambda d: d.get('video', {}).get('streams', []),
            lambda d: d.get('streams', []),
            lambda d: d.get('data', {}).get('video', {}).get('sources', []),
            lambda d: d.get('video', {}).get('files', []),
            lambda d: d.get('files', []),
        ]

        sources = []
        for p in paths:
            try:
                sources = p(data)
                if sources and isinstance(sources, list):
                    break
            except Exception:
                continue

        if not sources:
            print(f"[OnlyTarts] No sources found in initials")
            return ''

        # 按清晰度打分排序
        candidates = []
        for src in sources:
            if isinstance(src, dict):
                url = src.get('url', '') or src.get('file', '') or src.get('src', '')
                title = str(src.get('title', '') or src.get('label', '') or src.get('quality', '')).lower()
            elif isinstance(src, str):
                url = src
                title = ''
            else:
                continue

            if not url or not url.startswith('http'):
                continue

            score = 50
            if '720' in title or '1280' in title or 'hd' in title:
                score = 100
            elif '1080' in title or '1920' in title or 'fhd' in title:
                score = 90
            elif '480' in title or '854' in title:
                score = 80
            elif '360' in title:
                score = 70
            elif '240' in title:
                score = 60

            # 优先 mp4，其次 m3u8
            if '.m3u8' in url:
                score -= 10

            candidates.append((score, url, title))

        if not candidates:
            return ''

        candidates.sort(key=lambda x: x[0], reverse=True)
        print(f"[OnlyTarts] Source candidates: {[(c[2], c[0]) for c in candidates[:5]]}")
        return candidates[0][1]

    def _extract_from_scripts(self, html):
        """从所有 script 标签中提取视频 URL"""
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
        for script in scripts:
            # 搜索各种视频 URL 模式
            patterns = [
                r'[\'\"](https?://[^\'\"]*xhcdn\.com/[^\'\"]*\.mp4[^\'\"]*)[\'\"]',
                r'[\'\"](https?://[^\'\"]*/videos/[^\'\"]*\.mp4[^\'\"]*)[\'\"]',
                r'url\s*:\s*[\'\"](https?://[^\'\"]*\.mp4[^\'\"]*)[\'\"]',
                r'src\s*:\s*[\'\"](https?://[^\'\"]*\.mp4[^\'\"]*)[\'\"]',
                r'[\'\"](https?://[^\'\"]*\.xhcdn\.com/[^\'\"]*\.m3u8[^\'\"]*)[\'\"]',
            ]
            for pat in patterns:
                m = re.search(pat, script, re.I)
                if m:
                    url = m.group(1).replace('\\/', '/')
                    if url.startswith('http') and ('.mp4' in url or '.m3u8' in url):
                        return url
        return ''

    def _extract_from_video_tag(self, html):
        """从 video 标签提取"""
        patterns = [
            r'<video[^>]*src=[\'\"](https?://[^\'\"]*\.mp4[^\'\"]*)[\'\"]',
            r'<video[^>]*src=[\'\"](https?://[^\'\"]*\.m3u8[^\'\"]*)[\'\"]',
            r'<source[^>]*src=[\'\"](https?://[^\'\"]*\.mp4[^\'\"]*)[\'\"]',
            r'<source[^>]*src=[\'\"](https?://[^\'\"]*\.m3u8[^\'\"]*)[\'\"]',
            r'poster=[\'\"](https?://[^\'\"]*)[\'\"][^>]*src=[\'\"](https?://[^\'\"]*\.mp4)[\'\"]',
        ]
        for pat in patterns:
            m = re.search(pat, html, re.I | re.DOTALL)
            if m:
                # 如果有 poster+src 组合，取最后一个 group
                url = m.group(m.lastindex)
                url = url.replace('\\/', '/')
                if url.startswith('http'):
                    return url
        return ''

    def _extract_from_global(self, html):
        """全局暴力搜索"""
        # 先找 MP4
        mp4s = re.findall(r'(https?://[^\s\"\'<>]+\.mp4(?:\?[^\s\"\'<>]*)?)', html)
        for u in mp4s:
            u = u.replace('\\/', '/')
            if 'xhcdn' in u or 'onlytarts' in u:
                return u
        # 再找 m3u8
        m3u8s = re.findall(r'(https?://[^\s\"\'<>]+\.m3u8(?:\?[^\s\"\'<>]*)?)', html)
        for u in m3u8s:
            u = u.replace('\\/', '/')
            if 'xhcdn' in u or 'onlytarts' in u:
                return u
        # 最后放宽条件
        if mp4s:
            return mp4s[0].replace('\\/', '/')
        if m3u8s:
            return m3u8s[0].replace('\\/', '/')
        return ''

    def _resolve_redirect(self, url):
        """跟随 302 重定向获取真实 URL（TVBox 播放器通常无法跟随）"""
        if not url:
            return url
        try:
            import requests
            # 先尝试 HEAD
            r = requests.head(url, headers=self.header, allow_redirects=True, timeout=15)
            if r.status_code < 400 and r.url != url:
                print(f"[OnlyTarts] Redirect resolved (HEAD): {r.url[:80]}...")
                return r.url
        except Exception as e:
            print(f"[OnlyTarts] HEAD redirect failed: {e}")

        try:
            import requests
            # 再尝试 GET (stream=True 避免下载完整视频)
            r = requests.get(url, headers=self.header, allow_redirects=True, stream=True, timeout=15)
            final = r.url
            r.close()
            if final != url:
                print(f"[OnlyTarts] Redirect resolved (GET): {final[:80]}...")
                return final
        except Exception as e:
            print(f"[OnlyTarts] GET redirect failed: {e}")

        return url

    # ==================== 播放器接口 ====================

    def playerContent(self, flag, id, vipFlags):
        """
        TVBox 播放器接口。
        关键：返回格式必须严格兼容，否则播放器拒绝播放。
        """
        print(f"[OnlyTarts] playerContent called: flag={flag}, id={id}")

        if not id:
            print("[OnlyTarts] playerContent: empty id")
            return {'parse': 1, 'playUrl': '', 'url': ''}

        # 解析 id（可能格式: "播放$slug" 或 "slug" 或 URL 编码）
        raw_id = str(id).strip()
        if '$' in raw_id:
            slug = raw_id.split('$')[-1]
        else:
            slug = raw_id

        # URL 解码（以防 TVBox 编码了特殊字符）
        try:
            from urllib.parse import unquote
            slug = unquote(slug)
        except Exception:
            pass

        print(f"[OnlyTarts] playerContent: resolved slug={slug}")

        if not slug:
            return {'parse': 1, 'playUrl': '', 'url': ''}

        # 获取 MP4 地址
        mp4_url = self._play_cache.get(slug)
        if not mp4_url:
            print(f"[OnlyTarts] Cache miss, fetching detail page for {slug}")
            url = f'{self.host}/video/{slug}'
            html = self._fetch_html(url)
            if html:
                mp4_url = self._extract_play_url(html, slug)

        if not mp4_url:
            print(f"[OnlyTarts] playerContent: FAILED to get MP4 for {slug}")
            return {'parse': 1, 'playUrl': '', 'url': ''}

        print(f"[OnlyTarts] playerContent: returning MP4 {mp4_url[:80]}...")

        # 构建播放器返回（兼容 T3/T4 多种版本）
        result = {
            'parse': 0,           # 0 = 直链播放，不需要解析
            'jx': 0,              # 0 = 不需要解析
            'playUrl': '',        # 解析服务地址（空表示直链）
            'url': mp4_url,       # 视频真实地址
            'format': 'video/mp4',
            'contentType': 'video/mp4',
            'header': {
                'User-Agent': self.header['User-Agent'],
                'Referer': self.host + '/',
                'Origin': self.host,
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
            },
        }

        # 某些 TVBox 版本需要这些额外字段
        if '.m3u8' in mp4_url:
            result['format'] = 'application/x-mpegURL'
            result['contentType'] = 'application/x-mpegURL'

        print(f"[OnlyTarts] playerContent result keys: {list(result.keys())}")
        return result

    def searchContent(self, key, quick, pg):
        page = int(pg) if pg else 1
        if page < 1:
            page = 1
        try:
            url = f'{self.host}/search/{key}?page={page}'
            html = self._fetch_html(url)
            videos = self._parse_videos(html)
            page_count = self._get_pagecount(html)
            if page_count < 1:
                page_count = 1
            return {
                'list': videos,
                'page': page,
                'pagecount': page_count,
                'limit': len(videos),
                'total': page_count * 12,
            }
        except Exception:
            return {'list': [], 'page': page, 'pagecount': 1, 'limit': 0, 'total': 0}

    def isLive(self):
        return False

    def manualContent(self, lv):
        return {}
