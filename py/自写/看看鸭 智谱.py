#!/usr/bin/env python3
# 看看鸭 www.kankanya.me TVBox T4 爬虫源
# 特征: MacCMS v10 + MXOne 模板; jsjiami v7 混淆 kkyplayer 播放器
# 过墙: 自定义字母表加密(url+token) POST /robot.php 取 cookie
# 播放: /play/{id}-{sid}-{nid}.html -> player_aaaa.url(vid)
#       -> POST /kkyplayer/api.php {vid} -> {url,urlmode}
#       urlmode=1: std_b64 -> md5("test")循环XOR -> std_b64 -> parts[0]/[1]字母表JSON -> A[B.index(ch)]映射
#       urlmode=2: 自定义字母表b64 -> 步长3去随机填充位 -> 字母表-3还原
# 筛选: /show/{tid}-{area}-{by}-{class}-{lang}-{letter}-{-}-{?}-{page}-{?}-{?}-{year}.html (12段)
import json
import re
import hashlib
import base64
import random
from urllib.parse import urljoin, quote
import requests
from base.spider import Spider


class Spider(Spider):

    def getName(self):
        return "看看鸭"

    def init(self, extend=""):
        self.name = "看看鸭"
        self.host = "https://www.kankanya.me"
        self.ua = "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        self.headers = {"User-Agent": self.ua, "Referer": self.host + "/"}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.categories = [
            {"type_id": "dianying", "type_name": "电影"},
            {"type_id": "juji", "type_name": "剧集"},
            {"type_id": "zongyi", "type_name": "综艺"},
            {"type_id": "dongman", "type_name": "动漫"},
        ]
        self._waf_alphabet = "PXhw7UT1B0a9kQDKZsjIASmOezxYG4CHo5Jyfg2b8FLpEvRr3WtVnlqMidu6cN"
        self._filters = json.loads(FILTERS_JSON)

    # ---------- 基础请求 ----------

    def _waf_encode(self, text):
        alpha = self._waf_alphabet
        out = ""
        for c in text:
            idx = alpha.find(c)
            code = c if idx == -1 else alpha[(idx + 3) % 62]
            out += alpha[random.randrange(62)] + code + alpha[random.randrange(62)]
        return base64.b64encode(out.encode("utf-8")).decode("utf-8")

    def _get(self, url):
        try:
            r = self.session.get(url, headers=self.headers, timeout=15, verify=False)
            r.encoding = "utf-8"
            if "人机验证" not in r.text:
                return r.text
            m = re.search(r'var token\s*=\s*encrypt\("([^"]+)"\)', r.text)
            if not m:
                return ""
            token = m.group(1)
            self.session.post(
                self.host + "/robot.php",
                data={"value": self._waf_encode(url), "token": self._waf_encode(token)},
                headers={**self.headers, "Content-Type": "application/x-www-form-urlencoded",
                         "Referer": url},
                timeout=15, verify=False)
            r = self.session.get(url, headers=self.headers, timeout=15, verify=False)
            r.encoding = "utf-8"
            return r.text if "人机验证" not in r.text else ""
        except Exception:
            return ""

    def _post(self, url, data, xhr=False):
        try:
            h = self.headers
            if xhr:
                h = {**self.headers, "X-Requested-With": "XMLHttpRequest"}
            r = self.session.post(url, data=data, headers=h, timeout=15, verify=False)
            r.encoding = "utf-8"
            return r.text
        except Exception:
            return ""

    def _fix(self, url):
        return urljoin(self.host + "/", url or "")

    # ---------- 解析工具 ----------

    def _poster_list(self, html):
        """解析 module-poster-item 列表块"""
        out = []
        seen = set()
        blocks = re.split(r'<a\s+href="(/detail/[^"]+)"', html)
        for i in range(1, len(blocks) - 1, 2):
            path = blocks[i]
            blk = blocks[i + 1][:1200]
            m = re.search(r'title="([^"]+)"', blk)
            if not m:
                m = re.search(r'module-poster-item-title">([^<]+)<', blk)
            name = m.group(1).strip() if m else ""
            pic = re.search(r'data-original="([^"]+)"', blk)
            vod_id = path[len("/detail/"):-len(".html")]
            if not name or vod_id in seen:
                continue
            seen.add(vod_id)
            out.append({"vod_id": vod_id, "vod_name": name,
                        "vod_pic": self._fix(pic.group(1)) if pic else ""})
        return out

    def _field(self, html, label):
        m = re.search(r'module-info-item-title">\s*' + label + r'：?\s*</span>\s*<div class="module-info-item-content">(.*?)</div>', html, re.S)
        if not m:
            return ""
        text = re.sub(r'<[^>]+>', '/', m.group(1))
        text = re.sub(r'/+', '/', text).strip(' /')
        return text

    # ---------- 解密 ----------

    def _js_b64(self, s):
        """JS Base64.decode 语义: 逐字符 charCodeAt(i)&0xff 为字节流"""
        raw = bytes(ord(c) & 0xFF for c in s)
        raw = raw + b"=" * (-len(raw) % 4)
        return base64.b64decode(raw)

    def _decode_sign(self, value):
        """urlmode=1: b64 -> md5(test) XOR -> b64 -> parts[0]/[1]字母表 -> A[B.index(ch)]"""
        key = hashlib.md5(b"test").hexdigest()
        raw = self._js_b64(value)
        code = "".join(chr(b ^ ord(key[i % len(key)])) for i, b in enumerate(raw))
        mid = self._js_b64(code).decode("utf-8", "replace")
        parts = mid.split("/")
        if len(parts) < 3:
            return ""
        try:
            a = json.loads(self._js_b64(parts[0]).decode("utf-8", "replace"))
            b = json.loads(self._js_b64(parts[1]).decode("utf-8", "replace"))
        except Exception:
            return ""
        payload = self._js_b64("/".join(parts[2:])).decode("utf-8", "replace")
        out = ""
        for ch in payload:
            if ch.isascii() and ch.isalpha() and ch in b:
                idx = b.index(ch)
                out += a[idx] if idx < len(a) else ch
            else:
                out += ch
        return out

    def _decode2(self, value):
        """urlmode=2: 自定义字母表b64 -> 步长3去随机填充 -> 字母表-3还原"""
        s = self._js_b64(value).decode("utf-8", "replace")
        alpha = self._waf_alphabet
        out = ""
        for i in range(1, len(s), 3):
            idx = alpha.find(s[i])
            out += s[i] if idx < 0 else alpha[(idx + 0x3B) % 0x3E]
        return out

    # ---------- 六接口 ----------

    def homeContent(self, filter):
        result = {"class": self.categories, "list": []}
        if filter:
            result["filters"] = self._filters
        html = self._get(self.host + "/")
        if html:
            result["list"] = self._poster_list(html)
        return result

    def homeVideoContent(self):
        html = self._get(self.host + "/")
        return {"list": self._poster_list(html)}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg)
        # URL 段: tid-1:area-2:by-3:class-4:lang-5:letter-6:-7:-8:page-9:-10:-11:year
        seg = [""] * 12
        seg[0] = tid
        seg_map = {"area": 1, "by": 2, "class": 3, "lang": 4, "letter": 5, "year": 11}
        for k, v in (extend or {}).items():
            if k in seg_map and v:
                seg[seg_map[k]] = quote(v, safe="")
        seg[8] = str(pg)
        url = self.host + "/show/" + "-".join(seg) + ".html"
        html = self._get(url)
        vlist = self._poster_list(html)
        pagecount = pg
        m = re.search(r'href="(/show/[^"]+\.html)"[^>]*title="尾页"', html)
        if m:
            try:
                pagecount = max(pg, int(m.group(1).split("/")[-1][:-len(".html")].split("-")[8]))
            except Exception:
                pagecount = pg
        elif vlist:
            pagecount = pg
        return {"list": vlist, "page": pg, "pagecount": pagecount,
                "limit": len(vlist), "total": pagecount * 30}

    def detailContent(self, ids):
        did = ids[0]
        html = self._get(self.host + "/detail/" + did + ".html")
        if not html:
            return {"list": [{"vod_id": did}]}
        m = re.search(r'<h1>([^<]+)</h1>', html)
        name = m.group(1).strip() if m else did
        pic = re.search(r'module-poster-bg.*?data-original="([^"]+)"', html, re.S)
        tags = re.findall(r'module-info-tag-link[^>]*>\s*(?:<a[^>]*>([^<]+)</a>|<a[^>]*>([^<]+)</a>)', html)
        year = area = vclass = ""
        tag_links = re.findall(r'<div class="module-info-tag-link">(.*?)</div>', html, re.S)
        for idx, blk in enumerate(tag_links[:3]):
            vals = [x.strip() for x in re.findall(r'<a[^>]*>([^<]+)</a>', blk)]
            joined = "/".join(vals)
            if idx == 0:
                year = vals[0] if vals else ""
            elif idx == 1:
                area = joined
            elif idx == 2:
                vclass = joined
        intro = re.search(r'module-info-introduction-content">\s*<p>(.*?)</p>', html, re.S)
        director = self._field(html, "导演")
        actor = self._field(html, "主演")
        remarks = self._field(html, "备注")
        # 线路名(data-dropdown-value)与选集面板按顺序一一对应
        line_names = re.findall(r'data-dropdown-value="([^"]+)"', html.split("选集播放")[-1].split("相关推荐")[0])
        panels = re.findall(r'module-play-list-content[^"]*">(.*?)</div>\s*</div>', html, re.S)
        if not panels:
            panels = re.findall(r'module-play-list-content[^"]*">(.*?)</div>', html, re.S)
        plays = []
        for si, panel in enumerate(panels):
            eps = re.findall(r'<a\s+class="module-play-list-link"\s+href="/play/([^"]+?)\.html"[^>]*>\s*<span>([^<]+)</span>', panel)
            if not eps:
                continue
            line = line_names[si] if si < len(line_names) else "线路" + str(si + 1)
            urls = "#".join(n + "$" + e for e, n in eps)
            plays.append(line + "$$$" + urls)
        vod = {
            "vod_id": did,
            "vod_name": name,
            "vod_pic": self._fix(pic.group(1)) if pic else "",
            "type_name": vclass,
            "vod_year": year,
            "vod_area": area,
            "vod_remarks": remarks,
            "vod_actor": actor,
            "vod_director": director,
            "vod_content": re.sub(r'\s+', ' ', intro.group(1)).strip() if intro else "",
        }
        if plays:
            vod["vod_play_from"] = "$$$".join(p.split("$$$")[0] for p in plays)
            vod["vod_play_url"] = "$$$".join(p.split("$$$")[1] for p in plays)
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        url = self.host + "/search/" + quote(key, safe="") + "-------------.html"
        html = self._get(url)
        out = []
        seen = set()
        blocks = re.split(r'<a href="(/detail/[^"]+)" class="module-card-item-poster">', html)
        for i in range(1, len(blocks) - 1, 2):
            path = blocks[i]
            blk = blocks[i + 1][:1500]
            vod_id = path[len("/detail/"):-len(".html")]
            if vod_id in seen:
                continue
            m = re.search(r'module-card-item-title">\s*<a[^>]*>(?:<strong>)?([^<]+)', blk)
            pic = re.search(r'data-original="([^"]+)"', blk)
            info = re.search(r'module-info-item-content">([^<]+)<', blk)
            if not m:
                continue
            seen.add(vod_id)
            out.append({"vod_id": vod_id, "vod_name": m.group(1).strip(),
                        "vod_pic": self._fix(pic.group(1)) if pic else "",
                        "vod_remarks": info.group(1).strip() if info else ""})
        return {"list": out, "page": int(pg)}

    def playerContent(self, flag, id, vipFlags):
        play_url = self.host + "/play/" + id + ".html"
        html = self._get(play_url)
        result = {"parse": "1", "playUrl": "", "url": "", "header": self.headers}
        pd = self._extract_player(html)
        if not pd:
            return result
        vid = pd.get("url", "")
        if not vid:
            return result
        api_resp = self._post(self.host + "/kkyplayer/api.php", {"vid": vid}, xhr=True)
        try:
            data = json.loads(api_resp)["data"]
        except Exception:
            return result
        mode = data.get("urlmode")
        url = ""
        try:
            url = self._decode_sign(data["url"]) if mode == 1 else (self._decode2(data["url"]) if mode == 2 else "")
        except Exception:
            url = ""
        if not url:
            return result
        url = url.replace("&amp;", "&")
        result["parse"] = "0"
        result["url"] = url
        return result

    def _extract_player(self, html):
        """花括号配平提取 player_aaaa JSON(含嵌套vod_data)"""
        m = re.search(r'var player_aaaa\s*=\s*', html)
        if not m:
            return None
        i = m.end()
        while i < len(html) and html[i] != "{":
            i += 1
        depth = 0
        for j in range(i, len(html)):
            if html[j] == "{":
                depth += 1
            elif html[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[i:j + 1])
                    except Exception:
                        return None
        return None

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(?:m3u8|mp4)(?:$|[?#])', url, re.I))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return [200, "text/plain", "", ""]


FILTERS_JSON = r'''{"dianying":[{"key":"year","name":"年份","value":[{"n":"全部","v":""},{"n":"2026","v":"2026"},{"n":"2025","v":"2025"},{"n":"2024","v":"2024"},{"n":"2023","v":"2023"},{"n":"2022","v":"2022"},{"n":"2021","v":"2021"},{"n":"2020","v":"2020"},{"n":"2019","v":"2019"},{"n":"2018","v":"2018"},{"n":"2017","v":"2017"},{"n":"2016","v":"2016"},{"n":"2015","v":"2015"},{"n":"2014","v":"2014"},{"n":"2013","v":"2013"},{"n":"2012","v":"2012"},{"n":"2011","v":"2011"},{"n":"2010","v":"2010"}]},{"key":"letter","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"B","v":"B"},{"n":"C","v":"C"},{"n":"D","v":"D"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"},{"n":"0-9","v":"0"}]},{"key":"lang","name":"语言","value":[{"n":"全部","v":""},{"n":"国语","v":"国语"},{"n":"英语","v":"英语"},{"n":"粤语","v":"粤语"},{"n":"闽南语","v":"闽南语"},{"n":"韩语","v":"韩语"},{"n":"日语","v":"日语"},{"n":"法语","v":"法语"},{"n":"德语","v":"德语"},{"n":"其它","v":"其它"}]},{"key":"class","name":"剧情","value":[{"n":"全部","v":""},{"n":"喜剧","v":"喜剧"},{"n":"爱情","v":"爱情"},{"n":"恐怖","v":"恐怖"},{"n":"动作","v":"动作"},{"n":"科幻","v":"科幻"},{"n":"剧情","v":"剧情"},{"n":"战争","v":"战争"},{"n":"警匪","v":"警匪"},{"n":"犯罪","v":"犯罪"},{"n":"动画","v":"动画"},{"n":"奇幻","v":"奇幻"},{"n":"武侠","v":"武侠"},{"n":"冒险","v":"冒险"},{"n":"枪战","v":"枪战"},{"n":"恐怖","v":"恐怖"},{"n":"悬疑","v":"悬疑"},{"n":"惊悚","v":"惊悚"},{"n":"经典","v":"经典"},{"n":"青春","v":"青春"},{"n":"文艺","v":"文艺"},{"n":"微电影","v":"微电影"},{"n":"古装","v":"古装"},{"n":"历史","v":"历史"},{"n":"运动","v":"运动"},{"n":"农村","v":"农村"},{"n":"儿童","v":"儿童"},{"n":"网络电影","v":"网络电影"}]},{"key":"by","name":"排序","value":[{"n":"默认","v":""},{"n":"最近更新","v":"time"},{"n":"人气","v":"hits"},{"n":"评分","v":"score"}]},{"key":"area","name":"地区","value":[{"n":"全部","v":""},{"n":"大陆","v":"大陆"},{"n":"香港","v":"香港"},{"n":"台湾","v":"台湾"},{"n":"美国","v":"美国"},{"n":"法国","v":"法国"},{"n":"英国","v":"英国"},{"n":"日本","v":"日本"},{"n":"韩国","v":"韩国"},{"n":"德国","v":"德国"},{"n":"泰国","v":"泰国"},{"n":"印度","v":"印度"},{"n":"意大利","v":"意大利"},{"n":"西班牙","v":"西班牙"},{"n":"加拿大","v":"加拿大"},{"n":"其他","v":"其他"}]}],"juji":[{"key":"year","name":"年份","value":[{"n":"全部","v":""},{"n":"2026","v":"2026"},{"n":"2025","v":"2025"},{"n":"2024","v":"2024"},{"n":"2023","v":"2023"},{"n":"2022","v":"2022"},{"n":"2021","v":"2021"},{"n":"2020","v":"2020"},{"n":"2019","v":"2019"},{"n":"2018","v":"2018"},{"n":"2017","v":"2017"},{"n":"2016","v":"2016"},{"n":"2015","v":"2015"},{"n":"2014","v":"2014"},{"n":"2013","v":"2013"},{"n":"2012","v":"2012"},{"n":"2011","v":"2011"},{"n":"2010","v":"2010"},{"n":"2009","v":"2009"},{"n":"2008","v":"2008"},{"n":"2006","v":"2006"},{"n":"2005","v":"2005"},{"n":"2004","v":"2004"}]},{"key":"letter","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"B","v":"B"},{"n":"C","v":"C"},{"n":"D","v":"D"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"},{"n":"0-9","v":"0"}]},{"key":"lang","name":"语言","value":[{"n":"全部","v":""},{"n":"国语","v":"国语"},{"n":"英语","v":"英语"},{"n":"粤语","v":"粤语"},{"n":"闽南语","v":"闽南语"},{"n":"韩语","v":"韩语"},{"n":"日语","v":"日语"},{"n":"其它","v":"其它"}]},{"key":"class","name":"剧情","value":[{"n":"全部","v":""},{"n":"古装","v":"古装"},{"n":"战争","v":"战争"},{"n":"青春偶像","v":"青春偶像"},{"n":"喜剧","v":"喜剧"},{"n":"家庭","v":"家庭"},{"n":"犯罪","v":"犯罪"},{"n":"动作","v":"动作"},{"n":"奇幻","v":"奇幻"},{"n":"剧情","v":"剧情"},{"n":"历史","v":"历史"},{"n":"经典","v":"经典"},{"n":"乡村","v":"乡村"},{"n":"情景","v":"情景"},{"n":"商战","v":"商战"},{"n":"网剧","v":"网剧"},{"n":"其他","v":"其他"}]},{"key":"by","name":"排序","value":[{"n":"默认","v":""},{"n":"最近更新","v":"time"},{"n":"人气","v":"hits"},{"n":"评分","v":"score"}]},{"key":"area","name":"地区","value":[{"n":"全部","v":""},{"n":"内地","v":"内地"},{"n":"韩国","v":"韩国"},{"n":"香港","v":"香港"},{"n":"台湾","v":"台湾"},{"n":"日本","v":"日本"},{"n":"美国","v":"美国"},{"n":"泰国","v":"泰国"},{"n":"英国","v":"英国"},{"n":"新加坡","v":"新加坡"},{"n":"其他","v":"其他"}]}],"zongyi":[{"key":"year","name":"年份","value":[{"n":"全部","v":""},{"n":"2026","v":"2026"},{"n":"2025","v":"2025"},{"n":"2024","v":"2024"},{"n":"2023","v":"2023"},{"n":"2022","v":"2022"},{"n":"2021","v":"2021"},{"n":"2020","v":"2020"},{"n":"2019","v":"2019"},{"n":"2018","v":"2018"},{"n":"2017","v":"2017"},{"n":"2016","v":"2016"},{"n":"2015","v":"2015"},{"n":"2014","v":"2014"},{"n":"2013","v":"2013"},{"n":"2012","v":"2012"},{"n":"2011","v":"2011"},{"n":"2010","v":"2010"},{"n":"2009","v":"2009"},{"n":"2008","v":"2008"},{"n":"2007","v":"2007"},{"n":"2006","v":"2006"},{"n":"2005","v":"2005"},{"n":"2004","v":"2004"}]},{"key":"letter","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"B","v":"B"},{"n":"C","v":"C"},{"n":"D","v":"D"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"},{"n":"0-9","v":"0"}]},{"key":"lang","name":"语言","value":[{"n":"全部","v":""},{"n":"国语","v":"国语"},{"n":"英语","v":"英语"},{"n":"粤语","v":"粤语"},{"n":"闽南语","v":"闽南语"},{"n":"韩语","v":"韩语"},{"n":"日语","v":"日语"},{"n":"其它","v":"其它"}]},{"key":"class","name":"剧情","value":[{"n":"全部","v":""},{"n":"选秀","v":"选秀"},{"n":"情感","v":"情感"},{"n":"访谈","v":"访谈"},{"n":"播报","v":"播报"},{"n":"旅游","v":"旅游"},{"n":"音乐","v":"音乐"},{"n":"美食","v":"美食"},{"n":"纪实","v":"纪实"},{"n":"曲艺","v":"曲艺"},{"n":"生活","v":"生活"},{"n":"游戏互动","v":"游戏互动"},{"n":"财经","v":"财经"},{"n":"求职","v":"求职"}]},{"key":"by","name":"排序","value":[{"n":"默认","v":""},{"n":"最近更新","v":"time"},{"n":"人气","v":"hits"},{"n":"评分","v":"score"}]},{"key":"area","name":"地区","value":[{"n":"全部","v":""},{"n":"内地","v":"内地"},{"n":"港台","v":"港台"},{"n":"日韩","v":"日韩"},{"n":"欧美","v":"欧美"}]}],"dongman":[{"key":"year","name":"年份","value":[{"n":"全部","v":""},{"n":"2026","v":"2026"},{"n":"2025","v":"2025"},{"n":"2024","v":"2024"},{"n":"2023","v":"2023"},{"n":"2022","v":"2022"},{"n":"2021","v":"2021"},{"n":"2020","v":"2020"},{"n":"2019","v":"2019"},{"n":"2018","v":"2018"},{"n":"2017","v":"2017"},{"n":"2016","v":"2016"},{"n":"2015","v":"2015"},{"n":"2014","v":"2014"},{"n":"2013","v":"2013"},{"n":"2012","v":"2012"},{"n":"2011","v":"2011"},{"n":"2010","v":"2010"},{"n":"2009","v":"2009"},{"n":"2008","v":"2008"},{"n":"2007","v":"2007"},{"n":"2006","v":"2006"},{"n":"2005","v":"2005"},{"n":"2004","v":"2004"}]},{"key":"letter","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"B","v":"B"},{"n":"C","v":"C"},{"n":"D","v":"D"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"},{"n":"0-9","v":"0"}]},{"key":"lang","name":"语言","value":[{"n":"全部","v":""},{"n":"国语","v":"国语"},{"n":"英语","v":"英语"},{"n":"粤语","v":"粤语"},{"n":"闽南语","v":"闽南语"},{"n":"韩语","v":"韩语"},{"n":"日语","v":"日语"},{"n":"其它","v":"其它"}]},{"key":"class","name":"剧情","value":[{"n":"全部","v":""},{"n":"情感","v":"情感"},{"n":"科幻","v":"科幻"},{"n":"热血","v":"热血"},{"n":"推理","v":"推理"},{"n":"搞笑","v":"搞笑"},{"n":"冒险","v":"冒险"},{"n":"萝莉","v":"萝莉"},{"n":"校园","v":"校园"},{"n":"动作","v":"动作"},{"n":"机战","v":"机战"},{"n":"运动","v":"运动"},{"n":"战争","v":"战争"},{"n":"少年","v":"少年"},{"n":"少女","v":"少女"},{"n":"社会","v":"社会"},{"n":"原创","v":"原创"},{"n":"亲子","v":"亲子"},{"n":"益智","v":"益智"},{"n":"励志","v":"励志"},{"n":"其他","v":"其他"}]},{"key":"by","name":"排序","value":[{"n":"默认","v":""},{"n":"最近更新","v":"time"},{"n":"人气","v":"hits"},{"n":"评分","v":"score"}]},{"key":"area","name":"地区","value":[{"n":"全部","v":""},{"n":"国产","v":"国产"},{"n":"日本","v":"日本"},{"n":"欧美","v":"欧美"},{"n":"其他","v":"其他"}]}]}
'''
