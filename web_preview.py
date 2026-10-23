"""Render local HTML/CSS as a static, network-free preview; never execute JS."""
from html import escape
from html.parser import HTMLParser
import posixpath
import re

CSP="default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src 'none'; form-action 'none'; base-uri 'none'"
TAGS=set('div span p h1 h2 h3 h4 h5 h6 header footer main nav section article aside ul ol li dl dt dd strong em b i u s small code pre blockquote br hr table thead tbody tfoot tr th td caption button input label textarea select option details summary figure figcaption img a style'.split())
VOID={'br','hr','input','img'}
SKIP={'script','iframe','object','template','svg','math','noscript','title'}


def css_text(value):
    return value.replace('<','\\3c ')


class StaticHTML(HTMLParser):
    def __init__(self, files, entry):
        super().__init__(convert_charrefs=True)
        self.files=files;self.entry=entry;self.parts=[];self.skipped=[];self.in_style=False

    def handle_starttag(self, tag, attrs):
        if self.skipped:
            if tag in SKIP:self.skipped.append(tag)
            return
        if tag in SKIP:
            self.skipped.append(tag);return
        values=dict(attrs)
        if tag=='link' and values.get('rel','').lower()=='stylesheet':
            href=values.get('href','')
            path=posixpath.normpath(posixpath.join(posixpath.dirname(self.entry),href.split('?')[0].split('#')[0]))
            if href and not href.startswith(('/','\\')) and ':' not in href and path in self.files:
                self.parts.append('<style>'+css_text(self.files[path])+'</style>')
            return
        if tag not in TAGS:return
        safe=[]
        for name,value in attrs:
            if value is None:value=''
            if name.startswith('on') or name in ('srcset','srcdoc','formaction','action','form','target','is','autofocus'):
                continue
            if name in ('href','src','poster','background'):
                if tag=='a' and name=='href' and value.startswith('#'):pass
                elif tag=='img' and name=='src' and re.fullmatch(r'data:image/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=\s]+',value):pass
                else:continue
            if name=='style':value=css_text(value)
            safe.append(' '+name+'="'+escape(value,quote=True)+'"')
        self.parts.append('<'+tag+''.join(safe)+'>')
        if tag=='style':self.in_style=True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.skipped:
            if tag==self.skipped[-1]:self.skipped.pop()
            return
        if tag in TAGS and tag not in VOID:self.parts.append('</'+tag+'>')
        if tag=='style':self.in_style=False

    def handle_data(self, data):
        if not self.skipped:self.parts.append(css_text(data) if self.in_style else escape(data))


def preview_html(files, entry):
    content={item['path']:item['content'] for item in files}
    if not isinstance(entry,str) or entry not in content or not entry.lower().endswith(('.html','.htm')):
        raise ValueError('Chọn tệp HTML có trong bộ sản phẩm')
    parser=StaticHTML(content,entry);parser.feed(content[entry]);parser.close()
    return '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="'+escape(CSP,quote=True)+'"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>'+''.join(parser.parts)+'</body></html>'
