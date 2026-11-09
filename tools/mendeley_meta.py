# -*- coding: utf-8 -*-
"""Mendeley 数据集元数据提取（T5：DOI + 许可 + 引用信息）。"""
import urllib.request
import re

req = urllib.request.Request('https://data.mendeley.com/v1/datasets/pdnjz7zz5x/1',
                             headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req, timeout=60).read().decode('utf-8')

keys = ('citation_', 'citation', 'description', 'license', 'doi', 'creator',
        'publication_date', 'DC.', 'twitter:', 'og:')
out = []
for m in re.finditer(r'<meta[^>]*>', html):
    tag = m.group(0)
    low = tag.lower()
    if any(k.lower() in low for k in keys):
        out.append(tag)

for t in sorted(set(out)):
    print(t[:240])
