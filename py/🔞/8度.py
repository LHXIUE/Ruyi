# -*- coding: utf-8 -*-
#!/usr/bin/python
# TVBox Python Spider for badyi.cc
# 站点: 八度影院 (badyi.cc)
# 支持: 分类栏 / 子分类筛选 / 搜索 / 详情 / 播放

import sys
import json
import re

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def getName(self):
        return "八度影院"

    def init(self, extend=""):
        print("===== badyi.cc init ===== {0}".format(extend))
        pass

    # ======================== 首页 ========================

    def homeContent(self, filter):
        result = {}
        # 主分类列表 (导航栏分类)
        cateManual = {
            "后入": "c11",
            "玩偶姐姐": "c8",
            "蝴蝶逼": "c19",
            "蜜桃影像传媒": "c58",
            "主播": "c41",
            "饼干姐姐": "c7",
            "学妹": "c66",
            "精东影业": "c47",
            "姐弟": "c65",
            "情趣装扮": "c97",
            "cosplay": "c108",
            "巨乳": "c76",
            "勾引": "c85",
            "3p": "c90",
            "口交": "c12",
            "骑乘": "c16",
            "女同": "c51",
            "出轨": "c139",
            "爱豆传媒": "c45",
            "无码": "c110",
            "性奴": "c102",
            "大学生": "c145",
            "福利姬": "c178",
            "动漫": "c154",
            "内射": "c180",
            "反差婊": "c2",
            "swag": "c107",
            "p站": "c109",
            "星空无限传媒": "c111",
            "小宵虎南": "c186",
            "苏畅": "c81",
            "苏小涵": "c82",
            "懒懒猪": "c74",
            "小水水": "c71"
        }
        classes = []
        for k in cateManual:
            classes.append({
                'type_name': k,
                'type_id': cateManual[k]
            })
        result['class'] = classes
        if filter:
            result['filters'] = self.config['filter']
        return result

    def homeVideoContent(self):
        # 首页热门视频 - 直接解析首页HTML
        url = self.siteUrl + '/'
        rsp = self.fetch(url, headers=self.headers)
        root = self.html(rsp.text)
        aList = root.xpath("//a[contains(@class,'nav-art-card') and contains(@href,'/video/')]")
        videos = []
        for a in aList:
            try:
                href = a.xpath('./@href')[0]
                # 跳过广告卡片
                if 'adgo' in href or '/ad' in href:
                    continue
                title = a.xpath('.//h2/text()')
                if not title:
                    title = a.xpath('.//h2//text()')
                if not title:
                    continue
                title = title[0].strip()
                pic = a.xpath('.//img/@src')
                pic = pic[0] if pic else ''
                if pic and not pic.startswith('http'):
                    pic = self.siteUrl + pic
                date = a.xpath('.//span[contains(@class,"nav-card-date")]/text()')
                date = date[0].strip() if date else ''
                cat = a.xpath('.//span[contains(@class,"nav-card-cat")]/text()')
                cat = cat[0].strip() if cat else ''
                remarks = date or cat
                vid = href.replace('/video/', '').strip('/')
                videos.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': remarks
                })
            except:
                continue
        result = {'list': videos}
        return result

    # ======================== 分类页 ========================

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        page = int(pg) if pg else 1
        # 如果有子分类筛选, 使用子分类的tid
        if extend and 'tag' in extend and extend['tag']:
            tid = extend['tag']
        # 构造分类页URL
        if page <= 1:
            url = '{0}/{1}'.format(self.siteUrl, tid)
        else:
            url = '{0}/{1}/page/{2}'.format(self.siteUrl, tid, page)
        rsp = self.fetch(url, headers=self.headers)
        root = self.html(rsp.text)
        aList = root.xpath("//a[contains(@class,'nav-art-card') and contains(@href,'/video/')]")
        videos = []
        for a in aList:
            try:
                href = a.xpath('./@href')[0]
                if 'adgo' in href or '/ad' in href:
                    continue
                title = a.xpath('.//h2/text()')
                if not title:
                    title = a.xpath('.//h2//text()')
                if not title:
                    continue
                title = title[0].strip()
                pic = a.xpath('.//img/@src')
                pic = pic[0] if pic else ''
                if pic and not pic.startswith('http'):
                    pic = self.siteUrl + pic
                date = a.xpath('.//span[contains(@class,"nav-card-date")]/text()')
                date = date[0].strip() if date else ''
                cat = a.xpath('.//span[contains(@class,"nav-card-cat")]/text()')
                cat = cat[0].strip() if cat else ''
                remarks = date or cat
                vid = href.replace('/video/', '').strip('/')
                videos.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': remarks
                })
            except:
                continue
        # 解析分页信息
        pageCount = self._parsePageCount(root)
        result['list'] = videos
        result['page'] = page
        result['pagecount'] = pageCount
        result['limit'] = len(videos)
        result['total'] = pageCount * len(videos)
        return result

    def _parsePageCount(self, root):
        """从分页信息中解析总页数"""
        try:
            pgInfo = root.xpath("//span[contains(@class,'nav-pg-info')]/text()")
            if pgInfo:
                m = re.search(r'(\d+)\s*/\s*(\d+)', pgInfo[0])
                if m:
                    return int(m.group(2))
        except:
            pass
        return 9999

    # ======================== 详情页 ========================

    def detailContent(self, array):
        tid = array[0]
        url = '{0}/video/{1}'.format(self.siteUrl, tid)
        try:
            rsp = self.fetch(url, headers=self.headers)
            html_text = rsp.text
            root = self.html(html_text)
        except:
            # 请求失败也要返回基本结构, 避免TVBox一直转圈
            vod = {
                'vod_id': tid,
                'vod_name': '加载失败',
                'vod_pic': '',
                'type_name': '',
                'vod_year': '',
                'vod_area': '',
                'vod_remarks': '',
                'vod_actor': '',
                'vod_director': '',
                'vod_content': '页面加载失败, 请稍后重试',
                'vod_play_from': '八度影院',
                'vod_play_url': '播放$' + tid
            }
            return {'list': [vod]}

        vod = {
            'vod_id': tid,
            'vod_name': '',
            'vod_pic': '',
            'type_name': '',
            'vod_year': '',
            'vod_area': '',
            'vod_remarks': '',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': '',
            'vod_play_from': '八度影院',
            'vod_play_url': '播放$' + tid
        }

        # 1. 标题: 优先 h1, 其次 og:title, 最后 meta title
        try:
            h1 = root.xpath('//h1//text()')
            if h1:
                vod['vod_name'] = ''.join(h1).strip()
        except:
            pass
        if not vod['vod_name']:
            try:
                og_title = root.xpath('//meta[@property="og:title"]/@content')
                if og_title:
                    vod['vod_name'] = og_title[0].strip()
            except:
                pass
        if not vod['vod_name']:
            try:
                title_tag = root.xpath('//title/text()')
                if title_tag:
                    vod['vod_name'] = title_tag[0].split('|')[0].strip()
            except:
                pass

        # 2. 封面图: 优先 data-poster, 其次 og:image
        try:
            poster = root.xpath('//*[@id="watch-player"]/@data-poster')
            if poster:
                vod['vod_pic'] = poster[0]
        except:
            pass
        if not vod['vod_pic']:
            try:
                og_img = root.xpath('//meta[@property="og:image"]/@content')
                if og_img:
                    vod['vod_pic'] = og_img[0]
            except:
                pass

        # 3. 分类: 从 wm-cat 提取
        try:
            cats = root.xpath('//span[contains(@class,"wm-cat")]/text()')
            if cats:
                vod['type_name'] = cats[0].strip()
        except:
            pass

        # 4. 年份和日期: 从 time 标签提取
        try:
            date_text = root.xpath('//time/@datetime')
            if date_text:
                dt = date_text[0]
                if len(dt) >= 4:
                    vod['vod_year'] = dt[:4]
                if len(dt) >= 10:
                    vod['vod_remarks'] = dt[:10]
        except:
            pass

        # 5. 标签: 从 article-tag 提取
        tag_str = ''
        try:
            tags = root.xpath('//span[contains(@class,"article-tag")]/text()')
            if tags:
                tag_str = ' '.join([t.strip() for t in tags if t.strip()])
        except:
            pass

        # 6. 简介: 优先 meta description, 拼接标签
        try:
            desc = root.xpath('//meta[@name="description"]/@content')
            if desc:
                vod['vod_content'] = desc[0].strip()
        except:
            pass
        if tag_str:
            if vod['vod_content']:
                vod['vod_content'] += '\n标签: ' + tag_str
            else:
                vod['vod_content'] = '标签: ' + tag_str

        # 7. 播放信息: 用视频ID作为播放标识, playerContent 时再获取真实地址
        #    这样 detailContent 不需要额外网络请求, 加载更快
        vod['vod_play_from'] = '八度影院'
        vod['vod_play_url'] = '播放$' + tid

        return {'list': [vod]}

    def _getPlayUrl(self, vid):
        """通过 /api/video.php?id=XXXX 获取有效的 m3u8 播放地址"""
        # 方式1: 调用 API
        try:
            api_url = '{0}/api/video.php?id={1}'.format(self.siteUrl, vid)
            api_headers = dict(self.headers)
            api_headers['Referer'] = '{0}/video/{1}'.format(self.siteUrl, vid)
            rsp = self.fetch(api_url, headers=api_headers)
            jo = json.loads(rsp.text)
            if jo.get('ok') and jo.get('url'):
                return jo['url']
        except:
            pass

        # 方式2: 从详情页 JSON-LD 提取 contentUrl 作为备用
        try:
            detail_url = '{0}/video/{1}'.format(self.siteUrl, vid)
            rsp = self.fetch(detail_url, headers=self.headers)
            root = self.html(rsp.text)
            ld_scripts = root.xpath('//script[@type="application/ld+json"]/text()')
            for ld_text in ld_scripts:
                if ld_text.strip():
                    ld = json.loads(ld_text.strip())
                    graph = ld.get('@graph', []) if isinstance(ld, dict) else []
                    if isinstance(ld, dict) and not graph:
                        graph = [ld]
                    for item in graph:
                        if isinstance(item, dict) and item.get('@type') == 'VideoObject':
                            url = item.get('contentUrl', '')
                            if url and '.m3u8' in url:
                                return url
        except:
            pass

        # 方式3: 正则搜索 m3u8 链接
        try:
            detail_url = '{0}/video/{1}'.format(self.siteUrl, vid)
            rsp = self.fetch(detail_url, headers=self.headers)
            m = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', rsp.text)
            if m:
                return m.group(1)
        except:
            pass

        return ''

    # ======================== 搜索 ========================

    def searchContent(self, key, quick):
        result = {}
        url = '{0}/api/search.php?q={1}&page=1&per=20'.format(self.siteUrl, key)
        rsp = self.fetch(url, headers=self.headers)
        jo = json.loads(rsp.text)
        jArray = []
        if jo.get('ok') and int(jo.get('total', 0)) > 0:
            for article in jo.get('articles', []):
                pic = article.get('img', '') or article.get('thumb', '')
                if pic and not pic.startswith('http'):
                    pic = self.siteUrl + pic
                vid = str(article.get('id', ''))
                if not vid:
                    url_path = article.get('url', '')
                    vid = url_path.replace('/video/', '').strip('/')
                jArray.append({
                    'vod_id': vid,
                    'vod_name': article.get('title', ''),
                    'vod_pic': pic,
                    'vod_remarks': article.get('date', '')
                })
        result = {'list': jArray}
        return result

    # ======================== 播放 ========================

    def playerContent(self, flag, id, vipFlags):
        result = {}
        # id 是视频ID时, 通过 /api/video.php 获取真实 m3u8 地址
        if id.startswith('http'):
            play_url = id
        else:
            play_url = self._getPlayUrl(id)

        result['parse'] = 0
        result['playUrl'] = ''
        result['url'] = play_url
        # 请求头: Referer 设为视频页面, 确保 CloudFront 接受
        play_headers = dict(self.headers)
        if not id.startswith('http'):
            play_headers['Referer'] = '{0}/video/{1}'.format(self.siteUrl, id)
        result['header'] = json.dumps(play_headers)
        return result

    # ======================== 其他 ========================

    def isVideoFormat(self, url):
        if not url:
            return False
        if '.m3u8' in url or '.mp4' in url or '.flv' in url:
            return True
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return [200, "video/MP2T", "", ""]

    # ======================== 配置 ========================

    siteUrl = 'https://badyi.cc'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://badyi.cc/',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
    }

    # 子分类筛选配置
    # 每个主分类都可以按标签筛选, 选择标签后跳转到对应分类页
    config = {
        "filter": {
            "c11": [{"key": "tag", "name": "子分类", "value": [
                {"n": "全部", "v": ""},
                {"n": "无码", "v": "c110"},
                {"n": "中文字幕", "v": "c110"},
                {"n": "巨乳", "v": "c76"},
                {"n": "口交", "v": "c12"},
                {"n": "骑乘", "v": "c16"},
                {"n": "3p", "v": "c90"},
                {"n": "内射", "v": "c180"},
                {"n": "高潮", "v": "c162"},
                {"n": "cosplay", "v": "c108"},
                {"n": "大学生", "v": "c145"},
                {"n": "反差婊", "v": "c2"},
                {"n": "性奴", "v": "c102"},
                {"n": "女同", "v": "c51"},
                {"n": "出轨", "v": "c139"},
                {"n": "福利姬", "v": "c178"},
                {"n": "动漫", "v": "c154"},
                {"n": "勾引", "v": "c85"},
                {"n": "重口味", "v": "c130"},
                {"n": "乱交群p", "v": "c52"}
            ]}],
            "c8": [{"key": "tag", "name": "子分类", "value": [
                {"n": "全部", "v": ""},
                {"n": "网黄", "v": "c8"},
                {"n": "反差婊", "v": "c2"},
                {"n": "福利姬", "v": "c178"},
                {"n": "巨乳", "v": "c76"},
                {"n": "cosplay", "v": "c108"},
                {"n": "情趣装扮", "v": "c97"},
                {"n": "勾引", "v": "c85"},
                {"n": "口交", "v": "c12"},
                {"n": "骑乘", "v": "c16"},
                {"n": "3p", "v": "c90"},
                {"n": "内射", "v": "c180"}
            ]}],
            "c19": [{"key": "tag", "name": "子分类", "value": [
                {"n": "全部", "v": ""},
                {"n": "巨乳", "v": "c76"},
                {"n": "口交", "v": "c12"},
                {"n": "骑乘", "v": "c16"},
                {"n": "高潮", "v": "c162"},
                {"n": "内射", "v": "c180"},
                {"n": "3p", "v": "c90"},
                {"n": "勾引", "v": "c85"}
            ]}],
            "c58": [{"key": "tag", "name": "子分类", "value": [
                {"n": "全部", "v": ""},
                {"n": "爱豆传媒", "v": "c45"},
                {"n": "星空无限传媒", "v": "c111"},
                {"n": "精东影业", "v": "c47"},
                {"n": "无码", "v": "c110"},
                {"n": "巨乳", "v": "c76"},
                {"n": "出轨", "v": "c139"},
                {"n": "大学生", "v": "c145"}
            ]}],
            "c41": [{"key": "tag", "name": "子分类", "value": [
                {"n": "全部", "v": ""},
                {"n": "反差婊", "v": "c2"},
                {"n": "福利姬", "v": "c178"},
                {"n": "cosplay", "v": "c108"},
                {"n": "情趣装扮", "v": "c97"},
                {"n": "巨乳", "v": "c76"},
                {"n": "勾引", "v": "c85"},
                {"n": "大学生", "v": "c145"}
            ]}],
            "c7": [{"key": "tag", "name": "子分类", "value": [
                {"n": "全部", "v": ""},
                {"n": "网黄", "v": "c8"},
                {"n": "cosplay", "v": "c108"},
                {"n": "情趣装扮", "v": "c97"},
                {"n": "巨乳", "v": "c76"},
                {"n": "勾引", "v": "c85"}
            ]}],
            "c66": [{"key": "tag", "name": "子分类", "value": [
                {"n": "全部", "v": ""},
                {"n": "大学生", "v": "c145"},
                {"n": "十八岁", "v": "c193"},
                {"n": "福利姬", "v": "c178"},
                {"n": "反差婊", "v": "c2"},
                {"n": "cosplay", "v": "c108"},
                {"n": "巨乳", "v": "c76"}
            ]}],
            "c47": [{"key": "tag", "name": "子分类", "value": [
                {"n": "全部", "v": ""},
                {"n": "无码", "v": "c110"},
                {"n": "中文字幕", "v": "c110"},
                {"n": "巨乳", "v": "c76"},
                {"n": "口交", "v": "c12"},
                {"n": "骑乘", "v": "c16"},
                {"n": "3p", "v": "c90"},
                {"n": "内射", "v": "c180"},
                {"n": "高潮", "v": "c162"}
            ]}],
            "c65": [{"key": "tag", "name": "子分类", "value": [
                {"n": "全部", "v": ""},
                {"n": "出轨", "v": "c139"},
                {"n": "小三", "v": "c182"},
                {"n": "反差婊", "v": "c2"},
                {"n": "勾引", "v": "c85"},
                {"n": "巨乳", "v": "c76"}
            ]}],
            "c97": [{"key": "tag", "name": "子分类", "value": [
                {"n": "全部", "v": ""},
                {"n": "cosplay", "v": "c108"},
                {"n": "空姐", "v": "c181"},
                {"n": "眼镜娘", "v": "c196"},
                {"n": "圣诞", "v": "c147"},
                {"n": "元旦", "v": "c206"}
            ]}],
            "c108": [{"key": "tag", "name": "子分类", "value": [
                {"n": "全部", "v": ""},
                {"n": "情趣装扮", "v": "c97"},
                {"n": "眼镜娘", "v": "c196"},
                {"n": "空姐", "v": "c181"},
                {"n": "福利姬", "v": "c178"}
            ]}],
            "c76": [{"key": "tag", "name": "子分类", "value": [
                {"n": "全部", "v": ""},
                {"n": "无码", "v": "c110"},
                {"n": "后入", "v": "c11"},
                {"n": "口交", "v": "c12"},
                {"n": "骑乘", "v": "c16"},
                {"n": "3p", "v": "c90"}
            ]}],
            "c110": [{"key": "tag", "name": "子分类", "value": [
                {"n": "全部", "v": ""},
                {"n": "后入", "v": "c11"},
                {"n": "巨乳", "v": "c76"},
                {"n": "口交", "v": "c12"},
                {"n": "骑乘", "v": "c16"},
                {"n": "3p", "v": "c90"},
                {"n": "内射", "v": "c180"}
            ]}]
        }
    }
