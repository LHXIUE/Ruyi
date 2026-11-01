# coding: utf-8
# DramaRush 短剧爬虫 (实测可用版)
# 源站: https://ai.dramarush.tv
# 说明:
#   - 首页/搜索: tRPC API (drama.list)，20条/页，cursor 游标翻页
#   - 短剧/动漫: tRPC API (drama.list)，封面正常，cursor 游标翻页
#   - 长剧/电影/综艺: SSR 分类页解析，50条分3页展示，$L16 卡片含真实封面
#     (tRPC 对 DATACENTER 源内容返回统一占位图，SSR 页面才有真实封面)
#   - 详情页/播放页: 解析 SSR RSC 数据
#   - 播放: 三种源类型
#     mirror (/api/media/dc/mirror/): token 跨集通用，ep1 token 解锁全集
#     centaurus (/api/media/centaurus/hls/): token 跨集通用，ep1 token 解锁全集
#     dc/stream (/api/dc/stream/): token 每集独立，尝试 preview=0 解锁 + 跨集 token
#   - 会话: init() 时自动匿名登录 (better-auth anonymous)，获取 session cookie

from base.spider import Spider
import requests
import re
import json
import urllib.parse

try:
    import warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    warnings.filterwarnings('ignore')
except Exception:
    pass


