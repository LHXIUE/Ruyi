# -*- coding: utf-8 -*-
"""
泡泡屋 (ppw666.com -> tlobcnv.com) Python Spider
兼容 FongMi/TV (T3) 与 WebHomeTV / PeekPro (T4)

站点架构：
- 门户: http://ppw666.com/ (JS 跳转)
- 前端/API: https://tlobcnv.com (Next.js SPA + REST API)
- 封面CDN: https://mvimg.kaibmy.com (AES-128-CBC 加密, TVBox 无法显示)
- 播放CDN: https://idx.jvnmtr.cn (m3u8) / https://segs.jvnmtr.cn (TS分片+AES key)
- 播放器: xgplayer 3.0.26, HLS + AES-128 逐分片加密 (标准 HLS, TVBox 可直接播放)

认证流程：
- POST /api/app/v1/auth/register {"deviceFingerprint":"web:Linux:zh-CN"} -> JWT token
- 所有业务接口需 Authorization: Bearer <token>
- Token 有效期 2 小时

播放原理：
- playPath 形如 /日期/{hash}/720/{fileid}
- m3u8 URL = https://idx.jvnmtr.cn + playPath去掉最后一段 + /index.m3u8
- 直接拼完整 playPath + /index.m3u8 会 404 -> 黑屏
- m3u8 内 #EXT-X-KEY:METHOD=AES-128,URI="/keys/encX.key" (相对路径, 标准 HLS)
- key 无鉴权, TVBox 播放器自动获取并解密

封面图：
- coverPath + ".log" 后缀返回 AES-128-CBC 加密数据
- key: 88ce35562a6f085b53a00145444c445f, IV: d005d14d7ce6312ae54527a659be2c55
- TVBox 无法解密, 返回空字符串

会员机制：
- 普通视频: 全部免费, 无 VIP 限制
- 合集: 需 unlockCoins 解锁, 但 freeEpisodes (前N集) 免费
- 合集 episodes 端点: /collections/{id}/episodes, 每集有 free 标记和 playPath
"""
import sys
import re
import json
import time

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
        def post(self, url, headers=None, data=None, **kw):
            kw.pop('timeout', None)
            r = self._session.post(url, headers=headers, data=data, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


class Spider(Spider):
    HOST = 'https://tlobcnv.com'
    API = 'https://tlobcnv.com/api/app/v1'
    IMG_HOST = 'https://mvimg.kaibmy.com'
    M3U8_HOST = 'https://idx.jvnmtr.cn'

    def getName(self):
        return "泡泡屋"

    def init(self, extend=''):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.host = self.HOST
        self.header = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        self._token = ''
        self._token_time = 0
        # playPath 缓存：vid -> playPath，避免播放时重复请求详情页
        self._play_cache = {}
        # 合集 episodes 缓存：collection_id -> [episode, ...]
        self._ep_cache = {}

    # ========== 认证 ==========

    def _ensure_token(self):
        """确保 token 有效，过期自动重新注册"""
        if self._token and (time.time() - self._token_time < 7000):
            return self._token
        try:
            import requests as rq
            url = self.API + '/auth/register'
            body = json.dumps({'deviceFingerprint': 'web:Linux:zh-CN'})
            rsp = rq.post(url, headers={**self.header, 'Content-Type': 'application/json'},
                          data=body, timeout=15)
            data = rsp.json()
            if data.get('code') == 0:
                self._token = data['data']['token']
                self._token_time = time.time()
                return self._token
        except Exception:
            pass
        return self._token

    def _auth_header(self):
        """返回带 Bearer token 的请求头"""
        token = self._ensure_token()
        h = dict(self.header)
        if token:
            h['Authorization'] = 'Bearer ' + token
        return h

    def _api_get(self, path, params=None):
        """GET 请求 API，自动带 token，失败重试一次"""
        url = self.API + path
        headers = self._auth_header()
        for attempt in range(2):
            try:
                rsp = self.fetch(url, headers=headers, timeout=15)
                data = rsp.json()
                # token 过期时重新注册
                if data.get('code') == 1001 and attempt == 0:
                    self._token = ''
                    self._token_time = 0
                    headers = self._auth_header()
                    continue
                return data
            except Exception:
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                return {}
        return {}

    # ========== 封面图 ==========

    def _cover_url(self, cover_path):
        """
        拼接封面图完整 URL。
        封面图是 AES-128-CBC 加密的，TVBox 无法直接显示。
        返回 .log URL，部分 TVBox 版本会显示占位图。
        """
        if not cover_path:
            return ''
        if cover_path.startswith('http'):
            # 合集封面可能是完整 URL (ncp.maimaitom.com)
            return cover_path
        # 普通视频封面：mvimg.kaibmy.com + coverPath + .log
        return self.IMG_HOST + cover_path + '.log'

    # ========== m3u8 URL 构建 ==========

    def _build_m3u8_url(self, play_path):
        """
        构建 m3u8 直链 URL。
        playPath 形如 /20260824/{hash}/720/{fileid}
        最后一段 fileid 不参与 m3u8 URL，去掉后才返回 200。
        直接拼完整 playPath + /index.m3u8 会 404 -> 播放黑屏。
        """
        if not play_path:
            return ''
        # 去掉最后一段（fileid），保留目录部分
        m3u8_dir = play_path.rsplit('/', 1)[0] if play_path.count('/') >= 3 else play_path
        return self.M3U8_HOST + m3u8_dir + '/index.m3u8'

    # ========== 视频对象转换 ==========

    def _to_vod(self, item):
        """将 API 视频对象转为 TVBox vod 格式"""
        vod = {
            'vod_id': str(item.get('id', '')),
            'vod_name': item.get('title', ''),
            'vod_pic': self._cover_url(item.get('coverPath', '')),
            'vod_remarks': item.get('duration', ''),
        }
        return vod

    def _to_collection_vod(self, item):
        """将合集对象转为 TVBox vod 格式"""
        episodes = item.get('episodes', 0)
        free_eps = item.get('freeEpisodes', 0)
        unlock_coins = item.get('unlockCoins', 0)
        remark = f'{episodes}集'
        if free_eps > 0:
            remark += f'(免费{free_eps}集)'
        if unlock_coins == 0:
            remark = f'{episodes}集(免费)'
        vod = {
            'vod_id': 'col_' + str(item.get('id', '')),
            'vod_name': item.get('title', ''),
            'vod_pic': self._cover_url(item.get('coverPath', '')),
            'vod_remarks': remark,
        }
        return vod

    # ========== 首页 ==========

    def homeContent(self, filter):
        """首页分类栏 + 筛选器"""
        from urllib.parse import quote
        classes = []
        filters = {}

        # 固定分类
        classes.append({'type_id': 'all', 'type_name': '最新'})
        classes.append({'type_id': 'hot', 'type_name': '热门'})
        classes.append({'type_id': 'collections', 'type_name': '合集'})

        # 排序筛选器
        sort_filter = {
            'key': 'sort',
            'name': '排序',
            'value': [
                {'n': '最新', 'v': 'time'},
                {'n': '热门', 'v': 'hot'},
            ]
        }
        filters['all'] = [sort_filter]
        filters['hot'] = [sort_filter]
        filters['collections'] = []

        # 获取分类树
        data = self._api_get('/videos/categories')
        cats = (data.get('data') or {}).get('list', [])

        # 只添加主分类，不添加子分类
        # 原因：API 不支持子分类服务端筛选，客户端只过滤当前页 30 条
        # 很多子分类在前几页没有视频，导致空列表
        for cat in cats:
            type_id = cat.get('name', '')
            type_name = cat.get('name', '')
            classes.append({'type_id': type_id, 'type_name': type_name})
            filters[type_id] = [sort_filter]

        result = {'class': classes, 'filters': filters}
        return result

    def homeVideoContent(self):
        """首页推荐视频"""
        result = {'list': []}
        try:
            # 优先获取今日更新
            data = self._api_get('/home/today')
            items = (data.get('data') or {}).get('list', [])
            if not items:
                data = self._api_get('/videos?sort=time&page=1&pageSize=20')
                items = (data.get('data') or {}).get('list', [])
            result['list'] = [self._to_vod(v) for v in items]
        except Exception:
            pass
        return result

    # ========== 分类列表 ==========

    def categoryContent(self, tid, pg, filter, ext):
        """分类视频列表"""
        from urllib.parse import quote
        page = int(pg) if pg else 1
        if page < 1:
            page = 1

        # 解析筛选参数
        sort = 'time'
        if ext:
            if isinstance(ext, dict):
                sort = ext.get('sort', 'time') or 'time'
            elif isinstance(ext, str):
                try:
                    params = json.loads(ext)
                    sort = params.get('sort', 'time') or 'time'
                except Exception:
                    pass
        if sort not in ('time', 'hot'):
            sort = 'time'

        # 合集分类
        if tid == 'collections':
            data = self._api_get(f'/collections?page={page}&pageSize=30')
            d = data.get('data') or {}
            videos = [self._to_collection_vod(v) for v in d.get('list', [])]
            total = d.get('total', 0)
            page_size = 30
            page_count = max(1, (total + page_size - 1) // page_size) if total else 1
            return {
                'list': videos,
                'page': page,
                'pagecount': page_count,
                'limit': page_size,
                'total': total,
            }

        # 热门分类
        if tid == 'hot':
            data = self._api_get(f'/home/hot?sort=plays&page={page}&pageSize=30')
            d = data.get('data') or {}
            videos = [self._to_vod(v) for v in d.get('list', [])]
            total = d.get('total', 0)
            page_size = 30
            page_count = max(1, (total + page_size - 1) // page_size) if total else 1
            return {
                'list': videos,
                'page': page,
                'pagecount': page_count,
                'limit': page_size,
                'total': total,
            }

        # 普通分类
        params_list = [f'sort={sort}', f'page={page}', 'pageSize=30']
        if tid and tid != 'all':
            params_list.insert(0, f'category={quote(tid)}')

        url_path = '/videos?' + '&'.join(params_list)
        data = self._api_get(url_path)

        d = data.get('data') or {}
        videos = [self._to_vod(v) for v in d.get('list', [])]

        total = d.get('total', 0)
        page_size = d.get('pageSize', 30)
        page_count = max(1, (total + page_size - 1) // page_size) if total else 1

        return {
            'list': videos,
            'page': page,
            'pagecount': page_count,
            'limit': page_size,
            'total': total,
        }

    # ========== 详情页 ==========

    def detailContent(self, ids):
        """视频详情"""
        vid = str(ids[0]) if ids else ''
        if not vid:
            return {}

        # 合集详情
        if vid.startswith('col_'):
            return self._collection_detail(vid[4:])

        # 普通视频详情
        data = self._api_get(f'/videos/{vid}')
        d = data.get('data') or {}
        if not d:
            return {}

        play_path = d.get('playPath', '')
        if play_path:
            self._play_cache[vid] = play_path

        vod = {
            'vod_id': vid,
            'vod_name': d.get('title', ''),
            'vod_pic': self._cover_url(d.get('coverPath', '')),
            'vod_year': '',
            'vod_area': d.get('category', ''),
            'vod_remarks': d.get('duration', ''),
            'vod_tags': d.get('tag', ''),
            'vod_play_from': '泡泡屋',
            'vod_play_url': '播放$' + vid,
        }

        # 尝试获取推荐
        try:
            rec_data = self._api_get(f'/videos/{vid}/recommend?limit=6')
            rec_items = (rec_data.get('data') or {}).get('list', [])
            if rec_items:
                vod['vod_content'] = '相关推荐：' + '、'.join(
                    v.get('title', '')[:20] for v in rec_items[:3]
                )
        except Exception:
            pass

        return {'list': [vod]}

    def _collection_detail(self, cid):
        """合集详情 - 展示免费剧集列表"""
        data = self._api_get(f'/collections/{cid}')
        d = data.get('data') or {}
        if not d:
            return {}

        # 获取剧集列表
        ep_data = self._api_get(f'/collections/{cid}/episodes')
        episodes = (ep_data.get('data') or {}).get('list', [])
        self._ep_cache[cid] = episodes

        # 构建播放列表：免费剧集
        free_eps = [ep for ep in episodes if ep.get('free')]
        if not free_eps:
            # 如果没有标记免费的，取前10集
            free_eps = episodes[:10]

        play_names = []
        for ep in free_eps:
            idx = ep.get('index', 0)
            title = ep.get('title', f'第{idx}集')
            ep_id = f'col_{cid}_{idx}'
            play_names.append(f'{title}${ep_id}')

        vod = {
            'vod_id': 'col_' + cid,
            'vod_name': d.get('title', ''),
            'vod_pic': self._cover_url(d.get('coverPath', '')),
            'vod_year': d.get('releaseDate', ''),
            'vod_area': '',
            'vod_remarks': f'{d.get("episodes", 0)}集(免费{len(free_eps)}集)',
            'vod_content': d.get('intro', ''),
            'vod_play_from': '免费剧集',
            'vod_play_url': '#'.join(play_names),
        }

        return {'list': [vod]}

    # ========== 播放解析 ==========

    def playerContent(self, flag, id, vipFlags):
        """播放解析 - 返回 m3u8 直链"""
        if not id:
            return {'parse': 1, 'playUrl': '', 'url': ''}

        # 如果 id 以 $ 分隔，取后面的部分
        if '$' in id:
            parts = id.split('$')
            if len(parts) == 2:
                id = parts[1]

        vid = str(id)

        # 合集剧集播放
        if vid.startswith('col_'):
            return self._collection_play(vid)

        # 普通视频播放
        # 优先从缓存取 playPath
        play_path = self._play_cache.get(vid)
        if not play_path:
            try:
                data = self._api_get(f'/videos/{vid}')
                d = data.get('data') or {}
                play_path = d.get('playPath', '')
                if play_path:
                    self._play_cache[vid] = play_path
            except Exception:
                pass

        if not play_path:
            return {'parse': 1, 'playUrl': '', 'url': ''}

        m3u8_url = self._build_m3u8_url(play_path)

        return {
            'parse': 0,
            'playUrl': '',
            'url': m3u8_url,
            'header': {
                'User-Agent': self.header['User-Agent'],
                'Referer': self.host + '/',
            },
            'format': 'application/x-mpegURL',
            'contentType': 'application/x-mpegURL',
        }

    def _collection_play(self, vid):
        """合集剧集播放"""
        # vid 格式: col_{cid}_{episode_index}
        parts = vid.split('_')
        if len(parts) < 3:
            return {'parse': 1, 'playUrl': '', 'url': ''}
        cid = parts[1]
        ep_idx = int(parts[2]) if parts[2].isdigit() else 0

        # 从缓存取 episodes
        episodes = self._ep_cache.get(cid)
        if not episodes:
            ep_data = self._api_get(f'/collections/{cid}/episodes')
            episodes = (ep_data.get('data') or {}).get('list', [])
            self._ep_cache[cid] = episodes

        # 找到对应剧集
        play_path = ''
        for ep in episodes:
            if ep.get('index') == ep_idx:
                play_path = ep.get('playPath', '')
                break

        if not play_path:
            return {'parse': 1, 'playUrl': '', 'url': ''}

        m3u8_url = self._build_m3u8_url(play_path)

        return {
            'parse': 0,
            'playUrl': '',
            'url': m3u8_url,
            'header': {
                'User-Agent': self.header['User-Agent'],
                'Referer': self.host + '/',
            },
            'format': 'application/x-mpegURL',
            'contentType': 'application/x-mpegURL',
        }

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg):
        """搜索视频"""
        from urllib.parse import quote
        page = int(pg) if pg else 1
        if page < 1:
            page = 1

        try:
            url_path = f'/search?keyword={quote(key)}&type=video&page={page}&pageSize=20'
            data = self._api_get(url_path)
            d = data.get('data') or {}
            videos = [self._to_vod(v) for v in d.get('list', [])]
            total = d.get('total', 0)
            page_size = 20
            page_count = max(1, (total + page_size - 1) // page_size) if total else 1
            return {
                'list': videos,
                'page': page,
                'pagecount': page_count,
                'limit': page_size,
                'total': total,
            }
        except Exception:
            return {'list': [], 'page': page, 'pagecount': 1, 'limit': 20, 'total': 0}

    # ========== 直播/本地规则（不需要） ==========

    def isLive(self):
        return False

    def manualContent(self, lv):
        return {}
