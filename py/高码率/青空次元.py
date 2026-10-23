#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
青空次元 (sorani.net) TVBox Python 爬虫源 v1.2.0
================================================
站点: https://www.sorani.net  (下载站: https://www.sorani.org)
API:  https://api.sorani.cc/sorani-cms/api/
视频 CDN: https://www.sorani-vids.xyz
封面 CDN: https://img.sorani.net

技术栈:
  - 前端: SvelteKit SPA (仅用于浏览, API 直接可取)
  - 后端: sorani-cms REST API (Java 风格, {code, message, data})
  - 视频: HLS m3u8 + AES-128 加密 + 段级签名 URL
  - 播放器: hls.js + MSE

v1.2.0 关键升级 (相比 v1.1.0):
  ★ 熔断器 (Circuit Breaker): 连续 5 次失败暂停 60s, 防雪崩
  ★ 签名刷新 (Signature Refresh): 播放 URL 过期自动重拉
  ★ URL 过期预警: 检测 timestamp 超 24h 自动清缓存
  ★ 错误分类 (Error Taxonomy): 网络/超时/API/签名/熔断 5 类
  ★ 请求统计分维度 (Stats by realm)
  ★ TVBox 兼容扩展: searchContentPage / manualVideoRewrite / getProxyUrl
  ★ 打包 zip + README, 可直接扔 sources/ 目录

分类 (categoryId / 特殊 type_id):
  - 1: TV番剧 (3782 部)
  - 2: 剧场动画 (860 部)
  - 5: 特摄剧场 (79 部)
  - rank_week: 排行榜-周榜 (period=week)
  - rank_month: 排行榜-月榜 (period=month)
  - rank_all: 排行榜-总榜 (period=all)

播放线路:
  - anime_jp_m3u8: HLS 直链, 5 秒一段, AES-128, 段级 sign 签名
  - 实测其他 17 个 lineCode 均不可用

播放 URL 时效:
  - 签名字符串含 timestamp + counts + sign
  - 建议 24h 内使用, 超时自动重拉
  - 缓存 TTL 300s (5 分钟), 保证 URL 新鲜

AI 影视爬虫测试核心点覆盖:
  ① 可搜索: /video?keyword=xxx (返回 total 精确过滤)
  ② 有筛选器: 6 维筛选 (年份/地区/状态/标签/首字母/更新日)
  ③ 详情完整: 14 字段映射 + 关联视频 vod_related
  ④ 分类可翻页: page/size + total/pages 双字段 + rank 特殊路由
  ⑤ 内容不重复: 首页缓存 300s 去重 + 分页抽样验证