class Spider(Spider):
    # 分类 ID -> API contentKind 枚举映射
    CATEGORY_MAP = {
        'short-drama': 'SHORT_DRAMA',
        'series': 'SERIES',
        'movie': 'MOVIE',
        'variety': 'VARIETY',
        'anime': 'ANIME',
    }

    # 走 SSR 分类页的分类（tRPC 返回占位封面，SSR 有真实封面）
    SSR_CATEGORIES = {'series', 'movie', 'variety'}

    # 占位封面图标识
    PLACEHOLDER_COVER = '828ed491f008e85d9caef01a'

    # SSR 分类页每页展示条数
    SSR_PAGE_SIZE = 20

    def __init__(self):
        self.siteUrl = "https://ai.dramarush.tv"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        # Session 管理 (参考 yznb 架构: 持久 cookie + 连接复用)
        self._session = requests.Session()
        self._session.headers.update(self.headers)
        self._session.verify = False
        self._authed = False
        # cursor 缓存: key=f"{scope}_{page}" -> cursor 字符串
        self._cursor_cache = {}
        # SSR 分类页缓存: key=tid -> 视频列表 (最多50条)
        self._ssr_list_cache = {}
        # ep1 模板缓存: key=drama_id -> (hls_url, ep1_ep_id)
        self._ep1_cache = {}

    def getName(self):
        return "DramaRush"

    def init(self, extend=""):
        self._ensure_session()

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        pass

    # ========== 会话管理 ==========

    def _ensure_session(self):
        """确保已建立匿名会话（模拟浏览器行为，获取 session cookie）"""
        if self._authed:
            return
        try:
            self._session.get(f"{self.siteUrl}/webpc", timeout=10)
            resp = self._session.post(
                f"{self.siteUrl}/api/auth/sign-in/anonymous",
                json={},
                headers={
                    "Content-Type": "application/json",
                    "Origin": self.siteUrl,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                self._authed = True
        except Exception:
            pass

    # ========== 基础请求 ==========

    def _fetch(self, url, headers=None):
        self._ensure_session()
        h = headers if headers else {}
        try:
            resp = self._session.get(url, headers=h, timeout=15)
            return resp.text
        except Exception:
            return ""

    def _trpc_get(self, procedure, params=None):
        """调用 tRPC GET 接口，返回 result.data.json"""
        self._ensure_session()
        input_obj = {"json": params or {}}
        encoded = urllib.parse.quote(json.dumps(input_obj, ensure_ascii=False))
        url = f"{self.siteUrl}/api/trpc/{procedure}?input={encoded}"
        try:
            resp = self._session.get(url, headers={"Accept": "application/json"}, timeout=15)
            data = resp.json()
            return data.get("result", {}).get("data", {}).get("json", {})
        except Exception:
            return {}

    # ========== SSR HTML 解析工具 ==========

    def _extract_pushes(self, html):
        pushes = []
        pos = 0
        while True:
            idx = html.find('self.__next_f.push([', pos)
            if idx == -1:
                break
            m = re.search(r'self\.__next_f\.push\(\[(\d+),"', html[idx:idx+50])
            if not m:
                pos = idx + 1
                continue
            start = idx + m.end()
            i = start
            while i < len(html):
                if html[i] == '\\' and i + 1 < len(html):
                    i += 2
                elif html[i] == '"' and i + 1 < len(html) and html[i+1] == ']' and html[i+2] == ')':
                    pushes.append((m.group(1), html[start:i]))
                    pos = i + 3
                    break
                else:
                    i += 1
            else:
                pos = idx + 1
        return pushes

    def _extract_json_value(self, text, key):
        """用括号匹配从已解码字符串中提取 key 对应的 JSON 对象或数组"""
        marker = '"' + key + '":'
        idx = text.find(marker)
        if idx == -1:
            return None
        pos = idx + len(marker)
        while pos < len(text) and text[pos] in ' \t\n\r':
            pos += 1
        if pos >= len(text) or text[pos] not in '{[':
            return None
        open_ch = text[pos]
        close_ch = '}' if open_ch == '{' else ']'
        depth = 0
        in_string = False
        escape = False
        for i in range(pos, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if not in_string:
                if ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[pos:i+1])
                        except Exception:
                            return None
        return None

    # ========== SSR 分类页解析 ($L16 卡片) ==========

    def _parse_ssr_category(self, html):
        """解析 SSR 分类页的 $L16 视频卡片，提取 ID、标题、封面

        每个 push 可能含多个 $L16 卡片。
        图片匹配策略: 对每个卡片 ID，在同 push 内找距离最近的非占位图 URL。
        """
        videos = []
        seen = set()

        for num, raw in self._extract_pushes(html):
            try:
                inner = json.loads('"' + raw + '"')
            except Exception:
                continue
            if '$L16' not in inner:
                continue

            # 提取所有 $L16 drama ID 及位置
            id_matches = list(re.finditer(
                r'\["\$","\$L16","([cm][a-z0-9]{20,})"', inner
            ))
            if not id_matches:
                continue

            # 提取所有非占位图的真实图片 URL 及位置
            img_matches = []
            for img_m in re.finditer(
                r'"src":"(https://(?:raw|cdn)\.shorttv\.online/[^"]+\.(?:jpg|jpeg|png|webp))"',
                inner
            ):
                if self.PLACEHOLDER_COVER not in img_m.group(1):
                    img_matches.append(img_m)

            # 提取所有 alt 文本 (标题) 及位置
            alt_matches = list(re.finditer(r'"alt":"([^"]+)"', inner))

            for id_m in id_matches:
                vid = id_m.group(1)
                if vid in seen:
                    continue

                # 匹配距离最近的图片
                best_url = ""
                if img_matches:
                    best_dist = float('inf')
                    id_pos = id_m.start()
                    for img_m in img_matches:
                        dist = abs(img_m.start() - id_pos)
                        if dist < best_dist and dist < 5000:
                            best_dist = dist
                            best_url = img_m.group(1)

                # 匹配距离最近的标题
                title = ""
                if alt_matches:
                    best_dist = float('inf')
                    id_pos = id_m.start()
                    for alt_m in alt_matches:
                        dist = abs(alt_m.start() - id_pos)
                        if dist < best_dist and dist < 5000:
                            best_dist = dist
                            title = alt_m.group(1)

                # 如果 alt 没找到，尝试从 h3 children 提取
                if not title:
                    h3_match = re.search(
                        r'\["\$","h3",.*?"children":"([^"]+)"', inner
                    )
                    if h3_match:
                        title = h3_match.group(1)

                if vid and title:
                    seen.add(vid)
                    # 提取集数
                    remarks = ""
                    ep_match = re.search(r'"children":"(\d+\s*集)"', inner)
                    if ep_match:
                        remarks = ep_match.group(1)
                    videos.append({
                        'vod_id': vid,
                        'vod_name': title,
                        'vod_pic': best_url,
                        'vod_remarks': remarks
                    })

        return videos

    def _get_ssr_category_list(self, tid):
        """获取 SSR 分类页视频列表（带缓存）"""
        if tid in self._ssr_list_cache:
            return self._ssr_list_cache[tid]
        url = f"{self.siteUrl}/webpc/category/{tid}"
        html = self._fetch(url)
        videos = self._parse_ssr_category(html)
        self._ssr_list_cache[tid] = videos
        return videos

    # ========== tRPC 列表格式化 ==========

    def _format_video_list(self, items):
        """将 tRPC API 返回的 items 格式化为 TVBox 视频列表"""
        videos = []
        for item in items:
            if not isinstance(item, dict) or 'id' not in item:
                continue
            ep_count = item.get('totalEpisodes', 0)
            remarks = f"{ep_count}集" if ep_count else ''
            videos.append({
                'vod_id': item.get('id', ''),
                'vod_name': item.get('title', ''),
                'vod_pic': item.get('cover', item.get('poster', '')),
                'vod_remarks': remarks
            })
        return videos

    # ========== 首页 ==========

    def homeContent(self, filter):
        result = {}
        result['class'] = [
            {'type_id': 'short-drama', 'type_name': '短剧'},
            {'type_id': 'series', 'type_name': '长剧'},
            {'type_id': 'movie', 'type_name': '电影'},
            {'type_id': 'variety', 'type_name': '综艺'},
            {'type_id': 'anime', 'type_name': '动漫'},
        ]
        data = self._trpc_get('drama.list', {})
        result['list'] = self._format_video_list(data.get('items', []))
        cursor = data.get('nextCursor')
        if cursor:
            self._cursor_cache['short-drama_2'] = cursor
        return result

    def homeVideoContent(self):
        data = self._trpc_get('drama.list', {})
        return {'list': self._format_video_list(data.get('items', []))}

    # ========== 分类页 ==========

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg and str(pg).isdigit() else 1

        # --- SSR 分类 (series/movie/variety): 50条分页展示 ---
        if tid in self.SSR_CATEGORIES:
            all_videos = self._get_ssr_category_list(tid)
            total = len(all_videos)
            pagecount = (total + self.SSR_PAGE_SIZE - 1) // self.SSR_PAGE_SIZE
            if pagecount < 1:
                pagecount = 1
            start = (page - 1) * self.SSR_PAGE_SIZE
            end = start + self.SSR_PAGE_SIZE
            page_videos = all_videos[start:end]
            return {
                'list': page_videos,
                'page': pg,
                'pagecount': pagecount,
                'limit': self.SSR_PAGE_SIZE,
                'total': total
            }

        # --- tRPC 分类 (short-drama/anime): cursor 游标翻页 ---
        cache_key = f"{tid}_{page}"
        cursor = self._cursor_cache.get(cache_key) if page > 1 else None

        params = {}
        cat = self.CATEGORY_MAP.get(tid)
        if cat:
            params['contentKind'] = cat
        if cursor:
            params['cursor'] = cursor

        data = self._trpc_get('drama.list', params)
        items = data.get('items', [])
        next_cursor = data.get('nextCursor')

        if next_cursor:
            self._cursor_cache[f"{tid}_{page + 1}"] = next_cursor
            pagecount = page + 1
        else:
            pagecount = page

        return {
            'list': self._format_video_list(items),
            'page': pg,
            'pagecount': pagecount,
            'limit': 20,
            'total': pagecount * 20
        }

    # ========== 详情页 ==========

    def detailContent(self, ids):
        if not ids:
            return {'list': []}
        drama_id = ids[0]
        url = f"{self.siteUrl}/webpc/watch/{drama_id}/1"
        h = {'Referer': f"{self.siteUrl}/webpc/d/{drama_id}"}
        html = self._fetch(url, headers=h)

        pushes = self._extract_pushes(html)
        drama = None
        episodes = []
        for num, raw in pushes:
            try:
                inner = json.loads('"' + raw + '"')
            except Exception:
                continue
            if '"drama":' not in inner or '"episode":' not in inner:
                continue
            if drama is None:
                d = self._extract_json_value(inner, 'drama')
                if d and isinstance(d, dict) and 'id' in d and 'title' in d:
                    drama = d
            if not episodes:
                eps = self._extract_json_value(inner, 'episodes')
                if eps and isinstance(eps, list) and len(eps) > 0:
                    episodes = eps
            if drama and episodes:
                break

        if not drama:
            return {'list': []}

        # 封面: 如果是占位图，从 SSR 分类缓存中按 ID 查找真实封面
        cover = drama.get('cover') or ''
        if self.PLACEHOLDER_COVER in cover:
            for cached_list in self._ssr_list_cache.values():
                for v in cached_list:
                    if v['vod_id'] == drama_id and v['vod_pic']:
                        cover = v['vod_pic']
                        break
                if self.PLACEHOLDER_COVER not in cover:
                    break

        play_parts = []
        for ep in episodes:
            idx = ep.get('index', 1)
            title = ep.get('title', f'第{idx}集')
            ep_id = ep.get('id', '')
            play_parts.append(f"{title}${drama_id}|{idx}|{ep_id}")

        # 简介: description 为空时用集数信息兜底
        content = drama.get('description') or ''
        if not content:
            total_eps = drama.get('totalEpisodes', 0)
            free_eps = drama.get('freeEpisodes', 0)
            if total_eps and free_eps and free_eps < total_eps:
                content = f"共{total_eps}集，前{free_eps}集免费观看"
            elif total_eps:
                content = f"共{total_eps}集"

        return {
            'list': [{
                'vod_id': drama_id,
                'vod_name': drama.get('title', ''),
                'vod_pic': cover,
                'vod_content': content,
                'vod_director': '',
                'vod_actor': '',
                'vod_year': '',
                'vod_area': '',
                'vod_remarks': f"{drama.get('totalEpisodes', 0)}集",
                'vod_play_from': 'DramaRush',
                'vod_play_url': '#'.join(play_parts) if play_parts else ""
            }]
        }

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg and str(pg).isdigit() else 1
        cache_key = f"search_{key}_{page}"
        cursor = self._cursor_cache.get(cache_key) if page > 1 else None

        params = {'q': key}
        if cursor:
            params['cursor'] = cursor

        data = self._trpc_get('drama.list', params)
        items = data.get('items', [])
        next_cursor = data.get('nextCursor')

        if next_cursor:
            self._cursor_cache[f"search_{key}_{page + 1}"] = next_cursor
            pagecount = page + 1
        else:
            pagecount = page

        return {
            'list': self._format_video_list(items),
            'page': pg,
            'pagecount': pagecount,
            'limit': 20,
            'total': pagecount * 20
        }

    # ========== 播放 ==========

    def _get_ep1_template(self, drama_id):
        """获取第1集 hlsUrl 模板（带缓存），用于跨集解锁"""
        if drama_id in self._ep1_cache:
            return self._ep1_cache[drama_id]

        ep1_html = self._fetch(
            f"{self.siteUrl}/webpc/watch/{drama_id}/1",
            headers={'Referer': f"{self.siteUrl}/webpc/d/{drama_id}"}
        )
        ep1_hls = ""
        ep1_ep_id = ""
        for num, raw in self._extract_pushes(ep1_html):
            try:
                inner = json.loads('"' + raw + '"')
            except Exception:
                continue
            if '"episode":' in inner and '"hlsUrl"' in inner:
                m = re.search(r'"hlsUrl":"([^"]+)"', inner)
                if m:
                    ep1_hls = m.group(1)
                    ep_m = re.search(r'[?&]ep=([a-z0-9]+)', ep1_hls)
                    if ep_m:
                        ep1_ep_id = ep_m.group(1)
                break

        self._ep1_cache[drama_id] = (ep1_hls, ep1_ep_id)
        return ep1_hls, ep1_ep_id

    def playerContent(self, flag, id, vipFlags):
        parts = id.split('|')
        if len(parts) < 2:
            return {'parse': 0, 'url': '', 'header': ''}
        drama_id = parts[0]
        episode_index = parts[1]
        episode_id = parts[2] if len(parts) > 2 else ''

        # 请求当前集播放页
        url = f"{self.siteUrl}/webpc/watch/{drama_id}/{episode_index}"
        html = self._fetch(url, headers={'Referer': f"{self.siteUrl}/webpc/d/{drama_id}"})

        hls_url = ""

        # 从当前集播放页提取 hlsUrl（免费集有值，锁定集为 null）
        for num, raw in self._extract_pushes(html):
            try:
                inner = json.loads('"' + raw + '"')
            except Exception:
                continue
            if '"episode":' in inner and '"hlsUrl"' in inner:
                m = re.search(r'"hlsUrl":"([^"]+)"', inner)
                if m:
                    hls_url = m.group(1)
                break

        # 当前集 hlsUrl 为 null（locked），用第1集的 token 跨集构建
        # 三种源类型的跨集播放能力:
        #   mirror 源 (/api/media/dc/mirror/): token 可跨集，ep1 token 解锁全部集
        #   centaurus 源 (/api/media/centaurus/hls/): token 可跨集，ep1 token 解锁全部集
        #   dc/stream 源 (/api/dc/stream/): token 每集独立，尝试 preview=0 + 跨集 token
        if not hls_url and episode_id:
            ep1_hls, ep1_ep_id = self._get_ep1_template(drama_id)

            if ep1_hls and ep1_ep_id:
                # 替换路径中的 ep_id，保留 ep1 的 tok 和 ep 参数
                path_part = ep1_hls.split('?')[0]
                query_part = ep1_hls.split('?', 1)[1] if '?' in ep1_hls else ''
                path_part = path_part.replace(ep1_ep_id, episode_id)

                if '/dc/stream/' in ep1_hls:
                    # dc/stream 源: token 每集独立，跨集复用会 403
                    # preview=0 对 dramarush 无效（仅 yznb 站点支持）
                    # 不构建无效 URL，避免播放器转圈后黑屏
                    pass
                else:
                    # mirror / centaurus 源: token 跨集通用，直接替换即可
                    hls_url = path_part + ('?' + query_part if query_part else '')

        if hls_url.startswith('/'):
            hls_url = self.siteUrl + hls_url

        # centaurus 源返回 master playlist（多码率），子流 URL 不带 token
        # TVBox 播放器请求子流时会丢失 token 导致播放失败
        # 解决: 解析 master m3u8，直接返回最高码率的 index.m3u8 并拼接 token
        if hls_url and 'centaurus' in hls_url and 'master.m3u8' in hls_url:
            try:
                master_resp = self._session.get(
                    hls_url,
                    headers={"Referer": self.siteUrl + "/"},
                    timeout=10
                )
                if master_resp.status_code == 200 and '#EXT-X-STREAM-INF' in master_resp.text:
                    lines = master_resp.text.strip().split('\n')
                    for i, line in enumerate(lines):
                        if line.startswith('#EXT-X-STREAM-INF') and i + 1 < len(lines):
                            sub_url = lines[i + 1].strip()
                            # 拼接完整 URL
                            if not sub_url.startswith('http'):
                                base = hls_url.rsplit('/', 1)[0]
                                sub_url = base + '/' + sub_url
                            # 追加 token 参数
                            query_part = hls_url.split('?', 1)[1] if '?' in hls_url else ''
                            if query_part and 'tok=' not in sub_url:
                                sub_url = sub_url + ('&' if '?' in sub_url else '?') + query_part
                            hls_url = sub_url
                            break
            except Exception:
                pass

        header = json.dumps({
            "User-Agent": self.headers['User-Agent'],
            "Referer": self.siteUrl + "/",
            "Origin": self.siteUrl
        }, ensure_ascii=False)

        return {
            'parse': 0,
            'url': hls_url,
            'header': header
        }

    def localProxy(self, param):
        return [200, "video/MP2T", "", ""]
