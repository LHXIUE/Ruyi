# -*- coding: utf-8 -*-
"""
色天堂 TVBox / 影视仓 Spider (dr_py)
=============================================
目标: https://xn--0812ic51-7w4nx7c.settav03.sbs/
日期: 20260908

站点结构:
  分类: /vod-type/id-{N}-by-{sort}-pg-{N}.html
  详情: /vod-detail/id-{N}.html
  播放: /vod-play/id-{N}.html (主), /vod-play/idb-{N}.html (备用)
  搜索: /vod-search/wd-{keyword}-by-time-pg-{N}.html

反爬机制:
  1. d() 函数: 所有标题/文本/URL用 base64 编码, 前端JS d() 函数解码
     → Python 端直接 base64.b64decode 解码
  2. display:none 垃圾span: 解码后的文本中插入 <span style='display:none;'>垃圾字符</span>
     → 用正则清除 hidden span, 再去 HTML 标签

m3u8 提取:
  播放页 HTML 中直接包含 m3u8 直链
  备用播放页 iframe src 参数中也可能包含 m3u8
"""

import sys
import re
import json
import base64
import urllib.parse

sys.path.append('..')
try:
    from base.spider import Spider
except Exception:
    class Spider(object):
        def fetch(self, url, headers=None, **kw):
            import requests
            kw.pop('timeout', None)
            return requests.get(url, headers=headers, timeout=15, verify=False, **kw)

        def post(self, url, headers=None, **kw):
            import requests
            return requests.post(url, headers=headers, verify=False, timeout=15, **kw)

        def init(self, extend=""):
            pass


