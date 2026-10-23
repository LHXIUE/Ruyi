# coding=utf-8
#!/usr/bin/python
"""
玉女百科 Spider - 纯技术学习用爬虫
目标站: petersdigest.com (玉女百科 / JAEVE)
结构: 服务端 JS 加密 HTML，解密方法: 直接 hex decode
播放: 代理转发的 MP4 preview 视频@猪猪
"""
import sys
sys.path.append('..')
from base.spider import Spider as BaseSpider
import json
import urllib.parse
import re
import requests
import binascii
from html import unescape

# 抑制 verify=False 的 SSL 警告
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


class Spider(BaseSpider):

    def getName(self):
        return "JAEVE"

    def init(self, extend=""):
        self.host = "https://petersdigest.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Referer': self.host + '/',
        }
        # 分类: 从页脚导航提取的实际分类
        self.categories = [
            {'type_id': 'cn/new', 'type_name': '最近更新'},
            {'type_id': 'cn/release', 'type_name': '新作上市'},
            {'type_id': 'cn/uncensored-leak', 'type_name': '无码流出'},
            {'type_id': 'cn/chinese-subtitle', 'type_name': '中文字幕'},
            {'type_id': 'cn/today-hot', 'type_name': '今日热门'},
            {'type_id': 'cn/weekly-hot', 'type_name': '本周热门'},
            {'type_id': 'cn/monthly-hot', 'type_name': '本月热门'},
        ]
        self.timeout = 20
        self.log("JAEVE爬虫初始化完成，Host: %s" % self.host)

    # ===================== 解密核心 =====================

    def _decrypt_html(self, raw_html):
        """解密服务端 JS 加密的 HTML

        加密方式: 整个 HTML 文档被转义为十六进制字符串
        解密方式: 直接 binascii.unhexlify() + utf-8 decode
        加密字符串位于页面最外层 script 中，通常是页面上最长的十六进制字符串
        """
        try:
            # 找最长的十六进制字符串 (>= 1000 字符)
            hex_matches = re.findall(r'"([0-9a-fA-F]{1000,})"', raw_html)
            if not hex_matches:
                self.log("未找到加密内容，可能已经是明文")
                return raw_html

            hex_str = max(hex_matches, key=len)
            decrypted = binascii.unhexlify(hex_str).decode('utf-8', errors='replace')
            return decrypted
        except Exception as e:
            self.log("解密失败: %s" % str(e))
            return raw_html

    # ===================== 框架接口 =====================

    def homeContent(self, filter):
        """首页: 返回分类 + 最新影片列表"""
        result = {}
        result['class'] = self.categories
        try:
            videos = self._scrape_list_page('/cn/new')
            result['list'] = videos
        except Exception as e:
            self.log("首页获取出错: %s" % str(e))
            result['list'] = []
        return result

    def homeVideoContent(self):
        """首页推荐视频"""
        try:
            videos = self._scrape_list_page('/cn/new')
            return {'list': videos}
        except Exception as e:
            self.log("首页视频获取出错: %s" % str(e))
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        """分类内容: 根据 type_id 构建列表页 URL"""
        try:
            page = int(pg) if pg else 1

            # 分页 URL 规则: /cn/{category}/{page}
            if page <= 1:
                path = '/%s' % tid
            else:
                path = '/%s/%d' % (tid, page)

            videos = self._scrape_list_page(path)

            page_count = page + 1 if len(videos) >= 30 else page

            return {
                'list': videos,
                'page': page,
                'pagecount': page_count,
                'limit': len(videos),
                'total': len(videos)
            }
        except Exception as e:
            self.log("分类内容获取出错: %s" % str(e))
            return {'list': []}

    def searchContent(self, key, quick, pg="1"):
        """搜索: /cn/search/{keyword}"""
        try:
            page = int(pg) if pg else 1
            keyword = urllib.parse.quote(key)

            # 搜索 URL 格式
            if page <= 1:
                path = '/cn/search/%s' % keyword
            else:
                path = '/cn/search/%s/%d' % (keyword, page)

            videos = self._scrape_list_page(path)

            page_count = page + 1 if len(videos) >= 30 else page

            return {
                'list': videos,
                'page': page,
                'pagecount': page_count,
                'limit': len(videos),
                'total': len(videos)
            }
        except Exception as e:
            self.log("搜索出错: %s" % str(e))
            return {'list': []}

    def detailContent(self, ids):
        """详情页: 抓取 /cn/{vid} HTML，解密后提取结构化数据"""
        try:
            vid = ids[0]
            url = "%s/cn/%s" % (self.host, urllib.parse.quote(vid))
            self.log("访问详情页: %s" % url)

            rsp = self.fetch(url, headers=self.headers, timeout=self.timeout)
            if not rsp or rsp.status_code != 200:
                self.log("详情页请求失败")
                return {'list': []}

            # 解密 HTML
            html_text = self._decrypt_html(rsp.text)

            title = ''
            plot = ''
            pic = ''
            duration = ''
            barcode = ''
            tags = []

            # ---- 方式1: JSON-LD 结构化数据 ----
            ld_match = re.search(
                r'<script type="application/ld\+json">(.*?)</script>',
                html_text, re.DOTALL
            )
            if ld_match:
                try:
                    ld = json.loads(ld_match.group(1).strip())
                    # 可能是 VideoObject 或 WebSite
                    if ld.get('@type') == 'VideoObject':
                        title = unescape(ld.get('name', ''))
                        plot = unescape(ld.get('description', ''))
                        thumbnails = ld.get('thumbnailUrl', [])
                        if thumbnails:
                            pic = thumbnails[0] if isinstance(thumbnails, list) else thumbnails
                        duration = ld.get('duration', '')
                        tags = ld.get('genre', [])
                except Exception as e:
                    self.log("JSON-LD 解析失败: %s" % str(e))

            # ---- 方式2: 从 video 标签提取 ----
            if not title:
                video_match = re.search(
                    r'<video[^>]*data-src="([^"]*)"[^>]*poster="([^"]*)"[^>]*>',
                    html_text
                )
                if video_match:
                    # poster 就是封面图
                    pic = video_match.group(2)

            # ---- 封面提取: 优先 video poster, 其次 og:image ----
            if not pic:
                video_match = re.search(
                    r'<video[^>]*poster="([^"]+)"',
                    html_text
                )
                if video_match:
                    pic = video_match.group(1)

            if not pic:
                og_img = re.search(
                    r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"',
                    html_text
                )
                if og_img:
                    pic = og_img.group(1)
                    # 如果是站 logo，忽略
                    if 'logo' in pic.lower():
                        pic = ''

            # ---- 标题兜底: 从页面 title 提取 ----
            if not title:
                title_match = re.search(r'<title>(.*?)</title>', html_text, re.DOTALL)
                if title_match:
                    title = unescape(title_match.group(1).strip())
                    # 移除站名后缀
                    title = re.sub(r'\s*-\s*免费高清日本 AV 在线看.*$', '', title)

            # 番号提取
            if title:
                bc_match = re.match(r'^([A-Za-z]+-\d+)', title)
                if bc_match:
                    barcode = bc_match.group(1).upper()

            play_id = vid

            return {
                'list': [{
                    'vod_id': vid,
                    'vod_name': title or barcode or vid,
                    'vod_pic': pic,
                    'type_name': ','.join(tags) if isinstance(tags, list) else str(tags),
                    'vod_remarks': barcode,
                    'vod_content': plot,
                    'vod_play_from': 'JAEVE',
                    'vod_play_url': '第1集$%s' % play_id
                }]
            }
        except Exception as e:
            self.log("详情获取出错: %s" % str(e))
            return {'list': []}

    def playerContent(self, flag, id, vipFlags):
        """播放: 从详情页 HTML 中提取视频地址

        视频格式: mp4 preview，通过代理转发的 URL
        例如: https://mp.kkkppp.top/?url=https://fourhoi.com/{vid}/preview.mp4
        """
        try:
            self.log("获取播放链接: flag=%s, id=%s" % (flag, id))

            vid = id
            url = "%s/cn/%s" % (self.host, urllib.parse.quote(vid))

            rsp = self.fetch(url, headers=self.headers, timeout=self.timeout)
            if not rsp or rsp.status_code != 200:
                self.log("播放页请求失败")
                return {'parse': 0, 'playUrl': '', 'url': ''}

            # 解密 HTML
            html_text = self._decrypt_html(rsp.text)

            # 提取视频地址 (mp4 preview)
            video_url = ''
            
            # 1. 找 video[data-src]
            video_match = re.search(
                r'<video[^>]*data-src="([^"]+)"',
                html_text
            )
            if video_match:
                video_url = video_match.group(1)
            
            # 2. 兜底: 找 mp4 链接
            if not video_url:
                mp4_match = re.search(
                    r'(https?://[^\s"\']+\.mp4[^\s"\']*)',
                    html_text
                )
                if mp4_match:
                    video_url = mp4_match.group(1)

            # 3. 兜底: 找 m3u8
            if not video_url:
                m3u8_match = re.search(
                    r'(https?://[^\s"\']+\.m3u8[^\s"\']*)',
                    html_text
                )
                if m3u8_match:
                    video_url = m3u8_match.group(1)

            if video_url:
                self.log("获取到视频地址: %s" % video_url[:80])
                return {
                    'parse': 0,
                    'playUrl': '',
                    'url': video_url,
                    'header': {
                        'User-Agent': self.headers['User-Agent'],
                        'Referer': self.host + '/'
                    }
                }
            else:
                self.log("未找到视频地址")
                return {'parse': 0, 'playUrl': '', 'url': ''}

        except Exception as e:
            self.log("播放链接获取出错: %s" % str(e))
            return {'parse': 0, 'playUrl': '', 'url': ''}

    # ===================== 内部方法 =====================

    def _scrape_list_page(self, path):
        """抓取列表/搜索/分类页 HTML，解密后解析视频卡片"""
        videos = []
        try:
            url = self.host + path
            self.log("抓取列表页: %s" % url)

            rsp = self.fetch(url, headers=self.headers, timeout=self.timeout)
            if not rsp or rsp.status_code != 200:
                self.log("列表页请求失败: %d" % (rsp.status_code if rsp else -1))
                return videos

            # 解密 HTML
            html_text = self._decrypt_html(rsp.text)
            videos = self._parse_video_cards(html_text)
            self.log("列表页解析到 %d 个影片" % len(videos))
            return videos
        except Exception as e:
            self.log("抓取列表页出错: %s" % str(e))
            return videos

    def _parse_video_cards(self, html_text):
        """从解密后的 HTML 中解析视频卡片

        卡片结构:
        <div class="thumbnail group video-preview-trigger" data-preview-bound="true">
          <div class="relative aspect-w-16 aspect-h-9 rounded overflow-hidden shadow-lg">
            <a href="/cn/{vid}" class="block w-full h-full">
              <img src="https://cache-2608.sgvafs.com/base/{base64}.cache"
                   alt="{title}" loading="lazy"
                   class="w-full h-full object-cover">
              <video loop muted playsinline class="preview hidden"
                     data-src="https://mp.kkkppp.top/?url=https://fourhoi.com/{vid}/preview.mp4"
                     poster="{cover_url}" data-error-handled="true">
              </video>
            </a>
          </div>
          <div class="video-title">{title}</div>
          <div class="video-meta">
            <span class="duration">{duration}</span>
            <span class="views">{views}</span>
          </div>
        </div>
        """
        videos = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_text, 'html.parser')

            # 视频卡片容器: .thumbnail.group.video-preview-trigger
            cards = soup.find_all('div', class_=re.compile(r'\bthumbnail\b'))
            # 或者找包含 video[data-src] 的容器
            if not cards:
                cards = soup.find_all('div', class_=re.compile(r'\bvideo-preview-trigger\b'))

            for card in cards:
                # 找视频链接
                link = card.find('a', href=re.compile(r'^/cn/'))
                if not link:
                    continue

                vid = link.get('href', '').replace('/cn/', '')
                if not vid:
                    continue

                # 提取标题
                title = ''
                # 1. 从 alt 属性 (img 标签)
                img = card.find('img')
                if img:
                    title = img.get('alt', '')
                # 2. 从 .video-title
                if not title:
                    title_div = card.find('div', class_='video-title')
                    if title_div:
                        title = title_div.get_text(strip=True)
                # 3. 兜底: 从 a 标签文本
                if not title:
                    title = link.get_text(strip=True)

                if not title:
                    title = vid

                # 提取封面图
                pic = ''
                if img:
                    pic = img.get('src', '')
                if not pic:
                    # 从 video poster
                    video = card.find('video')
                    if video:
                        pic = video.get('poster', '')

                # 提取时长
                duration = ''
                duration_span = card.find('span', class_='duration')
                if duration_span:
                    duration = duration_span.get_text(strip=True)

                # 提取观看次数
                views = ''
                views_span = card.find('span', class_='views')
                if views_span:
                    views = views_span.get_text(strip=True)

                # 提取标记 (中文字幕/无码等)
                badge = ''
                badge_span = card.find('span', class_=re.compile(r'\b(chinese|uncensored|subtitle)\b'))
                if badge_span:
                    badge = badge_span.get_text(strip=True)

                # 从标题提取番号
                barcode = ''
                bc_match = re.match(r'^([A-Za-z]+-\d+)', title)
                if bc_match:
                    barcode = bc_match.group(1).upper()

                # 构建 remark: 番号 + 时长
                remark_parts = []
                if barcode:
                    remark_parts.append(barcode)
                if duration:
                    remark_parts.append(duration)
                if views:
                    remark_parts.append(views)

                videos.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': ' | '.join(remark_parts) if remark_parts else '',
                })

            return videos
        except Exception as e:
            self.log("解析影片卡片出错: %s" % str(e))
            return videos

    # ===================== 框架接口 =====================

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def log(self, message):
        print("[JAEVE] %s" % message)

    def fetch(self, url, headers=None, method='GET', data=None, timeout=10):
        try:
            if headers is None:
                headers = self.headers
            if method == 'GET':
                response = requests.get(
                    url, headers=headers, timeout=timeout,
                    verify=False, allow_redirects=True
                )
            else:
                response = requests.post(
                    url, headers=headers, data=data, timeout=timeout,
                    verify=False, allow_redirects=True
                )
            return response
        except Exception as e:
            self.log("网络请求失败: %s, 错误: %s" % (url, str(e)))
            return None


