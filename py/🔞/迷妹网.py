# -*- coding: utf-8 -*-
"""
3bmm 迷妹网 - v7 修复版
  修复：detailContent 中判断详情页有效性时，检查是否包含 vHLSurl/player 数据
  避免 404 错误页面被误判为有效详情页
"""
import sys
import json
import re
import time
from urllib.parse import urljoin, quote

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as rq
    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            try:
                r.encoding = 'utf-8'
            except Exception:
                pass
            return r


class Spider(Spider):

    def getName(self):
        return "3bmm迷妹"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''

        self.header = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }

        self.domains = [
            "https://fdsunru.info",
            "https://vkayrtz.info",
            "https://oahgtmr.info",
            "https://uptjdzh.info",
            "https://mkzmgpn.info",
            "https://dxpmfrs.info",
            "https://3bmm.com",
        ]

        self.host = self._probe_best_domain()
        self.header['Referer'] = self.host + '/'
        self._home_cache = []
        self._home_cache_time = 0
        self._vod_cache = {}

    def _probe_best_domain(self):
        for domain in self.domains:
            try:
                r = self.fetch(domain, headers=self.header, timeout=10)
                text = self._get_text(r)
                if text and len(text) > 1000:
                    return domain
            except Exception:
                continue
        return self.domains[0]

    def _get_text(self, rsp):
        if rsp is None:
            return ''
        if isinstance(rsp, str):
            return rsp
        if isinstance(rsp, bytes):
            try:
                return rsp.decode('utf-8')
            except Exception:
                return rsp.decode('utf-8', errors='ignore')
        try:
            return rsp.text
        except Exception:
            try:
                return rsp.content.decode('utf-8', errors='ignore')
            except Exception:
                return str(rsp)

    def _url(self, path):
        if not path:
            return self.host
        if path.startswith('http'):
            return path
        return self.host + path if path.startswith('/') else self.host + '/' + path

    def _fetch_html(self, url, referer=None, timeout=30):
        headers = dict(self.header)
        if referer:
            headers['Referer'] = referer
        try:
            rsp = self.fetch(url, headers=headers, timeout=timeout)
            return self._get_text(rsp)
        except Exception:
            return ''

    # ========== 分类定义 ==========
    classes = [
        {'type_name': '国产', 'type_id': 'guochan'},
        {'type_name': '直播', 'type_id': 'zhibo'},
        {'type_name': '日韩', 'type_id': 'rihan'},
        {'type_name': '欧美', 'type_id': 'oumei'},
        {'type_name': '三级', 'type_id': 'sanji'},
        {'type_name': '动漫', 'type_id': 'dongman'},
    ]

    filters = {}

    # ========== 首页 ==========
    def homeContent(self, filter):
        return {
            'class': self.classes,
            'filters': self.filters,
        }

    def homeVideoContent(self):
        now = int(time.time())
        if self._home_cache and now - self._home_cache_time < 300:
            return {'list': self._home_cache[:72]}

        tids = ['guochan', 'rihan', 'oumei', 'sanji']
        videos = []
        seen = set()

        for tid in tids:
            if len(videos) >= 72:
                break
            try:
                data = self._html_list(tid=tid, pg=1)
                for v in data.get('list', []):
                    vid = v.get('vod_id')
                    if vid and str(vid) not in seen:
                        seen.add(str(vid))
                        videos.append(v)
                    if len(videos) >= 72:
                        break
            except Exception:
                continue

        self._home_cache = videos[:72]
        self._home_cache_time = now
        return {'list': self._home_cache}

    # ========== 分类列表 ==========
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        result = self._html_list(tid=tid, pg=pg)
        if result and result.get('list'):
            return result
        return {
            'list': [],
            'page': pg,
            'pagecount': 1,
            'limit': 20,
            'total': 0,
        }

    def _html_list(self, tid, pg=1):
        try:
            if pg == 1:
                url = f"{self.host}/suoyoushipin/{tid}/"
            else:
                url = f"{self.host}/suoyoushipin/{tid}/index_{pg}.html"

            html = self._fetch_html(url, timeout=15)
            if not html:
                return None

            videos = self._parse_video_cards(html)
            if not videos:
                return None

            has_next = f'index_{pg+1}.html' in html or '下一页' in html or '下一頁' in html
            pagecount = pg + 1 if has_next else pg
            page_nums = re.findall(r'index_(\d+)\.html', html)
            if page_nums:
                max_pg = max(int(x) for x in page_nums)
                if max_pg > pagecount:
                    pagecount = max_pg

            return {
                'list': videos,
                'page': pg,
                'pagecount': pagecount,
                'limit': 20,
                'total': 0,
            }
        except Exception:
            return None

    def _parse_video_cards(self, html):
        videos = []
        if not html:
            return videos

        pattern = r'<li>\s*<a[^>]*href="(/suoyoushipin/[^/]+/([^/]+)\.html)"[^>]*title="([^"]*)"[^>]*>\s*<img[^>]*src="([^"]+)"[^>]*>\s*<p>([^<]*)</p>'
        items = re.findall(pattern, html)
        for href, vid, title, pic, p_title in items:
            name = title if title else p_title
            videos.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': pic if pic.startswith('http') else self._url(pic),
                'vod_remarks': '',
            })

        if not videos:
            pattern2 = r'href="(/suoyoushipin/[^/]+/([^/]+)\.html)"[^>]*title="([^"]*)"[^>]*>\s*<img[^>]*src="([^"]+)"'
            items2 = re.findall(pattern2, html)
            for href, vid, title, pic in items2:
                videos.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': pic if pic.startswith('http') else self._url(pic),
                    'vod_remarks': '',
                })

        if not videos:
            blocks = re.findall(r'<li[^>]*>(.*?)</li>', html, re.S)
            for li in blocks:
                href = re.search(r'href="(/suoyoushipin/[^/]+/([^/]+)\.html)"', li)
                if not href:
                    continue
                vid = href.group(2)
                pic = re.search(r'src="([^"]+\.jpg)"', li)
                pic = pic.group(1) if pic else ''
                title = re.search(r'title="([^"]*)"', li)
                title = title.group(1) if title else ''
                if not title:
                    p = re.search(r'<p>([^<]*)</p>', li)
                    title = p.group(1) if p else ''
                if vid and title:
                    videos.append({
                        'vod_id': vid,
                        'vod_name': title,
                        'vod_pic': pic if pic.startswith('http') else self._url(pic),
                        'vod_remarks': '',
                    })

        return videos

    # ========== 详情页（核心修复） ==========
    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vod_id = str(ids[0])

        if vod_id in self._vod_cache:
            return {'list': [self._vod_cache[vod_id]]}

        vod = self._html_detail(vod_id)
        return {'list': [vod] if vod else []}

    def _has_play_data(self, html):
        """检查HTML是否包含有效播放数据"""
        if not html:
            return False
        # 检查 vHLSurl
        if re.search(r'var\s+vHLSurl\s*=\s*["\']', html):
            return True
        # 检查 player_aaaa
        if re.search(r'var\s+player_[a-zA-Z0-9_]+\s*=\s*\{', html):
            return True
        # 检查 iframe
        if re.search(r'<iframe[^>]+src=["\']', html, re.S):
            return True
        return False

    def _html_detail(self, vod_id):
        try:
            # 优先尝试从缓存中获取该视频的分类信息
            # 如果没有，依次尝试所有分类路径
            cats = ['guochan', 'rihan', 'oumei', 'sanji', 'dongman', 'zhibo']
            valid_html = None
            valid_url = None

            for cat in cats:
                url = self._url(f'/suoyoushipin/{cat}/{vod_id}.html')
                html = self._fetch_html(url, timeout=10)
                # 核心修复：必须包含播放数据才算有效
                if html and self._has_play_data(html):
                    valid_html = html
                    valid_url = url
                    break

            if not valid_html:
                return None

            html = valid_html
            url = valid_url

            title = ''
            h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
            if h1:
                title = self._strip_tags(h1.group(1))
            if not title:
                title = self._match(r'<title>(.*?)</title>', html)
                title = re.sub(r'\s*[-_|].*$', '', title).strip()
                title = re.sub(r'^在线播放', '', title).strip()

            pic = ''
            for pattern in [
                r'<img[^>]*class="[^"]*pic[^"]*"[^>]*src="([^"]+)"',
                r'data-original="([^"]+)"',
                r'<img[^>]*src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"',
                r'poster="([^"]+)"',
            ]:
                m = re.search(pattern, html, re.S)
                if m:
                    pic = m.group(1)
                    break

            content = self._match(r'<meta name="description" content="([^"]*)"', html)
            if content:
                content = re.sub(r'免费在线观看.*$', '', content).strip()

            play_url = f"第1集${url}"

            vod = {
                'vod_id': str(vod_id),
                'vod_name': title,
                'vod_pic': pic if pic.startswith('http') else self._url(pic),
                'type_name': '',
                'vod_year': '',
                'vod_area': '',
                'vod_remarks': '',
                'vod_actor': '',
                'vod_director': '',
                'vod_content': content[:500] if content else '',
                'vod_play_from': '默认线路',
                'vod_play_url': play_url,
            }
            self._vod_cache[vod_id] = vod
            return vod
        except Exception:
            pass
        return None

    # ========== 搜索 ==========
    def searchContent(self, key, quick, pg="1"):
        pg = int(pg or 1)
        try:
            url = f"{self.host}/search/?wd={quote(key, safe='')}&page={pg}"
            html = self._fetch_html(url, timeout=15)
            if not html:
                return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0}

            videos = self._parse_video_cards(html)
            has_next = f'index_{pg+1}.html' in html or '下一页' in html or '下一頁' in html

            return {
                'list': videos,
                'page': pg,
                'pagecount': pg + 1 if has_next else pg,
                'limit': 20,
                'total': 0,
            }
        except Exception:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0}

    # ========== 播放解析 ==========
    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 1, "playUrl": "", "url": ""}

        url = id if str(id).startswith('http') else self._url(id)

        if self._is_direct_media(url):
            return {"parse": 0, "playUrl": "", "url": url, "header": self.header}

        html = self._fetch_html(url, referer=self.host + '/', timeout=30)
        if not html:
            return {"parse": 1, "playUrl": "", "url": url, "header": self.header}

        real = ""

        # 1. vHLSurl + vservers
        vHLSurl = re.search(r'var\s+vHLSurl\s*=\s*["\']([^"\']+)["\']', html)
        if vHLSurl:
            hls_path = vHLSurl.group(1)
            servers = re.search(r"var\s+vservers\s*=\s*(\[[^\]]+\])", html)
            if servers:
                try:
                    srv_list = json.loads(servers.group(1).replace("'", '"'))
                    if srv_list:
                        real = srv_list[0].rstrip('/') + hls_path
                except:
                    srv_items = re.findall(r"['\"](https?://[^'\"]+)['\"]", servers.group(1))
                    if srv_items:
                        real = srv_items[0].rstrip('/') + hls_path
            else:
                real = self.host.rstrip('/') + hls_path

        # 2. player_aaaa
        if not real:
            m = re.search(r'var\s+player_[a-zA-Z0-9_]+\s*=\s*(\{.*?\})\s*</script>', html, re.S)
            if m:
                try:
                    pdata = json.loads(m.group(1))
                    real = pdata.get('url', '')
                    encrypt = pdata.get('encrypt', 0)
                    if encrypt in [1, 2] and real:
                        try:
                            real = base64.b64decode(real).decode('utf-8')
                        except Exception:
                            pass
                except Exception:
                    pass

        # 3. iframe
        if not real:
            iframe = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.S)
            if iframe:
                iframe_url = self._url(iframe.group(1))
                iframe_html = self._fetch_html(iframe_url, referer=url, timeout=30)
                m2 = re.search(r'var\s+vHLSurl\s*=\s*["\']([^"\']+)["\']', iframe_html)
                if m2:
                    hls_path = m2.group(1)
                    srv = re.search(r"var\s+vservers\s*=\s*(\[[^\]]+\])", iframe_html)
                    if srv:
                        try:
                            srv_list = json.loads(srv.group(1).replace("'", '"'))
                            if srv_list:
                                real = srv_list[0].rstrip('/') + hls_path
                        except:
                            srv_items = re.findall(r"['\"](https?://[^'\"]+)['\"]", srv.group(1))
                            if srv_items:
                                real = srv_items[0].rstrip('/') + hls_path
                if not real:
                    real = self._match(r'"url"\s*:\s*"([^"]+)"', iframe_html)
                if not real:
                    real = self._match(r'src=["\'](https?://[^"\']+\.(?:m3u8|mp4))["\']', iframe_html)

        # 4. 全局 m3u8/mp4
        if not real:
            m2 = re.search(r'["\'](https?://[^"\']+\.(?:m3u8|mp4)[^"\']*)["\']', html, re.I)
            if m2:
                real = m2.group(1)

        # 5. HLS 子清单
        if real and ".m3u8" in real:
            real = self._resolve_m3u8_child(real, referer=url)

        if real:
            real = real.replace("\\/", "/")
            return {
                "parse": 0,
                "playUrl": "",
                "url": real,
                "header": {
                    "User-Agent": self.header["User-Agent"],
                    "Referer": url,
                },
            }

        return {"parse": 1, "playUrl": "", "url": url, "header": self.header}

    def _is_direct_media(self, url):
        url = (url or "").lower()
        return any(ext in url for ext in [".m3u8", ".mp4", ".flv", ".mkv"])

    def _resolve_m3u8_child(self, m3u8_url, referer=""):
        text = self._fetch_html(m3u8_url, referer=referer or self.host + '/', timeout=20)
        if not text or "#EXTM3U" not in text:
            return m3u8_url
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF"):
                for nxt in lines[i + 1:]:
                    if nxt and not nxt.startswith("#"):
                        return urljoin(m3u8_url, nxt)
        return m3u8_url

    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]

    def _match(self, pattern, text, flags=0):
        m = re.search(pattern, text, flags)
        return m.group(1) if m else ""

    def _strip_tags(self, text):
        if not text:
            return ""
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.S)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.S)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def destroy(self):
        pass

    def close(self):
        self.destroy()