class Spider(Spider):

    HOST = 'https://xn--0812ic51-7w4nx7c.settav03.sbs'

    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.host = self.HOST
        self.ua = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/131.0.0.0 Safari/537.36')

    # ==================== 基础接口 ====================

    def getName(self):
        return "色天堂"

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        if not url:
            return False
        u = url.lower()
        return any(ext in u for ext in ['.m3u8', '.mp4', '.flv', '.ts', '/m3u8'])

    def manualWebSearch(self):
        return False

    def homeContent(self, filter):
        classes = [
            {"type_name": "奥斯卡资源", "type_id": "14"},
            {"type_name": "乐播资源", "type_id": "15"},
            {"type_name": "老色逼资源", "type_id": "18"},
        ]
        filters = {}
        result = {"class": classes, "filters": filters}
        try:
            home_data = self.homeContentVod()
            if home_data:
                result["list"] = home_data
        except Exception as e:
            pass
        return result

    def homeContentVod(self):
        html = self._fetch_page('/')
        return self._parse_vod_list(html)

    def homeVideoContent(self):
        try:
            return self.homeContentVod()
        except:
            return []

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        sort = 'time'
        if extend and 'sort' in extend:
            sort = extend['sort']
        url = f'{self.host}/vod-type/id-{tid}-by-{sort}-pg-{page}.html'
        html = self._fetch_page(url)
        videos = self._parse_vod_list(html)
        # page count
        total = page
        pagecount_match = re.search(r'pg-(\d+)\.html', html)
        if pagecount_match:
            pass
        max_match = re.findall(r'pg-(\d+)\.html', html)
        if max_match:
            total = max(int(m) for m in max_match)
        limit = len(videos) if videos else 20
        total_count = total * limit
        return {
            'list': videos,
            'page': page,
            'pagecount': total,
            'limit': limit,
            'total': total_count
        }

    def detailContent(self, ids):
        vid = ids[0]
        url = f'{self.host}/vod-detail/id-{vid}.html'
        html = self._fetch_page(url)

        # title: site1 uses <h3> with d() encoded content (not <h1> which is logo)
        title = ''
        title_m = re.search(r'<h3[^>]*>(.*?)</h3>', html, re.DOTALL)
        if title_m:
            title = self._decode_content(title_m.group(1))
        if not title:
            # fallback: first d() call that contains the title
            for d in re.findall(r"d\('([^']+)'\)", html):
                decoded = self._clean_junk(self._decode_d(d))
                if len(decoded) > 5 and '在线观看' not in decoded:
                    title = decoded
                    break

        # pic
        pic = ''
        pic_m = (re.search(r'data-original="([^"]+)"', html) or
                 re.search(r'data-src="([^"]+)"', html) or
                 re.search(r'<img[^>]*src="([^"]+)"', html))
        if pic_m:
            pic = pic_m.group(1)
            if 'load_' in pic or 'default' in pic:
                pic = ''

        # description
        desc = ''
        desc_m = re.search(r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        if desc_m:
            desc = self._decode_content(desc_m.group(1))

        # play links - TVBox format: play_from = "线路1$$$线路2", play_url = "名称1$链接1#名称2$链接2$$$名称3$链接3"
        play_links = re.findall(r'href="(/vod-play/[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
        play_from = []
        play_url_parts = []
        seen_routes = set()
        for href, label in play_links:
            route_key = re.sub(r'\d+', '', href)
            if route_key in seen_routes:
                continue
            seen_routes.add(route_key)
            label_clean = self._decode_content(label) or '播放'
            play_from.append(label_clean)
            play_url_parts.append(label_clean + '$' + href)

        # fallback: direct id play + backup
        if not play_from:
            play_from = ['播放1', '备用']
            play_url_parts = ['播放1$/vod-play/id-{}.html'.format(vid), '备用$/vod-play/idb-{}.html'.format(vid)]

        from_str = '$$$'.join(play_from)
        url_str = '#'.join(play_url_parts)
        vod_play_url = from_str + '$$$' + url_str

        # info
        year = ''
        area = ''
        actor = ''
        director = ''
        remarks = ''
        # try extract info from labels
        info_patterns = [
            (r'(?:年份|发行)[：:]?\s*(\d{4})', 'year'),
            (r'(?:地区|国家)[：:]?\s*([^\s<]+)', 'area'),
            (r'(?:主演|演员)[：:]?\s*(.*?)(?:<|$|导演)', 'actor'),
            (r'(?:导演)[：:]?\s*(.*?)(?:<|$|主演)', 'director'),
        ]
        for pat, field in info_patterns:
            m = re.search(pat, html)
            if m:
                val = self._decode_content(m.group(1))
                if field == 'year':
                    year = val
                elif field == 'area':
                    area = val
                elif field == 'actor':
                    actor = val
                elif field == 'director':
                    director = val

        # remarks from play page
        state_m = re.search(r'(更新|完结|状态)[：:]?\s*(.*?)(?:<|$)', html)
        if state_m:
            remarks = self._decode_content(state_m.group(2))

        return {
            'list': [{
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': remarks,
                'vod_year': year,
                'vod_area': area,
                'vod_actor': actor,
                'vod_director': director,
                'vod_content': desc,
                'vod_play_from': from_str,
                'vod_play_url': url_str,
            }]
        }

    def searchContent(self, key, quick, pg=1):
        page = int(pg) if pg else 1
        keyword = urllib.parse.quote(key)
        url = f'{self.host}/vod-search/wd-{keyword}-by-time-pg-{page}.html'
        html = self._fetch_page(url)
        videos = self._parse_vod_list(html)
        return {
            'list': videos,
            'page': page,
            'pagecount': 1,
            'limit': len(videos) if videos else 20,
            'total': len(videos) if videos else 0
        }

    def searchContentPage(self, key, quick, pg=1):
        return self.searchContent(key, quick, pg)

    def playerContent(self, flag, id, vipFlags):
        # id is the play route href like /vod-play/id-823164.html
        if id.startswith('http'):
            play_url = id
        else:
            play_url = self.host + id

        html = self._fetch_page(play_url)

        # Strategy 1: direct m3u8/mp4 in HTML
        m3u8 = self._extract_m3u8(html)
        if m3u8:
            return {
                'parse': 0,
                'url': m3u8,
                'header': {'User-Agent': self.ua, 'Referer': self.host}
            }

        # Strategy 2: iframe with m3u8 in src or url parameter
        iframes = re.findall(r'<iframe[^>]*src="([^"]+)"', html, re.I)
        for iframe_src in iframes:
            m3u8 = self._extract_m3u8(iframe_src)
            if m3u8:
                return {
                    'parse': 0,
                    'url': m3u8,
                    'header': {'User-Agent': self.ua, 'Referer': self.host}
                }
            # iframe itself might be a player page
            iframe_html = self._fetch_page(iframe_src if iframe_src.startswith('http') else self.host + iframe_src)
            m3u8 = self._extract_m3u8(iframe_html)
            if m3u8:
                return {
                    'parse': 0,
                    'url': m3u8,
                    'header': {'User-Agent': self.ua, 'Referer': self.host}
                }

        # Strategy 3: player.php?url= pattern
        player_m = re.search(r'player\.php\?url=([^"&\']+)', html)
        if player_m:
            raw_url = urllib.parse.unquote(player_m.group(1))
            if self.isVideoFormat(raw_url):
                return {
                    'parse': 0,
                    'url': raw_url,
                    'header': {'User-Agent': self.ua, 'Referer': self.host}
                }

        # Strategy 4: encrypted d() content might contain m3u8
        d_blocks = re.findall(r"d\('([^']+)'\)", html)
        for d_block in d_blocks:
            decoded = self._decode_d(d_block)
            m3u8 = self._extract_m3u8(decoded)
            if m3u8:
                return {
                    'parse': 0,
                    'url': m3u8,
                    'header': {'User-Agent': self.ua, 'Referer': self.host}
                }

        # Strategy 5: fallback to sniff mode
        return {
            'parse': 1,
            'url': play_url,
            'header': {'User-Agent': self.ua, 'Referer': self.host}
        }

    def init(self, extend=""):
        ext = str(extend or '').strip()
        if ext.startswith('http'):
            self.host = ext.rstrip('/')
        if '|' in ext:
            parts = ext.split('|', 1)
            if parts[0].startswith('http'):
                self.host = parts[0].strip().rstrip('/')

    # ==================== 内部方法 ====================

    def _fetch_page(self, path):
        """Fetch a page and return HTML text."""
        url = path if path.startswith('http') else self.host + path
        headers = {
            'User-Agent': self.ua,
            'Referer': self.host,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        try:
            resp = self.fetch(url, headers=headers, timeout=15)
            return resp.text
        except Exception as e:
            try:
                import requests
                resp = requests.get(url, headers=headers, timeout=15, verify=False)
                return resp.text
            except:
                return ''

    def _decode_d(self, b64_str):
        """Decode d() function: base64 decode."""
        try:
            return base64.b64decode(b64_str).decode('utf-8', 'ignore')
        except:
            return ''

    def _clean_junk(self, text):
        """Remove display:none spam spans and HTML tags from decoded text."""
        if not text:
            return ''
        # Remove hidden spans (single or double quote style)
        text = re.sub(
            r"<span[^>]*style=['\"][^'\"]*display:\s*none[^'\"]*['\"][^>]*>.*?</span>",
            '', text, flags=re.DOTALL
        )
        # Remove remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Clean whitespace
        return text.strip()

    def _decode_content(self, raw_html):
        """Decode content that may contain d() calls and junk spans."""
        if not raw_html:
            return ''
        # Find all d() calls and decode them
        d_calls = re.findall(r"d\('([^']+)'\)", raw_html)
        if d_calls:
            decoded = ''
            for d in d_calls:
                decoded += self._decode_d(d)
            return self._clean_junk(decoded)
        # No d() calls, just clean HTML
        return self._clean_junk(raw_html)

    def _extract_m3u8(self, text):
        """Extract m3u8/mp4 URL from text."""
        if not text:
            return ''
        # Direct m3u8
        m = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', text)
        if m:
            return m.group(1)
        # Direct mp4
        m = re.search(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', text)
        if m:
            return m.group(1)
        # m3u8 in url parameter
        m = re.search(r'[?&]url=(https?://[^\s"&\'<>]+\.m3u8[^\s"&\'<>]*)', text)
        if m:
            return urllib.parse.unquote(m.group(1))
        m = re.search(r'[?&]url=(https?://[^\s"&\'<>]+)', text)
        if m:
            decoded = urllib.parse.unquote(m.group(1))
            if '.m3u8' in decoded or '.mp4' in decoded:
                return decoded
        return ''

    def _parse_vod_list(self, html):
        """Parse video list from category/search/home page.
        Site1 uses <div class="vod"> containers, each with an <img> and a
        <script>document.write(d('...'))</script> title.
        """
        videos = []
        if not html:
            return videos

        # Split by <div class="vod"> containers
        blocks = re.split(r'<div class="vod">', html)
        blocks = blocks[1:]  # skip content before first block
        seen_ids = set()
        for block in blocks:
            # detail link + id
            link_m = re.search(r'href="/vod-detail/id-(\d+)[^"]*"', block)
            if not link_m:
                continue
            vid = link_m.group(1)
            if vid in seen_ids:
                continue
            seen_ids.add(vid)

            # title: decode all d() calls in the block, then clean
            title = self._decode_content(block)
            if not title:
                continue
            # truncate long titles to first meaningful line
            title = title.split('_')[0].strip() if '_' in title else title
            if len(title) > 100:
                title = title[:100]

            # image: data-original preferred, then data-src, then src
            pic = ''
            img_m = (re.search(r'data-original="([^"]+)"', block) or
                     re.search(r'data-src="([^"]+)"', block) or
                     re.search(r'<img[^>]*src="([^"]+)"', block))
            if img_m:
                pic = img_m.group(1)
                # skip placeholder images
                if 'load_' in pic or 'default' in pic:
                    pic = ''

            # remarks (score)
            remarks = ''
            score_m = re.search(r'>([\d.]+)\s*分<', block)
            if score_m:
                remarks = score_m.group(1) + '分'

            videos.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': remarks
            })
        return videos
