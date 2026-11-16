#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Render the screenshot manual. Requires playwright, markdown-it-py and a CJK font."""
import asyncio, os, sys, re
from urllib.parse import quote
from pathlib import Path
from markdown_it import MarkdownIt
from playwright.async_api import async_playwright

md = Path(sys.argv[1]).resolve()
pdf = Path(sys.argv[2]).resolve()
pdf.parent.mkdir(parents=True, exist_ok=True)
html = pdf.with_suffix('.print.html')
body = MarkdownIt('commonmark').enable('table').render(md.read_text())
def remote_link(match):
    link=match.group(1)
    if link.startswith(('https://','http://','#','mailto:')):
        return match.group(0)
    relative=(md.parent/link).resolve().relative_to(md.parents[2])
    return '<a href="https://gitee.com/xwy6848/core/blob/master/' + quote(relative.as_posix()) + '"'
body=re.sub(r'<a href="([^"]+)"',remote_link,body)

html.write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>工业可信防火墙 · 安装与使用说明</title>
<base href="''' + md.parent.as_uri() + '''/"><style>
body { font: 10.5pt/1.65 "Source Han Sans SC", sans-serif; color:#1d2830; }
h1,h2,h3 {font-weight:700;line-height:1.35;break-after:avoid}
h1{font-size:22pt;border-bottom:3px solid #bc4618;padding:0 0 12pt;color:#24272a}
h2{font-size:15.5pt;border-left:3px solid #bc4618;padding-left:7pt;margin:18pt 0 8pt}
h3{font-size:12pt;color:#9d3613}
p,ul,ol{margin:7pt 0}
li{margin:2pt 0}
table{width:100%;border-collapse:collapse;font-size:9.5pt}
tr{break-inside:avoid}
th,td{border:1px solid #d8dadb;text-align:left;padding:4pt 6pt;vertical-align:top;}
th{background:#f4ede7}
pre{white-space:pre-wrap;overflow-wrap:anywhere;break-inside:avoid;background:#f1f3f5;padding:8pt;font-size:8.5pt;border:1px solid #d8dadb;}
code{overflow-wrap:anywhere;font-family:"DejaVu Sans Mono","Source Han Sans SC",monospace;}
figure{margin:8pt 0 12pt;break-inside:avoid}
figure img{display:block;max-width:100%;max-height:142mm;height:auto;object-fit:contain;border:1px solid #d8dadb;}
figcaption{padding-top:4pt;color:#4b5760;font-size:9pt;}
a{color:#9d3613;}
</style><body>''' + body + '</body></html>', encoding='utf-8')

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH'), args=['--no-sandbox','--allow-file-access-from-files'])
        page = await browser.new_page()
        await page.goto(html.as_uri(),wait_until='load')
        await page.evaluate('''() => {
            document.querySelectorAll('p > img').forEach((img) => {
                const p = img.parentElement;
                const next = p.nextElementSibling;
                const fig = document.createElement('figure');
                fig.append(img);
                if (next && next.tagName === 'P' && next.textContent.startsWith('图 ')) {
                    const cap = document.createElement('figcaption');
                    cap.textContent = next.textContent;
                    next.remove(); fig.append(cap);
                }
                p.replaceWith(fig);
            });
            return document.fonts.ready;
        }''')
        images = await page.locator('img').evaluate_all('(imgs) => imgs.map(i => [i.src, i.naturalWidth, i.naturalHeight])')
        assert images and all(w and h for _,w,h in images),images
        font = await page.evaluate("document.fonts.check('12px Source Han Sans SC')")
        assert font
        await page.pdf(path=str(pdf),format='A4',print_background=True,display_header_footer=True,
                       outline=True,tagged=True,
                       margin={'top':'16mm','left':'14mm','right':'14mm','bottom':'17mm'},
                       header_template='<span></span>',
                       footer_template='<div style="width:100%;font:8px sans-serif;color:#555;text-align:center">Industrial Firewall 2026.11.16 &nbsp; · &nbsp; <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        await browser.close()
        print(f'PDF: {pdf.name} with {len(images)} verified screenshot images')
try:
    asyncio.run(run())
finally:
    html.unlink(missing_ok=True)
