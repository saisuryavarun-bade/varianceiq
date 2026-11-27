"""Real headless Edge UI checks against an isolated localhost server.

Uses only synthetic inputs. AI HTTP responses are explicitly mocked, never live.
Run after installing requirements-dev.txt; requires Microsoft Edge.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'data/browser-test-results'


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env=dict(os.environ,OPENAI_API_KEY='',ENABLE_LEGACY_AGENT='false')
    server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],
                            cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    url=f'http://127.0.0.1:{port}'
    checks=[]; errors=[]; success=False
    def passed(name):
        checks.append(name);print('PASS:',name,flush=True)
    try:
        for _ in range(100):
            try:
                with urlopen(url+'/api/health',timeout=1) as response:
                    if response.status==200:break
            except Exception:time.sleep(.1)
        else:raise RuntimeError('Local test server did not start')
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1100},accept_downloads=True)
            page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(url)
            expect(page.locator('#notice')).to_have_text('Review ready. No AI was used.')
            expect(page.locator('#findings tr')).to_have_count(75)
            expect(page.locator('#investigate')).to_be_disabled()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(OUTPUT/'desktop.png'),full_page=True)
            passed('Desktop review loads without a model key; 75 findings; no page overflow')
            page.locator('#search').fill('no-such-account')
            expect(page.locator('#empty')).to_be_visible()
            page.locator('#search').fill('')
            page.locator('#material-only').check()
            expect(page.locator('#findings tr')).to_have_count(49)
            page.locator('#material-only').uncheck()
            page.locator('#period').select_option('2025-09')
            page.locator('#refresh').click()
            expect(page.locator('#findings tr')).to_have_count(25)
            page.locator('#findings button').nth(1).click()
            passed('Search, materiality filter, period selection, and finding selection')
            page.locator('#note').fill('Synthetic reviewer note')
            page.locator('#reviewed').check()
            with page.expect_download() as download:
                page.locator('#export').click()
            packet=json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
            assert any(n.get('text')=='Synthetic reviewer note' and n.get('reviewed') for n in packet['analyst_annotations'])
            assert len(packet['source_data']['budget_actuals'])==75
            with page.expect_download() as download:
                page.locator('#csv').click()
            assert len(Path(download.value.path()).read_text(encoding='utf-8').splitlines())==26
            passed('JSON exports retain source inputs and notes; CSV exports selected-period findings')
            page.locator('.upload summary').click()
            fixture=ROOT/'tests/fixtures/synthetic_product/reconciled_40_transactions'
            page.locator('#budget-file').set_input_files(str(fixture/'budget.csv'))
            page.locator('#transactions-file').set_input_files(str(fixture/'transactions.csv'))
            page.locator('#upload-form button').click()
            expect(page.locator('#findings tr')).to_have_count(1)
            expect(page.locator('#detail .pill').first).to_have_text('Reconciled')
            expect(page.locator('.evidence-summary')).to_contain_text('Showing 25 of 40')
            expect(page.locator('.evidence-summary')).to_contain_text('40,780.00')
            page.locator('#detail summary').first.click()
            expect(page.locator('#detail tbody tr')).to_have_count(25)
            passed('Real CSV upload reconciles 40 rows and displays the 25-row evidence limit accurately')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile page overflows'
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(OUTPUT/'mobile-top.png'))
            page.screenshot(path=str(OUTPUT/'mobile.png'),full_page=True)
            page.locator('#investigate').scroll_into_view_if_needed()
            page.screenshot(path=str(OUTPUT/'mobile-detail.png'))
            passed('390px mobile layout has no page overflow and evidence remains accessible')
            # Simulated key availability and drafts exercise rendering only. No API call leaves localhost.
            page.route('**/api/health',lambda route:route.fulfill(json={'key_configured':True,'model':'mock-only'}))
            page.set_viewport_size({'width':1440,'height':1100});page.reload()
            expect(page.locator('#investigate')).to_be_enabled()
            page.route('**/api/review/investigate',lambda route:route.fulfill(status=502,json={'detail':'Simulated provider failure'}))
            page.locator('#investigate').click()
            expect(page.locator('#notice')).to_have_text('Simulated provider failure')
            expect(page.locator('#detail .pill').first).to_have_text('Reconciled')
            expect(page.locator('#investigate')).to_be_enabled()
            passed('AI failure is visible and leaves the deterministic review intact')
            page.unroute('**/api/review/investigate')
            draft={'observations':[{'claim':'<img src=x onerror=alert(1)>','source_ids':['synthetic-reference']}],
                   'hypotheses':['Unconfirmed explanation'],'questions':['Request business context'],
                   'limitation':'Mock output for UI safety testing only.'}
            page.route('**/api/review/investigate',lambda route:route.fulfill(json={'draft':draft}))
            page.locator('#investigate').click()
            expect(page.locator('#draft')).to_contain_text('AI draft')
            expect(page.locator('#draft img')).to_have_count(0)
            expect(page.locator('#draft')).to_contain_text('<img src=x onerror=alert(1)>')
            passed('AI draft is marked unverified and HTML is displayed as inert text')
            assert not errors, errors
            body=page.locator('body').inner_text()
            assert '\u00c2\u00b7' not in body and '\u00e2\u20ac' not in body, 'Corrupted UTF-8 text in UI'
            passed('No JavaScript exceptions or mojibake in rendered text')
            success=True
            browser.close()
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait()
        (OUTPUT/'results.json').write_text(json.dumps({'success':success,'checks_passed':checks,'javascript_errors':errors,
             'live_ai_tested':False,'browser':'Microsoft Edge headless'},indent=2)+'\n',encoding='utf-8')
    print(f'{len(checks)} browser checks passed; screenshots in {OUTPUT}.')


if __name__=='__main__':main()