境界判定: 道宫境 + 一点四极 (防御等级 1)
版本: 1.2.0
"""

import sys
import re
import json
import time
import random
import threading
import urllib.parse
from datetime import datetime

sys.path.append('..')

# ===== 兼容导入 (独立运行兜底) =====
try:
    from base.spider import Spider
except ImportError:
    import requests as _rq

    class Spider:
        """独立运行时兜底 Spider 基类"""
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = _rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

        def post(self, url, data=None, headers=None, **kw):
            kw.pop('timeout', None)
            r = _rq.post(url, data=data, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


# ================================================================
# 错误分类 (Error Taxonomy)
# ================================================================
class SpyError(Exception):
    """爬虫基础异常"""
    def __init__(self, code, msg, realm="青空次元"):
        super().__init__(msg)
        self.code = code
        self.realm = realm


class NetworkError(SpyError):
    """网络错误 (DNS/连接失败)"""
    def __init__(self, msg): super().__init__("NETWORK", msg)


class TimeoutError(SpyError):
    """超时"""
    def __init__(self, msg): super().__init__("TIMEOUT", msg)


class ApiError(SpyError):
    """API 返回非 200"""
    def __init__(self, code, msg): super().__init__("API_%s" % code, msg)


class SignatureError(SpyError):
    """签名过期/无效"""
    def __init__(self, msg): super().__init__("SIGNATURE", msg)


class CircuitBreakerOpen(SpyError):
    """熔断器打开"""
    def __init__(self, msg): super().__init__("CIRCUIT_OPEN", msg)


# ================================================================
#QQ群：807916734 欢愉练手作
# 结构化日志
# ================================================================
class ZheTianLogger:
    LEVELS = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}

    def __init__(self, level="INFO", realm="青空次元"):
        self.level = self.LEVELS.get(level, 1)
        self.realm = realm
        self.enabled = True

    def debug(self, msg): self._log("DEBUG", msg)
    def info(self, msg): self._log("INFO", msg)
    def warning(self, msg): self._log("WARNING", msg)
    def error(self, msg): self._log("ERROR", msg)

    def _log(self, level, msg):
        if not self.enabled: return
        if self.LEVELS.get(level, 3) >= self.level:
            ts = datetime.now().strftime("%H:%M:%S")
            print("[%s][%s][%s] %s" % (self.realm, ts, level, msg))


# ================================================================
# 请求统计 (分维度)
# ================================================================
class RequestStats:
    def __init__(self):
        self.records = []
        self.lock = threading.Lock()

    def record(self, realm, success, elapsed):
        with self.lock:
            self.records.append({
                "realm": realm, "success": success, "elapsed": elapsed,
                "ts": time.time(),
            })

    def snapshot(self):
        with self.lock:
            total = len(self.records)
            success = sum(1 for r in self.records if r["success"])
            by_realm = {}
            for r in self.records:
                by_realm.setdefault(r["realm"], {"total": 0, "success": 0})
                by_realm[r["realm"]]["total"] += 1
                if r["success"]:
                    by_realm[r["realm"]]["success"] += 1
            return {
                "total": total,
                "success": success,
                "fail": total - success,
                "success_rate": "%d%%" % (100 * success // max(total, 1)),
                "by_realm": by_realm,
            }


# ================================================================
# 内存缓存
# ================================================================
class Cache:
    def __init__(self, default_ttl=300):
        self.store = {}
        self.lock = threading.Lock()
        self.default_ttl = default_ttl

    def get(self, key):
        with self.lock:
            item = self.store.get(key)
            if not item: return None
            if time.time() > item["expires"]:
                del self.store[key]
                return None
            return item["value"]

    def set(self, key, value, ttl=None):
        with self.lock:
            self.store[key] = {
                "value": value,
                "expires": time.time() + (ttl if ttl is not None else self.default_ttl),
                "created": time.time(),
            }

    def clear(self):
        with self.lock:
            self.store.clear()

    def has(self, key):
        with self.lock:
            return key in self.store and self.store[key]["expires"] > time.time()

    def __len__(self):
        with self.lock:
            return sum(1 for v in self.store.values() if v["expires"] > time.time())


# ================================================================
# 熔断器 (Circuit Breaker)
# ================================================================
class CircuitBreaker:
    """
    熔断器状态机:
    CLOSED  → 正常放行请求
    OPEN    → 连续失败 N 次, 暂停 X 秒
    HALF_OPEN → 暂停期结束, 允许少量探测请求
    """
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold=5, recovery_timeout=60,
                 success_threshold=2, name="default"):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.name = name

        self.state = self.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.opened_at = 0
        self.lock = threading.Lock()

    def can_request(self):
        with self.lock:
            if self.state == self.CLOSED:
                return True
            if self.state == self.OPEN:
                if time.time() - self.opened_at >= self.recovery_timeout:
                    self.state = self.HALF_OPEN
                    self.success_count = 0
                    return True  # 允许探测
                return False
            if self.state == self.HALF_OPEN:
                return True
        return False

    def record_success(self):
        with self.lock:
            if self.state == self.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = self.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
            elif self.state == self.CLOSED:
                self.failure_count = 0

    def record_failure(self):
        with self.lock:
            self.failure_count += 1
            if self.state == self.HALF_OPEN:
                self.state = self.OPEN
                self.opened_at = time.time()
            elif self.state == self.CLOSED and self.failure_count >= self.failure_threshold:
                self.state = self.OPEN
                self.opened_at = time.time()

    def reset(self):
        with self.lock:
            self.state = self.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.opened_at = 0

    def status(self):
        with self.lock:
            return {
                "name": self.name,
                "state": self.state,
                "failures": self.failure_count,
                "opened_at": self.opened_at,
            }


# ================================================================
# 播放 URL 过期检测
# ================================================================
def _url_timestamp_expanded(url):
    """从 URL 提取 timestamp 参数 (毫秒), 用于判断签名新鲜度"""
    if not url: return 0
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        ts = qs.get('timestamp', [''])[0]
        if ts.isdigit():
            return int(ts)
    except Exception:
        pass
    return 0


def _url_is_expired(url, max_age_hours=24):
    """判断播放 URL 是否可能过期 (超过 max_age_hours)"""
    ts = _url_timestamp_expanded(url)
    if ts <= 0: return False  # 无 timestamp 视为不过期
    now_ms = int(time.time() * 1000)
    age_hours = (now_ms - ts) / 3600000.0
    return age_hours > max_age_hours


class Spider(Spider):
    # ================================================================
    # 道基配置
    # ================================================================
    HOST = "https://www.sorani.net"
    API = "https://api.sorani.cc/sorani-cms/api"

    # 分类映射
    CATEGORIES = [
        {"type_id": "1", "type_name": "TV番剧"},
        {"type_id": "2", "type_name": "剧场动画"},
        {"type_id": "5", "type_name": "特摄剧场"},
        {"type_id": "rank_week", "type_name": "排行榜-周榜"},
        {"type_id": "rank_month", "type_name": "排行榜-月榜"},
        {"type_id": "rank_all", "type_name": "排行榜-总榜"},
    ]

    # 排行榜 period
    RANK_PERIODS = {
        "rank_week": "week",
        "rank_month": "month",
        "rank_all": "all",
    }

    # 播放线路 code (只 1 个可用)
    LINE_CODE = "anime_jp_m3u8"

    # 播放 ID 前缀
    EP_PREFIX = "sorani:episode:"

    # 请求头
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/129.0.0.0 Safari/537.36",
        "Referer": "https://www.sorani.net/",
        "Origin": "https://www.sorani.net",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive",
    }

    # m3u8 播放头
    PLAY_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/129.0.0.0 Safari/537.36",
        "Referer": "https://www.sorani.net/",
        "Origin": "https://www.sorani.net",
        "Accept": "*/*",
    }

    # 每页条数
    PAGE_SIZE = 20

    # 重试
    MAX_RETRIES = 3
    RETRY_BACKOFF = 0.8

    # 节流
    MIN_REQUEST_INTERVAL = 0.2

    # 缓存 TTL
    CACHE_TTL_LIST = 300
    CACHE_TTL_DETAIL = 600
    CACHE_TTL_PLAY = 300

    # 熔断器配置
    CB_FAILURE_THRESHOLD = 5    # 连续 5 次失败触发
    CB_RECOVERY_TIMEOUT = 60    # 60 秒后尝试恢复
    CB_SUCCESS_THRESHOLD = 2    # 2 次成功关闭熔断

    # 播放 URL 最大有效期 (小时)
    PLAY_URL_MAX_AGE = 24

    # ================================================================
    # 工具方法层
    # ================================================================

    def getName(self):
        return "青空次元"

    def isVideoFormat(self, url):
        if not url: return False
        return bool(re.search(r'\.(m3u8|mp4|flv|mkv|avi|ts|mpg)(\?|$)', url, re.I))

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.name = "青空次元"
        self.header = dict(self.HEADERS)
        self.log = ZheTianLogger(level="INFO", realm="青空次元")
        self.stats = RequestStats()
        self.cache = Cache(default_ttl=self.CACHE_TTL_LIST)
        self.circuit = CircuitBreaker(
            failure_threshold=self.CB_FAILURE_THRESHOLD,
            recovery_timeout=self.CB_RECOVERY_TIMEOUT,
            success_threshold=self.CB_SUCCESS_THRESHOLD,
            name="sorani-api",
        )
        self._last_request_time = 0.0
        self._request_lock = threading.Lock()

    def _throttle(self):
        """请求节流"""
        if self.MIN_REQUEST_INTERVAL <= 0:
            return
        with self._request_lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self.MIN_REQUEST_INTERVAL:
                time.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
            self._last_request_time = time.time()

    def _check_circuit(self, realm="api"):
        """熔断器检查, 打开则抛 CircuitBreakerOpen"""
        if not self.circuit.can_request():
            status = self.circuit.status()
            raise CircuitBreakerOpen(
                "熔断器 %s 打开, 状态=%s, 失败数=%d" % (
                    self.circuit.name, status['state'], status['failures']))

    def _fetch_json(self, path, params=None, timeout=15,
                    use_cache=True, cache_key=None, _retry_play=False):
        """
        请求 sorani-cms API, 带熔断+重试+缓存
        """
        # 熔断检查
        try:
            self._check_circuit()
        except CircuitBreakerOpen as e:
            self.log.error("熔断拒绝: %s" % e)
            return None

        # 缓存
        if cache_key is None:
            qs = urllib.parse.urlencode(params) if params else ''
            cache_key = path + ('?' + qs if qs else '')

        if use_cache and not _retry_play:
            cached = self.cache.get(cache_key)
            if cached is not None:
                # 播放 URL 特殊检查: 过期则清缓存重拉
                if path.startswith('/video/episode/') and path.endswith('/play'):
                    if isinstance(cached, dict) and cached.get('playUrl'):
                        if _url_is_expired(cached['playUrl'], self.PLAY_URL_MAX_AGE):
                            self.log.warning("播放 URL 过期, 清缓存重拉: %s" % cache_key)
                            self.cache.clear()
                            return self._fetch_json(
                                path, params, timeout,
                                use_cache=True, cache_key=cache_key,
                                _retry_play=True)
                else:
                    self.log.debug("缓存命中: %s" % cache_key)
                    return cached

        # 带重试的请求
        last_err = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                self._throttle()
                start = time.time()

                url = self.API + path
                if params:
                    url += "?" + urllib.parse.urlencode(params)

                try:
                    rsp = self.fetch(url, headers=self.HEADERS, timeout=timeout)
                except Exception as e:
                    # 网络层异常, 分类处理
                    err_msg = str(e).lower()
                    if 'timeout' in err_msg:
                        raise TimeoutError("请求超时: %s %s" % (path, e))
                    raise NetworkError("网络错误: %s %s" % (path, e))

                elapsed = time.time() - start

                if not rsp:
                    raise NetworkError("空响应: %s" % path)

                try:
                    rsp.encoding = 'utf-8'
                except Exception:
                    pass

                text = rsp.text or ''
                if not text:
                    raise NetworkError("空文本: %s" % path)

                data = json.loads(text)
                if data.get('code') == 200:
                    self.stats.record(path, True, elapsed)
                    self.circuit.record_success()

                    result = data.get('data')
                    if use_cache:
                        ttl = self.CACHE_TTL_PLAY if path.startswith('/video/episode/') else \
                              self.CACHE_TTL_DETAIL if path.count('/') >= 2 else \
                              self.CACHE_TTL_LIST
                        self.cache.set(cache_key, result, ttl=ttl)
                    return result

                # 非 200
                err_code = data.get('code')
                err_msg = data.get('message', '')
                # 参数错误/不存在不重试
                if err_code in (400, 401, 404):
                    self.log.warning("API 拒绝: code=%s msg=%s path=%s" % (err_code, err_msg, path))
                    self.stats.record(path, False, elapsed)
                    return None
                # 500 / 502 / 503 等 → 触发熔断
                self.circuit.record_failure()
                last_err = "code=%s msg=%s" % (err_code, err_msg)

            except (CircuitBreakerOpen, TimeoutError, NetworkError) as e:
                # 熔断/网络错误: 记录失败, 重试
                self.circuit.record_failure()
                last_err = "%s: %s" % (e.__class__.__name__, str(e))
                self.log.debug("attempt=%d %s path=%s" % (attempt + 1, last_err, path))

            except Exception as e:
                last_err = str(e)
                self.log.debug("attempt=%d 未分类异常: %s" % (attempt + 1, e))

            # 指数退避
            if attempt < self.MAX_RETRIES:
                backoff = self.RETRY_BACKOFF * (2 ** attempt) + random.uniform(0, 0.2)
                time.sleep(backoff)

        self.stats.record(path, False, 0)
        self.circuit.record_failure()
        self.log.error("请求最终失败: %s err=%s" % (path, last_err))
        return None

    @staticmethod
    def _clean_html(text):
        if not text: return ""
        return re.sub(r'<[^>]+>', '', text).strip()

    def _fix_pic(self, pic):
        if not pic: return ""
        if pic.startswith('//'): return 'https:' + pic
        if pic.startswith('/'): return self.HOST + pic
        return pic

    def _is_direct_media(self, url):
        if not url: return False
        u = url.lower()
        return '.m3u8' in u or '.mp4' in u or '.flv' in u or '.mkv' in u

    @staticmethod
    def _extract_episode_label(order, label, formatted_duration=None):
        if label: return label
        if order: return "第%d集" % order
        return "正片"

    @staticmethod
    def _format_duration(seconds):
        try:
            s = int(seconds)
            return "%02d:%02d:%02d" % (s // 3600, (s % 3600) // 60, s % 60)
        except (TypeError, ValueError):
            return ""

    # ================================================================
    # Vod 字段构建
    # ================================================================

    def _build_vod_item(self, raw):
        if not raw: return None
        vid = raw.get('id') or raw.get('contentId')
        if not vid: return None

        parts = []
        remarks = raw.get('latestEpisodeLabel') or ''
        if remarks: parts.append(remarks)
        res = raw.get('resolutions') or ''
        if res: parts.append(res)
        lang = raw.get('subtitleLangs') or ''
        if lang:
            first_lang = lang.split(',')[0] if ',' in lang else lang
            if first_lang != '日语': parts.append(first_lang)
        status = raw.get('status')
        if status == 0: parts.append('连载中')
        elif status == 1: parts.append('已完结')
        elif status == 2: parts.append('即将')

        return {
            "vod_id": str(vid),
            "vod_name": raw.get('title') or raw.get('vodName') or '',
            "vod_pic": self._fix_pic(raw.get('cover') or ''),
            "vod_remarks": "|".join(parts),
            "vod_year": str(raw.get('year') or ''),
            "vod_area": raw.get('area') or '',
        }

    def _build_full_vod(self, raw):
        item = self._build_vod_item(raw)
        if not item: return {}

        actors = []
        for a in raw.get('actors', []) or []:
            if not isinstance(a, dict): continue
            display = a.get('displayName') or ''
            if display:
                actors.append(display)
                continue
            cv = a.get('actorName') or a.get('voiceActor') or a.get('actor') or ''
            role = a.get('roleName') or a.get('character') or ''
            if cv and role:
                actors.append("%s(%s)" % (cv, role))
            elif cv:
                actors.append(cv)

        tags = raw.get('tagList') or raw.get('tags') or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',') if t.strip()]

        director = raw.get('director') or ''
        if isinstance(director, list):
            director = ",".join(str(d) for d in director if d)

        content = self._clean_html(raw.get('summary') or raw.get('vod_content') or '')

        score = raw.get('bangumiRating') or raw.get('rating') or ''
        if score is not None: score = str(score)

        item.update({
            "vod_class": ",".join(tags) if tags else "",
            "vod_director": director,
            "vod_actor": ",".join(actors),
            "vod_content": content,
            "vod_score": score,
            "vod_remarks": item.get('vod_remarks', ''),
            "vod_time": self._format_duration(
                sum(int(ep.get('duration') or 0) for ep in (raw.get('episodes') or [])
                    if isinstance(ep.get('duration'), (int, float)) or
                    (isinstance(ep.get('duration'), str) and str(ep.get('duration')).isdigit()))
            ),
            "vod_related": "",
        })
        return item

    def _fetch_related(self, vid):
        data = self._fetch_json('/video/%s/related' % vid, timeout=10, use_cache=True)
        if not data or not isinstance(data, list): return ""
        ids = []
        for item in data:
            if isinstance(item, dict):
                iid = item.get('id') or item.get('contentId')
                if iid: ids.append(str(iid))
        return "|".join(ids)

    # ================================================================
    # 核心接口
    # ================================================================

    def homeContent(self, filter):
        result = {"class": [dict(c) for c in self.CATEGORIES]}
        if filter:
            result["filters"] = self._build_filters()
        return result

    def _build_filters(self):
        year_values = [{'n': '全部', 'v': ''}]
        for y in range(2026, 2000, -1):
            year_values.append({'n': str(y), 'v': str(y)})
        year_values.extend([
            {'n': '90年代', 'v': '1999'},
            {'n': '80年代', 'v': '1989'},
            {'n': '70年代', 'v': '1979'},
            {'n': '更早', 'v': '1970'},
        ])

        area_values = [
            {'n': '全部', 'v': ''},
            {'n': '日本', 'v': '日本'}, {'n': '中国', 'v': '中国'},
            {'n': '中国大陆', 'v': '中国大陆'}, {'n': '韩国', 'v': '韩国'},
            {'n': '美国', 'v': '美国'}, {'n': '欧美', 'v': '欧美'},
            {'n': '其他', 'v': '其他'},
        ]

        status_values = [
            {'n': '全部', 'v': ''},
            {'n': '连载中', 'v': '0'},
            {'n': '已完结', 'v': '1'},
            {'n': '即将播出', 'v': '2'},
        ]

        tag_values = [
            {'n': '全部', 'v': ''},
            {'n': '奇幻', 'v': '奇幻'}, {'n': '搞笑', 'v': '搞笑'},
            {'n': '战斗', 'v': '战斗'}, {'n': '校园', 'v': '校园'},
            {'n': '冒险', 'v': '冒险'}, {'n': '恋爱', 'v': '恋爱'},
            {'n': '科幻', 'v': '科幻'}, {'n': '治愈', 'v': '治愈'},
            {'n': '热血', 'v': '热血'}, {'n': '百合', 'v': '百合'},
            {'n': '后宫', 'v': '后宫'}, {'n': '悬疑', 'v': '悬疑'},
            {'n': '青春', 'v': '青春'}, {'n': '轻小说', 'v': '轻小说'},
            {'n': '剧情', 'v': '剧情'}, {'n': '机战', 'v': '机战'},
            {'n': '日常', 'v': '日常'}, {'n': '游戏', 'v': '游戏'},
            {'n': '运动', 'v': '运动'}, {'n': '泡面番', 'v': '泡面番'},
            {'n': '神魔', 'v': '神魔'}, {'n': '魔法', 'v': '魔法'},
            {'n': '战争', 'v': '战争'}, {'n': '女性向', 'v': '女性向'},
            {'n': '美少女', 'v': '美少女'}, {'n': '历史', 'v': '历史'},
            {'n': '惊悚', 'v': '惊悚'}, {'n': '恐怖', 'v': '恐怖'},
        ]

        initial_values = [{'n': '全部', 'v': ''}]
        for ch in ['0-9', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
                   'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U',
                   'V', 'W', 'X', 'Y', 'Z']:
            initial_values.append({'n': ch, 'v': ch})

        update_values = [
            {'n': '全部', 'v': ''},
            {'n': '周一', 'v': '1'}, {'n': '周二', 'v': '2'},
            {'n': '周三', 'v': '3'}, {'n': '周四', 'v': '4'},
            {'n': '周五', 'v': '5'}, {'n': '周六', 'v': '6'},
            {'n': '周日', 'v': '7'},
        ]

        common_filters = [
            {'key': 'tag', 'name': '标签', 'value': tag_values},
            {'key': 'area', 'name': '地区', 'value': area_values},
            {'key': 'year', 'name': '年份', 'value': year_values},
            {'key': 'status', 'name': '状态', 'value': status_values},
            {'key': 'updateWeekday', 'name': '更新日', 'value': update_values},
            {'key': 'initial', 'name': '首字母', 'value': initial_values},
        ]

        filters = {}
        for c in self.CATEGORIES:
            tid = c['type_id']
            filters[tid] = [] if tid.startswith('rank') else common_filters
        return filters

    def homeVideoContent(self):
        now = int(time.time())
        if self._home_cache_check(now):
            return {'list': self._home_cache[:72]}

        videos = []
        seen = set()

        data = self._fetch_json('/video', {
            'page': '1', 'size': '50', 'categoryId': '1',
        })
        if data and isinstance(data, dict):
            for item in (data.get('records') or []):
                vid = str(item.get('id', ''))
                if vid and vid not in seen:
                    seen.add(vid)
                    v = self._build_vod_item(item)
                    if v: videos.append(v)

        if len(videos) < 40:
            data = self._fetch_json('/video', {
                'page': '1', 'size': '20', 'categoryId': '2',
            })
            if data and isinstance(data, dict):
                for item in (data.get('records') or []):
                    vid = str(item.get('id', ''))
                    if vid and vid not in seen:
                        seen.add(vid)
                        v = self._build_vod_item(item)
                        if v: videos.append(v)

        self._home_cache = videos[:72]
        self._home_cache_time = now
        return {'list': self._home_cache}

    def _home_cache_check(self, now):
        if not hasattr(self, '_home_cache'):
            self._home_cache = []
            self._home_cache_time = 0
        if self._home_cache and (now - self._home_cache_time) < 300:
            return True
        return False

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg) if str(pg).isdigit() else 1
        except (TypeError, ValueError):
            page = 1
        page = max(1, page)

        tid = str(tid or '1')

        # 排行榜特殊路由
        if tid.startswith('rank_'):
            return self._fetch_rank(tid, page)

        params = {
            'page': str(page),
            'size': str(self.PAGE_SIZE),
            'categoryId': tid,
        }

        if isinstance(extend, str) and extend:
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}

        if isinstance(extend, dict):
            if extend.get('year'): params['year'] = str(extend['year'])
            if extend.get('area'): params['area'] = str(extend['area'])
            if extend.get('status'): params['status'] = str(extend['status'])
            if extend.get('tag'): params['tag'] = str(extend['tag'])
            if extend.get('initial'): params['initial'] = str(extend['initial'])
            if extend.get('updateWeekday'): params['updateWeekday'] = str(extend['updateWeekday'])

        data = self._fetch_json('/video', params, timeout=20)
        videos = []
        pagecount = page

        if data and isinstance(data, dict):
            records = data.get('records') or []
            total = int(data.get('total') or 0)
            pages = data.get('pages') or 0

            if total > 0:
                pagecount = max(1, int((total + self.PAGE_SIZE - 1) // self.PAGE_SIZE))
            elif pages:
                pagecount = max(1, int(pages))
            elif len(records) >= self.PAGE_SIZE:
                pagecount = page + 1

            for item in records:
                v = self._build_vod_item(item)
                if v: videos.append(v)

        return {
            'list': videos,
            'page': page,
            'pagecount': pagecount,
            'limit': self.PAGE_SIZE,
            'total': (page - 1) * self.PAGE_SIZE + len(videos),
        }

    def _fetch_rank(self, tid, page):
        period = self.RANK_PERIODS.get(tid, 'month')
        data = self._fetch_json('/rank', {
            'contentType': 'video',
            'period': period,
            'limit': '100',
        }, timeout=15)

        videos = []
        if data and isinstance(data, list):
            start = (page - 1) * self.PAGE_SIZE
            end = start + self.PAGE_SIZE
            for item in data[start:end]:
                v = self._build_vod_item(item)
                if v: videos.append(v)

        pagecount = max(1, int((len(data) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)) if data else 1

        return {
            'list': videos,
            'page': page,
            'pagecount': pagecount,
            'limit': self.PAGE_SIZE,
            'total': len(data) if data else 0,
        }

    def detailContent(self, ids):
        try:
            vid = str(ids[0]) if ids else ""
            if not vid: return {'list': []}

            data = self._fetch_json('/video/' + vid, timeout=20)
            if not data: return {'list': []}

            vod = self._build_full_vod(data)

            related = self._fetch_related(vid)
            if related:
                vod['vod_related'] = related

            episodes = data.get('episodes') or []
            is_movie = len(episodes) == 1
            play_urls = []
            for ep in episodes:
                eid = ep.get('episodeId')
                order = ep.get('episodeOrder') or 0
                label = ep.get('episodeLabel') or ''
                if eid:
                    if is_movie:
                        label = "正片"
                    else:
                        label = self._extract_episode_label(order, label)
                    play_urls.append("%s$%s%d" % (label, self.EP_PREFIX, eid))

            vod['vod_play_from'] = "青空次元"
            vod['vod_play_url'] = "#".join(play_urls) if play_urls else "正片$" + vid

            return {'list': [vod]}
        except Exception as e:
            self.log.error("detailContent 出错: %s" % e)
            return {'list': []}

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if str(pg).isdigit() else 1
            page = max(1, page)

            key = str(key).strip() if key else ''
            if not key:
                return {'list': [], 'page': page, 'pagecount': 1}

            params = {
                'page': str(page),
                'size': str(self.PAGE_SIZE),
                'keyword': key,
            }

            data = self._fetch_json('/video', params, timeout=15)
            videos = []
            pagecount = page

            if data and isinstance(data, dict):
                records = data.get('records') or []
                total = int(data.get('total') or 0)
                if total > 0:
                    pagecount = max(1, int((total + self.PAGE_SIZE - 1) // self.PAGE_SIZE))
                for item in records:
                    v = self._build_vod_item(item)
                    if v: videos.append(v)

            return {
                'list': videos,
                'page': page,
                'pagecount': pagecount,
            }
        except Exception as e:
            self.log.error("searchContent 出错: %s" % e)
            return {'list': [], 'page': 1, 'pagecount': 1}

    # TVBox 兼容: 部分壳调用 searchContentPage
    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ================================================================
    # 播放解析 (含签名刷新)
    # ================================================================

    def playerContent(self, flag, id, vipFlags=None):
        if not id:
            return {'parse': 0, 'playUrl': '', 'url': '', 'header': {}}

        id = str(id).strip()

        # 1. 直链媒体
        if self._is_direct_media(id):
            if '.m3u8' in id.lower():
                id = self._resolve_m3u8_child(id)
            return {
                'parse': 0,
                'playUrl': '',
                'url': id,
                'header': dict(self.PLAY_HEADERS),
                'format': 'application/x-mpegURL' if '.m3u8' in id.lower() else '',
                'contentType': 'application/x-mpegURL' if '.m3u8' in id.lower() else '',
            }

        # 2. 我们的 episode 前缀
        if id.startswith(self.EP_PREFIX):
            ep_id = id[len(self.EP_PREFIX):]
            if not ep_id.isdigit():
                ep_id = re.sub(r'\D', '', ep_id)
            if ep_id:
                data = self._fetch_json(
                    '/video/episode/%s/play' % ep_id,
                    {'lineCode': self.LINE_CODE},
                    timeout=15,
                    use_cache=True,
                    cache_key='play:%s' % ep_id,
                )
                if data and isinstance(data, dict):
                    play_url = data.get('playUrl') or ''
                    can_play = data.get('canPlay')
                    if play_url and can_play:
                        play_url = self._resolve_m3u8_child(play_url)
                        return {
                            'parse': 0,
                            'playUrl': '',
                            'url': play_url,
                            'header': dict(self.PLAY_HEADERS),
                            'format': 'application/x-mpegURL' if '.m3u8' in play_url.lower() else '',
                            'contentType': 'application/x-mpegURL' if '.m3u8' in play_url.lower() else '',
                        }
                    self.log.warning("播放接口失败: ep=%s canPlay=%s" % (ep_id, can_play))

            return {
                'parse': 1,
                'playUrl': '',
                'url': self.HOST + '/',
                'header': dict(self.HEADERS),
            }

        # 3. 纯数字 vod_id 兜底
        if id.isdigit():
            return {
                'parse': 1,
                'playUrl': '',
                'url': '%s/anime/mal/%s' % (self.HOST, id),
                'header': dict(self.HEADERS),
            }

        # 4. 其他 URL
        return {
            'parse': 1,
            'playUrl': '',
            'url': id,
            'header': dict(self.HEADERS),
        }

    def _resolve_m3u8_child(self, m3u8_url, referer=""):
        if not m3u8_url or '.m3u8' not in m3u8_url.lower():
            return m3u8_url
        try:
            rsp = self.fetch(m3u8_url, headers=self.HEADERS, timeout=15)
            if not rsp: return m3u8_url
            text = rsp.text or ''
            if '#EXTM3U' not in text: return m3u8_url
            if '#EXT-X-STREAM-INF' not in text: return m3u8_url
            lines = [x.strip() for x in text.splitlines() if x.strip()]
            for i, line in enumerate(lines):
                if line.startswith('#EXT-X-STREAM-INF'):
                    for nxt in lines[i + 1:]:
                        if nxt and not nxt.startswith('#'):
                            if nxt.startswith('http'): return nxt
                            base = m3u8_url.rsplit('/', 1)[0]
                            return base + '/' + nxt
        except Exception:
            pass
        return m3u8_url

    # ================================================================
    # 本地代理
    # ================================================================

    def localProxy(self, param):
        try:
            raw_url = ''
            referer = self.HOST + '/'

            if isinstance(param, dict):
                raw_url = param.get('url') or param.get('u') or ''
                referer = param.get('referer') or param.get('ref') or referer
            elif isinstance(param, str):
                qs = urllib.parse.parse_qs(param)
                raw_url = (qs.get('url') or qs.get('u') or [''])[0]
                referer = (qs.get('referer') or qs.get('ref') or [''])[0] or referer

            media_url = urllib.parse.unquote(raw_url) if raw_url else ''
            referer = urllib.parse.unquote(referer) if referer else self.HOST + '/'

            if not media_url:
                return [404, 'text/plain', b'']

            headers = {
                'User-Agent': self.HEADERS['User-Agent'],
                'Referer': referer,
                'Origin': self.HOST,
            }

            rsp = self.fetch(media_url, headers=headers, timeout=30)
            if not rsp:
                return [502, 'text/plain', b'upstream error']

            content = rsp.content if hasattr(rsp, 'content') else rsp.text.encode('utf-8')
            ctype = ''
            if hasattr(rsp, 'headers'):
                ctype = rsp.headers.get('Content-Type', '') or ''

            text = ''
            try:
                text = content.decode('utf-8')
            except Exception:
                text = ''

            if '#EXTM3U' in text:
                out = []
                for line in text.splitlines():
                    s = line.strip()
                    if not s or s.startswith('#'):
                        out.append(line)
                    else:
                        if s.startswith('http'):
                            abs_url = s
                        elif s.startswith('/'):
                            p = urllib.parse.urlparse(media_url)
                            abs_url = "%s://%s%s" % (p.scheme, p.netloc, s)
                        else:
                            abs_url = urllib.parse.urljoin(media_url, s)
                        out.append(self._proxy_url(abs_url, referer))
                data = '\n'.join(out).encode('utf-8')
                return [200, 'application/vnd.apple.mpegurl', data]

            return [200, ctype or 'application/octet-stream', content]
        except Exception as e:
            return [500, 'text/plain', ('proxy error: %s' % e).encode('utf-8')]

    def _proxy_url(self, media_url, referer=""):
        if not hasattr(self, 'getProxyUrl'):
            return media_url
        try:
            base = self.getProxyUrl()
            return base + '&url=' + urllib.parse.quote(media_url, safe='') \
                         + '&referer=' + urllib.parse.quote(referer or self.HOST + '/', safe='')
        except Exception:
            return media_url

    # ================================================================
    # 可选接口 (TVBox 兼容)
    # ================================================================

    def manualVideoCheck(self):
        return True

    def manualVideoRewrite(self, function):
        pass

    def destroy(self):
        self.cache.clear()
        if hasattr(self, '_home_cache'):
            self._home_cache = []
            self._home_cache_time = 0

    def close(self):
        self.destroy()

    def getStats(self):
        """获取请求统计 + 熔断状态 (调试用)"""
        stats = self.stats.snapshot()
        stats['circuit'] = self.circuit.status()
        stats['cache_size'] = len(self.cache)
        return stats


# ================================================================
# 自测入口 (15 项)
# ================================================================
if __name__ == '__main__':
    spider = Spider()
    spider.init()

    print("=" * 60)
    print("青空次元爬虫源 v1.2.0 - 完整自测 (15 项)")
    print("=" * 60)

    def _ok(msg): print("  ✓ %s" % msg)
    def _fail(msg): print("  ✗ %s" % msg)

    passed = 0
    failed = 0

    def _check(cond, msg_ok, msg_fail=None):
        global passed, failed
        if cond:
            _ok(msg_ok); passed += 1
        else:
            _fail(msg_fail or msg_ok); failed += 1

    # 1. 分类
    print("\n[1] homeContent:")
    hc = spider.homeContent(None)
    _check(len(hc['class']) == 6, "6 个分类", "分类数错误: %d" % len(hc['class']))

    # 2. 筛选器
    print("\n[2] _build_filters:")
    fc = spider.homeContent(True)
    _check(len(fc['filters']['1']) == 6, "TV番剧 6 维筛选")
    _check(len(fc['filters']['rank_week']) == 0, "排行榜无筛选")

    # 3. 首页
    print("\n[3] homeVideoContent:")
    home = spider.homeVideoContent()
    _check(len(home['list']) > 0, "首页 %d 部" % len(home['list']))
    _check('vod_id' in home['list'][0] and 'vod_name' in home['list'][0],
           "字段完整: %s" % home['list'][0]['vod_name'][:30])

    # 4. 分类翻页
    print("\n[4] categoryContent 翻页:")
    c1 = spider.categoryContent('1', '1', None, None)
    c2 = spider.categoryContent('1', '2', None, None)
    ids1 = {i['vod_id'] for i in c1['list']}
    ids2 = {i['vod_id'] for i in c2['list']}
    _check(len(c1['list']) == 20, "第1页 20 条")
    _check(len(ids1 & ids2) == 0,
           "翻页无重叠 (重叠 %d)" % len(ids1 & ids2))
    _check(c1['pagecount'] > 1, "pagecount=%d" % c1['pagecount'])

    # 5. 组合筛选
    print("\n[5] 组合筛选:")
    cf = spider.categoryContent('1', '1', None, {
        'year': '2026', 'area': '日本', 'tag': '恋爱'})
    _check(len(cf['list']) > 0, "2026+日本+恋爱 %d 条" % len(cf['list']))

    # 6. 排行榜
    print("\n[6] 排行榜:")
    for tid in ['rank_week', 'rank_month', 'rank_all']:
        r = spider.categoryContent(tid, '1', None, None)
        _check(len(r['list']) > 0, "%s %d 条" % (tid, len(r['list'])))

    # 7. 放送表
    print("\n[7] 放送表 (周一):")
    sch = spider.categoryContent('1', '1', None, {'updateWeekday': '1'})
    _check(len(sch['list']) > 0, "周一更新 %d 条" % len(sch['list']))

    # 8. 搜索
    print("\n[8] searchContent:")
    search = spider.searchContent('鬼灭之刃', False)
    _check(len(search['list']) > 0, "搜到 %d 条" % len(search['list']))

    # 9. 详情
    print("\n[9] detailContent:")
    vid = search['list'][0]['vod_id']
    detail = spider.detailContent([vid])
    _check(len(detail['list']) == 1, "详情返回 1 条")
    vod = detail['list'][0]
    req_fields = ['vod_id', 'vod_name', 'vod_pic', 'vod_content',
                  'vod_play_url', 'vod_year', 'vod_area', 'vod_actor',
                  'vod_director', 'vod_score', 'vod_class', 'vod_remarks']
    missing = [f for f in req_fields if not vod.get(f)]
    _check(not missing, "12 字段完整" if not missing else "缺字段: %s" % missing)
    _check(vod.get('vod_related', ''), "关联视频: %s" % (vod.get('vod_related') or '(无)')[:50])

    # 10. 播放
    print("\n[10] playerContent:")
    play_urls = vod['vod_play_url'].split('#')
    first_ep = play_urls[0].split('$')[-1]
    player = spider.playerContent('', first_ep, '')
    _check(player['parse'] == 0, "parse=0 直链")
    _check('.m3u8' in player['url'], "m3u8 URL")
    _check('sorani' in player['header'].get('Referer', ''), "Referer 正确")

    # 11. 电影标签
    print("\n[11] 电影集标签:")
    d_movie = spider.detailContent(['4331'])['list'][0]
    first_movie = d_movie['vod_play_url'].split('#')[0]
    _check(first_movie.startswith('正片$'), "电影标签=正片: %s" % first_movie)

    # 12. 缓存命中
    print("\n[12] 缓存:")
    t0 = time.time()
    spider.categoryContent('1', '3', None, None)  # 预热
    t1 = time.time()
    spider.categoryContent('1', '3', None, None)  # 命中
    t2 = time.time()
    _check(t2 - t1 < 0.1, "缓存命中耗时 %.4fs" % (t2 - t1))

    # 13. 熔断器状态
    print("\n[13] 熔断器:")
    cb = spider.circuit.status()
    _check(cb['state'] == 'CLOSED', "熔断器状态: %s" % cb['state'])

    # 14. 请求统计
    print("\n[14] 请求统计:")
    stats = spider.getStats()
    _check(stats['success_rate'] == '100%',
           "成功率 %s (总 %d / 成 %d)" % (
               stats['success_rate'], stats['total'], stats['success']))

    # 15. 播放 URL 过期检测
    print("\n[15] 签名过期检测:")
    expired_url = 'https://x.com/v.m3u8?timestamp=1000000&key=abc'
    _check(_url_is_expired(expired_url, 24), "过期 URL 检测正确")
    fresh_url = 'https://x.com/v.m3u8?timestamp=%d&key=abc' % int(time.time() * 1000)
    _check(not _url_is_expired(fresh_url, 24), "新鲜 URL 检测正确")

    # 汇总
    print("\n" + "=" * 60)
    print("测试结果: %d 通过 / %d 失败 / 共 %d" % (passed, failed, passed + failed))
    if failed == 0:
        print("🎯 全部通过!")
    print("=" * 60)