if __name__ == '__main__':
    # 独立测试入口
    spider = Spider()
    spider.init()

    print("=" * 60)
    print("测试1: 首页内容")
    print("=" * 60)
    home = spider.homeContent(False)
    print("分类数: %d" % len(home.get('class', [])))
    print("影片数: %d" % len(home.get('list', [])))
    if home.get('list'):
        v = home['list'][0]
        print("第一个影片: id=%s, name=%s" % (v['vod_id'], v['vod_name'][:50]))
        print("  pic=%s" % v.get('vod_pic', '')[:80])
        print("  remark=%s" % v.get('vod_remarks', ''))

    print("\n" + "=" * 60)
    print("测试2: 搜索 SSIS")
    print("=" * 60)
    search = spider.searchContent('SSIS', False, '1')
    print("搜索结果数: %d" % len(search.get('list', [])))
    if search.get('list'):
        v = search['list'][0]
        print("第一个结果: id=%s, name=%s" % (v['vod_id'], v['vod_name'][:60]))
        print("  pic=%s" % v.get('vod_pic', '')[:80])
        print("  remark=%s" % v.get('vod_remarks', ''))

    print("\n" + "=" * 60)
    print("测试3: 分类内容 (中文字幕)")
    print("=" * 60)
    cat = spider.categoryContent('cn/chinese-subtitle', '1', False, '')
    print("分类结果数: %d" % len(cat.get('list', [])))
    if cat.get('list'):
        v = cat['list'][0]
        print("第一个: id=%s, name=%s" % (v['vod_id'], v['vod_name'][:60]))

    print("\n" + "=" * 60)
    print("测试4: 详情页")
    print("=" * 60)
    if home.get('list'):
        test_vid = home['list'][0]['vod_id']
        print("测试 vid: %s" % test_vid)
        detail = spider.detailContent([test_vid])
        if detail.get('list'):
            d = detail['list'][0]
            print("标题: %s" % d.get('vod_name', '')[:60])
            print("番号: %s" % d.get('vod_remarks', ''))
            print("封面: %s" % d.get('vod_pic', '')[:80])
            print("简介: %s" % d.get('vod_content', '')[:100])
            print("播放源: %s" % d.get('vod_play_from', ''))
            print("播放ID: %s" % d.get('vod_play_url', ''))

        print("\n" + "=" * 60)
        print("测试5: 播放链接")
        print("=" * 60)
        play = spider.playerContent('JAEVE', test_vid, '')
        print("parse: %s" % play.get('parse', ''))
        print("url: %s" % play.get('url', '')[:100])

    print("\n" + "=" * 60)
    print("测试6: 解密功能")
    print("=" * 60)
    # 测试解密
    test_hex = "3c21444f43545950452068746d6c3e"
    test_decoded = spider._decrypt_html('"' + test_hex + '"')
    print("解密测试: %s" % test_decoded[:50])
