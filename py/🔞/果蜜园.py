# -*- coding: utf-8 -*-
# TVBox Spider for xHamster (zh.xhamster1.desi)
# Support: categories, subcategory filters, search, video playback

import sys
import re
import json
import urllib.parse

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    HOST = 'https://zh.xhamster1.desi'

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://zh.xhamster1.desi/'
    }

    # ---- popular categories with Chinese names ----
    CATEGORIES = [
        ('newest', '最新'),
        ('best/month', '本月最佳'),
        ('categories/asian', '亚洲人'),
        ('categories/japanese', '日本人'),
        ('categories/chinese', '中国人'),
        ('categories/korean', '韩国人'),
        ('categories/amateur', '素人'),
        ('categories/homemade', '家庭自制'),
        ('categories/mature', '成熟'),
        ('categories/milf', '人妻'),
        ('categories/mom', '人母'),
        ('categories/old-young', '老少配'),
        ('categories/lesbian', '女同'),
        ('categories/anal', '肛交'),
        ('categories/creampie', '内射'),
        ('categories/big-tits', '大奶子'),
        ('categories/big-ass', '大屁股'),
        ('categories/big-cock', '大鸡巴'),
        ('categories/bbw', '胖美女'),
        ('categories/teen', '青年'),
        ('categories/18-year-old', '18岁'),
        ('categories/pov', '第一人称视角'),
        ('categories/blowjob', '口交'),
        ('categories/cumshot', '射精'),
        ('categories/creampie', '内射'),
        ('categories/hentai', '成人动漫'),
        ('categories/cartoon', '卡通'),
        ('categories/3d', '3D'),
        ('categories/vintage', '复古'),
        ('categories/hairy', '毛发浓密'),
        ('categories/interracial', '跨人种'),
        ('categories/group-sex', '群交'),
        ('categories/gangbang', '多对一群交'),
        ('categories/threesome', '3P'),
        ('categories/public-sex', '公共场合性爱'),
        ('categories/voyeur', '偷窥癖'),
        ('categories/webcam', '直播'),
        ('categories/cosplay', '角色扮演'),
        ('categories/compilation', '合集'),
        ('categories/cuckold', '绿帽奴'),
        ('categories/uncensored', '无码'),
        ('categories/jav', '日本AV'),
        ('categories/solo', '单人表演'),
        ('categories/romantic', '浪漫'),
        ('categories/softcore', '唯美'),
        ('categories/orgy', '群交派对'),
        ('categories/swingers', '换妻癖者'),
        ('categories/bdsm', '捆绑SM'),
        ('categories/bondage', '捆绑'),
        ('categories/femdom', '女主调教'),
        ('categories/squirting', '潮吹'),
        ('categories/pregnant', '怀孕'),
    ]

    # ---- sort filter options ----
    SORT_OPTIONS = [
        {'n': '最新', 'v': 'newest'},
        {'n': '最佳', 'v': 'best'},
        {'n': '本月最佳', 'v': 'best/month'},
        {'n': '本周最佳', 'v': 'best/week'},
        {'n': 'HD', 'v': 'hd'},
        {'n': '4K', 'v': '4k'},
        {'n': 'VR', 'v': 'vr'},
        {'n': '长片', 'v': 'full-length'},
        {'n': '短片', 'v': 'shorts'},
    ]

    # ---- duration filter options ----
    DURATION_OPTIONS = [
        {'n': '全部时长', 'v': ''},
        {'n': '0-2分钟', 'v': '?min-duration=0&max-duration=2'},
        {'n': '2-5分钟', 'v': '?min-duration=2&max-duration=5'},
        {'n': '5-10分钟', 'v': '?min-duration=5&max-duration=10'},
        {'n': '10-30分钟', 'v': '?min-duration=10&max-duration=30'},
        {'n': '30-60分钟', 'v': '?min-duration=30&max-duration=60'},
        {'n': '60分钟以上', 'v': '?min-duration=60'},
    ]

    def getName(self):
        return "xHamster"

    def init(self, extend=""):
        self.extend = extend

    def isVideoFormat(self, url):
        if not url:
            return False
        return '.mp4' in url or '.m3u8' in url

    def manualVideoWrith(self):
        return

    # ============================================================
    #  Home: return categories + filters
    # ============================================================
    def homeContent(self, filter):
        result = {}
        classes = []
        for tid, name in self.CATEGORIES:
            classes.append({"type_id": tid, "type_name": name})
        result['class'] = classes

        if filter:
            filters = {}
            for tid, name in self.CATEGORIES:
                filters[tid] = [
                    {"key": "sort", "name": "排序", "value": self.SORT_OPTIONS},
                    {"key": "duration", "name": "时长", "value": self.DURATION_OPTIONS},
                ]
            result['filters'] = filters

        return result

    def homeVideoContent(self):
        url = self.HOST + '/'
        html = self.fetch(url, headers=self.HEADERS).text
        videos = self._parse_video_list(html)
        return {"list": videos}

    # ============================================================
    #  Category: list videos by category with filters
    # ============================================================
    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        page = int(pg) if pg and str(pg).isdigit() else 1

        # parse extend (filter selections)
        try:
            ext = json.loads(extend) if extend else {}
        except Exception:
            ext = {}

        sort = ext.get('sort', '')
        duration = ext.get('duration', '')

        # determine if tid is a special route (newest, best/month, etc.)
        # or a category path (categories/xxx)
        if tid.startswith('categories/') or tid.startswith('categories'):
            # category page: /categories/{slug}[/{sort}] [/{page}] [?duration]
            parts = [tid]
            if sort:
                parts.append(sort)
            if page > 1:
                parts.append(str(page))
            path = '/'.join(parts)
            url = '{}/{}'.format(self.HOST, path)
        else:
            # special routes like newest, best/month
            parts = [tid]
            if sort:
                # avoid double sort for special routes like newest/best
                # if tid already contains a sort keyword, replace
                if '/' in tid:
                    parts = [tid.split('/')[0] + '/' + sort.split('/')[-1]]
                else:
                    parts = [sort]
            if page > 1:
                parts.append(str(page))
            path = '/'.join(parts)
            url = '{}/{}'.format(self.HOST, path)

        if duration:
            url = url + duration

        try:
            resp = self.fetch(url, headers=self.HEADERS)
            html = resp.text
            videos = self._parse_video_list(html)
        except Exception:
            videos = []

        result['list'] = videos
        result['page'] = page
        result['pagecount'] = 9999
        result['limit'] = len(videos)
        result['total'] = 999999

        return result

    # ============================================================
    #  Search: search videos by keyword
    # ============================================================
    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, 1)

    def searchContentPage(self, key, quick, page):
        key_encoded = urllib.parse.quote(key)
        url = '{}/search/{}?page={}'.format(self.HOST, key_encoded, page)

        try:
            resp = self.fetch(url, headers=self.HEADERS)
            html = resp.text
            videos = self._parse_video_list(html)
        except Exception:
            videos = []

        result = {
            'list': videos,
            'page': page,
            'pagecount': 9999,
            'limit': len(videos),
            'total': 999999
        }
        return result

    # ============================================================
    #  Detail: parse video detail page
    # ============================================================
    def detailContent(self, ids):
        video_id = ids[0]
        url = '{}/videos/{}'.format(self.HOST, video_id)

        try:
            resp = self.fetch(url, headers=self.HEADERS)
            html = resp.text
        except Exception:
            return {"list": []}

        # ---- title: prefer og:title, then h1, then <title> ----
        title = ''
        title_match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
        if not title_match:
            title_match = re.search(r"<meta\s+property='og:title'\s+content='([^']+)'", html)
        if not title_match:
            title_match = re.search(r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</h1>', html, re.DOTALL)
            if title_match:
                title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
        if not title_match:
            title_match = re.search(r'<title>([^<|]+)', html)
        if title_match and not title:
            title = title_match.group(1).strip()
        title = title if title else video_id

        # ---- thumbnail: prefer og:image ----
        thumb_match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
        if not thumb_match:
            thumb_match = re.search(r"<meta\s+property='og:image'\s+content='([^']+)'", html)
        if not thumb_match:
            thumb_match = re.search(r'"thumbnailUrl"\s*:\s*"([^"]+)"', html)
        if not thumb_match:
            thumb_match = re.search(r'<link[^>]*rel="image_src"[^>]*href="([^"]+)"', html)
        thumb = thumb_match.group(1) if thumb_match else ''

        # ---- description: handle mixed quote styles (name="..." content='...') ----
        desc = ''
        desc_match = re.search(r'<meta\s+name=["\']?description["\']?\s+content=["\']([^"\']+)["\']', html)
        if not desc_match:
            desc_match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', html)
        if not desc_match:
            desc_match = re.search(r'"description"\s*:\s*"([^"]+)"', html)
        if desc_match:
            desc = desc_match.group(1)
        desc = desc.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')

        # ---- tags ----
        tag_matches = re.findall(r'<a[^>]*class="[^"]*tag[^"]*"[^>]*>([^<]+)</a>', html)
        tags = [t.strip() for t in tag_matches[:10]]
        tag_str = ' '.join(tags) if tags else ''

        # ---- play URL: prefer m3u8 (HLS multi-quality) ----
        play_url = ''
        # Method 1: <link rel="preload" href="...m3u8">
        m3u8_match = re.search(r'<link[^>]*rel="preload"[^>]*href="(https://video[^"]*\.m3u8[^"]*)"', html)
        if m3u8_match:
            play_url = m3u8_match.group(1)
        else:
            # Method 2: any m3u8 URL in the page
            m3u8_match = re.search(r'(https://video[^"\s]+\.m3u8[^"\s]*)', html)
            if m3u8_match:
                play_url = m3u8_match.group(1)
            else:
                # Method 3: direct mp4 from noscript fallback
                mp4_match = re.search(r'<noscript>.*?src="(https://video[^"]*\.mp4[^"]*)"', html, re.DOTALL)
                if mp4_match:
                    play_url = mp4_match.group(1)
                else:
                    mp4_match = re.search(r'(https://video\d*\.cdnsolutions\.media/[^"\s]+\.mp4[^"\s]*)', html)
                    if mp4_match:
                        play_url = mp4_match.group(1)

        # ---- duration: extract from JSON data (seconds) ----
        duration_str = ''
        # Try ISO 8601 format first: "duration":"PT5M48S"
        dur_match = re.search(r'"duration"\s*:\s*"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"', html)
        if dur_match:
            hours = int(dur_match.group(1) or 0)
            mins = int(dur_match.group(2) or 0)
            secs = int(dur_match.group(3) or 0)
            if hours > 0:
                duration_str = '{:02d}:{:02d}:{:02d}'.format(hours, mins, secs)
            else:
                duration_str = '{:02d}:{:02d}'.format(mins, secs)
        else:
            # Try numeric seconds format: "duration":473
            dur_match2 = re.search(r'"duration"\s*:\s*(\d+)', html)
            if dur_match2:
                total = int(dur_match2.group(1))
                hours = total // 3600
                mins = (total % 3600) // 60
                secs = total % 60
                if hours > 0:
                    duration_str = '{:02d}:{:02d}:{:02d}'.format(hours, mins, secs)
                else:
                    duration_str = '{:02d}:{:02d}'.format(mins, secs)

        vod_info = {
            'vod_id': video_id,
            'vod_name': title,
            'vod_pic': thumb,
            'vod_remarks': duration_str,
            'vod_year': '',
            'vod_area': '',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': desc,
            'vod_tag': tag_str,
            'vod_play_from': 'xHamster',
            'vod_play_url': 'xHamster${}'.format(play_url)
        }

        return {"list": [vod_info]}

    # ============================================================
    #  Player: return play URL with headers
    # ============================================================
    def playerContent(self, flag, id, vipFlags):
        result = {
            'parse': 0,
            'playUrl': '',
            'url': id,
            'header': json.dumps(self.HEADERS)
        }
        return result

    # ============================================================
    #  Helper: parse video list from HTML
    # ============================================================
    def _parse_video_list(self, html):
        videos = []
        seen = set()

        # Pattern 1: video-thumb__image-container with href and aria-label
        # This captures the main video link and title
        thumb_pattern = re.compile(
            r'<a[^>]*class="video-thumb__image-container[^"]*"[^>]*'
            r'href="https://zh\.xhamster1\.desi/videos/([^"]+)"'
            r'[^>]*aria-label="([^"]*)"',
            re.DOTALL
        )
        matches = thumb_pattern.findall(html)

        # Extract all thumbnails (img src in thumb containers)
        img_pattern = re.compile(
            r'<img[^>]*class="[^"]*thumb-image-container__image[^"]*"[^>]*'
            r'src="([^"]*)"'
            r'[^>]*alt="([^"]*)"',
            re.DOTALL
        )
        img_matches = img_pattern.findall(html)

        # Extract all durations
        dur_pattern = re.compile(
            r'data-role="video-duration"[^>]*>.*?'
            r'<div[^>]*>([^<]+)</div>',
            re.DOTALL
        )
        dur_matches = dur_pattern.findall(html)

        # Extract HD/4K badges
        badge_pattern = re.compile(
            r'class="[^"]*video-thumb-image__badge[^"]*"[^>]*>([^<]+)',
            re.DOTALL
        )
        badge_matches = badge_pattern.findall(html)

        # Build video list
        for i, (slug, title) in enumerate(matches):
            if slug in seen:
                continue
            seen.add(slug)

            # Clean title
            title = title.replace('&amp;', '&').replace('&quot;', '"').strip()

            # Find matching thumbnail
            pic = ''
            for img_url, img_alt in img_matches:
                if title in img_alt or slug in img_url:
                    pic = img_url
                    break
            # Fallback: use index-based matching
            if not pic and i < len(img_matches):
                pic = img_matches[i][0]

            # Find duration
            remark = ''
            if i < len(dur_matches):
                remark = dur_matches[i].strip()

            # Add badge if available
            if i < len(badge_matches) and badge_matches[i].strip():
                remark = '{} {}'.format(badge_matches[i].strip(), remark).strip()

            videos.append({
                'vod_id': slug,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': remark
            })

        # Fallback: if Pattern 1 didn't match, try simpler pattern
        if not videos:
            simple_pattern = re.compile(
                r'href="https://zh\.xhamster1\.desi/videos/([^"]+)"[^>]*'
                r'(?:aria-label|title)="([^"]*)"',
                re.DOTALL
            )
            simple_matches = simple_pattern.findall(html)
            for slug, title in simple_matches:
                if slug in seen:
                    continue
                seen.add(slug)
                title = title.replace('&amp;', '&').strip()
                videos.append({
                    'vod_id': slug,
                    'vod_name': title,
                    'vod_pic': '',
                    'vod_remarks': ''
                })

        return videos
