"""
政策采集爬虫核心模块 v3
- 支持静态+动态(Playwright)页面采集
- 国家+福建省+各地市政策源
- 关键词过滤 + 日期范围过滤（2025-2026）
- PDF附件下载 + 增量采集（去重）
- 输出格式匹配用户案例
"""

import os, re, sys, time, json, hashlib, logging
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import Optional

import requests, yaml
from bs4 import BeautifulSoup

# Playwright for dynamic pages
_PLAYWRIGHT = False
try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT = True
except ImportError:
    pass

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"collector_{datetime.now().strftime('%Y%m%d')}.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
PDF_DIR = OUTPUT_DIR / "pdfs"
DATA_DIR = OUTPUT_DIR / "data"
VISITED_FILE = DATA_DIR / "visited_urls.json"
for d in [OUTPUT_DIR, PDF_DIR, DATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
})
SESSION.timeout = 30

# 需要动态渲染的域名
DYNAMIC_DOMAINS = ['nea.gov.cn', 'ndrc.gov.cn']

# --- 工具函数 ---

def load_config():
    with open(PROJECT_ROOT / "config" / "sources.yaml", 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def load_visited_urls():
    if VISITED_FILE.exists():
        with open(VISITED_FILE, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()

def save_visited_urls(urls):
    with open(VISITED_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(urls), f, ensure_ascii=False)

def load_policy_index():
    f = DATA_DIR / "policy_index.json"
    if f.exists():
        with open(f, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    return {}

def save_policy_index(idx):
    with open(DATA_DIR / "policy_index.json", 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)

def normalize_url(url, base_url):
    if not url: return ""
    url = url.strip()
    if url.startswith("//"): url = "https:" + url
    elif url.startswith("/"): url = urljoin(base_url, url)
    elif not url.startswith("http"): url = urljoin(base_url + "/", url)
    return url

def extract_date(text):
    if not text: return None
    for pat in [r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', r'(\d{4}年\d{1,2}月\d{1,2}日)']:
        m = re.search(pat, text.strip())
        if m:
            ds = m.group(1)
            if '年' in ds: ds = ds.replace('年','-').replace('月','-').replace('日','')
            parts = re.split(r'[-/]', ds)
            if len(parts) == 3:
                return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    return None

def matches_keywords(text, keywords):
    if not text: return False
    t = text.lower()
    return any(kw.lower() in t for kw in keywords)

def get_filename_from_url(url):
    name = os.path.basename(urlparse(url).path)
    return name if (name and '.' in name) else hashlib.md5(url.encode()).hexdigest()[:12] + ".pdf"

def safe_request(url, retries=3, delay=2.0):
    for i in range(retries):
        try:
            resp = SESSION.get(url, timeout=30)
            resp.raise_for_status()
            if resp.encoding and 'gb' in resp.encoding.lower():
                resp.encoding = 'gbk'
            elif not resp.encoding or resp.encoding == 'ISO-8859-1':
                cs = resp.content[:2048]
                if b'gb2312' in cs.lower() or b'gbk' in cs.lower(): resp.encoding = 'gbk'
                elif b'utf-8' in cs.lower(): resp.encoding = 'utf-8'
            return resp
        except requests.RequestException as e:
            logger.warning(f"请求失败({i+1}/{retries}): {url} - {e}")
            if i < retries - 1: time.sleep(delay * (i + 1))
    return None

def fetch_dynamic_page(url, timeout=20000):
    """Playwright渲染动态页面"""
    if not _PLAYWRIGHT:
        resp = safe_request(url)
        return resp.text if resp else ""
    try:
        # 修复 Node.js preload 模块问题
        import os as _os
        if 'NODE_OPTIONS' not in _os.environ:
            _os.environ['NODE_OPTIONS'] = ''
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=[
                '--no-sandbox','--disable-setuid-sandbox',
                '--disable-dev-shm-usage','--disable-gpu'
            ])
            page = browser.new_page()
            page.set_default_timeout(timeout)
            page.goto(url, wait_until='networkidle')
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        logger.warning(f"Playwright失败: {e}")
        resp = safe_request(url)
        return resp.text if resp else ""

def extract_wenhao(text):
    for pat in [
        r'(发改能源规?〔\d{4}〕\d+号)', r'(发改能源〔\d{4}〕\d+号)',
        r'(发改价格〔\d{4}〕\d+号)', r'(发改环资〔\d{4}〕\d+号)',
        r'(国能发\w+〔\d{4}〕\d+号)', r'(国办发〔\d{4}〕\d+号)',
        r'(国发〔\d{4}〕\d+号)', r'(闽政办〔\d{4}〕\d+号)',
        r'(闽发改\w*〔\d{4}〕\d+号)', r'([\u4e00-\u9fa5]+〔\d{4}〕\d+号)',
    ]:
        m = re.search(pat, text)
        if m: return m.group(1)
    return ""

def classify_policy(title, summary):
    text = (title + ' ' + summary).lower()
    level = "国家"
    if any(w in text for w in ['福建省','福建','闽']): level = "福建省级"
    if any(w in text for w in ['福州市','厦门市','泉州市','漳州市','龙岩市','三明市','莆田市','南平市','宁德市']): level = "地市级"
    type_map = {
        '新能源': ['新能源','光伏','风电','可再生能源','分布式'],
        '储能': ['储能','新型储能','抽水蓄能'],
        '电力政策': ['电改','电力体制','电力市场','售电','输配电价','电价','容量电价','上网电价'],
        '交易规则': ['交易','中长期','现货','辅助服务','绿电','绿证'],
        '园区低碳': ['零碳','低碳','园区','节能降碳','碳达峰','碳中和','节能改造'],
        '综合': ['综合能源','能源托管','电力运维','充电桩','充电站','微电网','虚拟电厂'],
        '监管': ['监管','督查','检查','考核'],
        '标准': ['标准','规范','指南','导则'],
    }
    types = [n for n, kws in type_map.items() if any(k.lower() in text for k in kws)]
    return level, '、'.join(types[:3]) if types else '综合'

def generate_policy_id(date_str, publisher, wenhao, title):
    """政策唯一ID = 发文编号；无发文编号则用日期+标题前20字"""
    if wenhao and len(wenhao) >= 6:
        return wenhao
    if date_str:
        return f"{date_str}_{title[:30]}"
    return title[:40]

# --- 爬虫核心 ---

class PolicyScraper:
    def __init__(self):
        self.config = load_config()
        self.keywords = self.config.get('keywords', [])
        self.visited = load_visited_urls()
        self.policy_index = load_policy_index()
        self.results = []
        self.collection_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
        self.year_start = 2025

    def scrape_all(self):
        logger.info("=" * 60)
        logger.info(f"政策采集开始 {datetime.now():%Y-%m-%d %H:%M:%S}")
        logger.info(f"关键词:{len(self.keywords)} | 年份:≥{self.year_start} | 已访问:{len(self.visited)}")
        sources = (
            self.config.get('national', []) +
            self.config.get('fujian_province', []) +
            self.config.get('fujian_cities', [])
        )
        logger.info(f"采集源:{len(sources)}个\n")
        for src in sources:
            self._scrape_source(src)
        self._save_results()
        self._save_policy_index()
        logger.info(f"\n✅ 完成: 新增{len(self.results)}条")

    def _get_page_html(self, url):
        """智能获取页面HTML：动态站点用Playwright，静态用requests"""
        domain = urlparse(url).netloc.lower()
        if any(d in domain for d in DYNAMIC_DOMAINS):
            logger.debug(f"  动态渲染: {url}")
            return fetch_dynamic_page(url)
        resp = safe_request(url)
        return resp.text if resp else ""

    def _scrape_source(self, source):
        name = source.get('name','?')
        url = source.get('url','')
        base_url = source.get('base_url', url)
        category = source.get('category','')

        logger.info(f"[{category}] {name}")
        html = self._get_page_html(url)
        if not html:
            logger.warning("  ⚠ 无法获取页面")
            return

        soup = BeautifulSoup(html, 'html.parser')
        items = self._find_items(soup, source)
        if not items:
            logger.info("  → 无列表项")
            return

        new = 0
        for item in items:
            try:
                link = self._extract(item, 'link', source)
                title = self._extract(item, 'title', source)
                date_str = self._extract(item, 'date', source)
                date = extract_date(date_str)

                if not link or not title: continue
                full_url = normalize_url(link, base_url)
                full_title = title.strip()
                title_hash = hashlib.md5(full_title.encode()).hexdigest()[:8]

                if full_url in self.visited: continue
                if date:
                    try:
                        if int(date[:4]) < self.year_start: continue
                    except: pass

                if not matches_keywords(full_title, self.keywords): continue

                detail = self._fetch_detail(full_url, full_title)
                pub = detail.get('department', '') or category
                wh = detail.get('wenhao', '')
                pid = generate_policy_id(date or 'unknown', pub, wh, full_title)
                if pid in self.policy_index: continue

                level, ctype = classify_policy(full_title, detail.get('summary',''))

                result = {
                    '政策唯一ID': pid,
                    '发布日期': date or '',
                    '发布单位': pub,
                    '文件标题': full_title,
                    '内容层级': level,
                    '内容类型': ctype,
                    '核心要点': detail.get('summary','')[:500],
                    '业务影响': '',
                    '生效日期': date or '',
                    '原文链接': full_url,
                    '文件位置': '',
                    '收集人': 'WorkBuddy自动采集',
                    '收集时间': self.collection_time,
                    '备注': '',
                    '发文编号': detail.get('wenhao',''),
                    '附件PDF': detail.get('pdf_urls',[]),
                }
                self.results.append(result)
                self.visited.add(full_url)
                new += 1
                logger.info(f"  ✓ [{date or '?'}] {full_title[:70]}...")
            except Exception as e:
                logger.debug(f"  × {e}")
                continue
        logger.info(f"  → +{new}条")

    def _find_items(self, soup, source):
        """多策略查找列表项，兼容各种政府网站结构"""
        # 策略1：使用配置的选择器
        sel = source.get('list_selector','')
        if sel:
            for s in sel.split(','):
                s = s.strip()
                if not s: continue
                items = soup.select(s)
                if items and len(items) >= 2:
                    return items

        # 策略2：常见政府网站列表模式
        common_selectors = [
            'ul.list li', 'ul.right_list li', 'ul.news_list li',
            'div.list li', 'div.list_content li', 'div.news_list li',
            'div.right_list li', 'table[class*="list"] tr', 'div.zwgk_list li',
            'div.xxgk_list li', 'div.content_list li', '.main-content li',
            'ul.policy_list li', 'div.article-list li', 'ul.info-list li',
        ]
        for s in common_selectors:
            items = soup.select(s)
            if items and len(items) >= 2:
                return items

        # 策略3：找包含链接最多的ul或div
        best_items = []
        for container in soup.find_all(['ul', 'div', 'table']):
            lis = container.find_all('li') or container.find_all('tr')
            linked = [x for x in lis if x.find('a', href=True)]
            if len(linked) > len(best_items):
                best_items = linked

        if len(best_items) >= 2:
            return best_items[:100]

        # 策略4：找所有带链接的li
        items = [li for li in soup.find_all('li') if li.find('a', href=True)]
        return items[:100] if items else []

    def _extract(self, element, field, source):
        """通用提取器"""
        if field == 'link':
            sel = source.get('link_selector','')
            if '::attr' in sel:
                tag = sel.split('::attr')[0] or 'a'
                attr = sel.split('::attr(')[1].rstrip(')')
                child = element.select_one(tag) if tag != '*' else element
                if child: return child.get(attr,'')
            a = element.find('a') if element.name != 'a' else element
            return a.get('href','') if a else ''
        elif field == 'title':
            sel = source.get('title_selector','')
            if '::text' in sel:
                tag = sel.split('::text')[0] or 'a'
                child = element.select_one(tag) if tag != '*' else element
                if child: return child.get_text(strip=True)
            a = element.find('a') if element.name != 'a' else element
            return a.get_text(strip=True) if a else ''
        elif field == 'date':
            # 优先找 class 含 date/time/sj 的 span
            for cls_name in ['sj', 'date', 'time']:
                span = element.find('span', class_=re.compile(cls_name, re.I))
                if span:
                    txt = span.get_text(strip=True)
                    if txt: return txt
            # 找任何span
            span = element.find('span')
            if span:
                txt = span.get_text(strip=True)
                if txt and re.search(r'\d{4}', txt): return txt
        return ''

    def _fetch_detail(self, url, title):
        result = {'department':'','summary':'','pdf_urls':[],'wenhao':''}
        resp = safe_request(url)
        if not resp: return result
        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text()

        # 发文编号
        result['wenhao'] = extract_wenhao(text) or extract_wenhao(title)

        # 发布部门 - 多种策略
        dept = ''
        # 策略1：元数据标签
        for meta_name in ['source', 'author', 'ContentSource', 'article_author', 'dc:creator']:
            meta = soup.find('meta', attrs={'name': meta_name})
            if meta and meta.get('content'):
                dept = meta['content'].strip()
                if len(dept) >= 4: break
        # 策略2：页面文本中匹配
        if not dept or len(dept) < 4:
            for pat in [
                r'(?:发布单位|发文机关|发布机构|来源|成文单位|制发单位)[：:]\s*([^\s<，,]+)',
                r'([\u4e00-\u9fa5]{2,10}(?:部|委|局|厅|办|处|中心))',
            ]:
                m = re.search(pat, text[:800])
                if m:
                    dept = m.group(1).strip()
                    if 3 <= len(dept) <= 30: break
        # 策略3：从标题推断（如 "国家能源局关于...的通知"）
        if not dept or len(dept) < 3:
            m = re.match(r'([\u4e00-\u9fa5]{2,20}(?:部|委|局|厅|办|中心|委员会))', title)
            if m: dept = m.group(1)
        result['department'] = dept if (dept and len(dept) >= 3) else ''

        # 摘要
        for sel in ['div.article-content','div.content','div.TRS_Editor',
                     'div#content','article','div.zw','div.detail-content','div.news-content']:
            div = soup.select_one(sel)
            if div:
                result['summary'] = div.get_text(strip=True)[:500]
                break
        if not result['summary']: result['summary'] = text[:500]

        # PDF附件
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '.pdf' in href.lower():
                pdf_url = normalize_url(href, url)
                result['pdf_urls'].append({
                    'url': pdf_url,
                    'filename': get_filename_from_url(pdf_url),
                    'title': a.get_text(strip=True) or get_filename_from_url(pdf_url),
                })
        return result

    def _save_results(self):
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        jp = DATA_DIR / f"policies_{ts}.json"
        with open(jp, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        with open(DATA_DIR / "policies_latest.json", 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        save_visited_urls(self.visited)

    def _save_policy_index(self):
        for r in self.results:
            pid = r['政策唯一ID']
            if pid not in self.policy_index:
                self.policy_index[pid] = {
                    'title': r['文件标题'], 'date': r['发布日期'],
                    'url': r['原文链接'], 'collected_at': self.collection_time,
                }
        save_policy_index(self.policy_index)

    def download_pdfs(self, max_per=5):
        logger.info("\n--- 下载PDF ---")
        dl = 0
        for r in self.results:
            pdfs = r.get('附件PDF',[])
            if not pdfs: continue
            pd = PDF_DIR / r['政策唯一ID'][:50].replace('/','_')
            pd.mkdir(exist_ok=True)
            for i, pi in enumerate(pdfs[:max_per]):
                pu = pi['url']
                fn = pi.get('filename', f'doc_{i}.pdf')
                fp = pd / fn
                if fp.exists():
                    pi['local_path'] = str(fp)
                    continue
                try:
                    logger.info(f"  下载:{fn}...")
                    pr = safe_request(pu)
                    if pr and len(pr.content) > 1000:
                        with open(fp, 'wb') as f: f.write(pr.content)
                        pi['local_path'] = str(fp)
                        dl += 1
                except Exception as e:
                    logger.error(f"  ✗ {e}")
                time.sleep(0.5)
        with open(DATA_DIR / "policies_latest.json", 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        logger.info(f"下载PDF:{dl}个")

def main():
    s = PolicyScraper()
    s.scrape_all()
    s.download_pdfs()
    return s.results

if __name__ == '__main__':
    r = main()
    print(f"\n总计:{len(r)}条")
