import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { site, categories, docs, icon, docOrder } from './site-data.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const contentDir = path.join(root, 'content', 'docs');
const outDir = path.join(root, 'docs');
const meta = JSON.parse(fs.readFileSync(path.join(contentDir, 'meta.json'), 'utf8'));
const today = new Date().toISOString().slice(0, 10);
const contentDate =
  Object.values(meta)
    .map((item) => item.updated)
    .filter(Boolean)
    .sort()
    .pop() || today;

const escapeHtml = (value) =>
  String(value).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

const decodeEntities = (value) =>
  String(value)
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)));

const stripTags = (value) =>
  decodeEntities(String(value).replace(/<[^>]*>/g, ' ')).replace(/\s+/g, ' ').trim();

const readingTime = (body) => {
  const chars = stripTags(body).replace(/\s/g, '').length;
  return Math.max(3, Math.ceil(chars / 500));
};

/* ---------------------------------------------------------- body processing */

function addHeadingIds(body) {
  const toc = [];
  let counter = 0;

  const processChunk = (chunk) =>
    chunk.replace(/<h([234])([^>]*)>([\s\S]*?)<\/h\1>/g, (match, level, attrs, inner) => {
      const text = stripTags(inner);
      if (!text) return match;
      let id = '';
      const existing = attrs.match(/\bid="([^"]+)"/);
      if (existing) {
        id = existing[1];
      } else {
        counter += 1;
        id = `sec-${counter}`;
        attrs += ` id="${id}"`;
      }
      if (level === '2' || level === '3') {
        toc.push({ level: Number(level), text, id });
      }
      return `<h${level}${attrs}>${inner}</h${level}>`;
    });

  // never touch markup inside code blocks
  const parts = body.split(/(<pre[\s\S]*?<\/pre>)/i);
  const processed = parts
    .map((part) => (part.startsWith('<pre') ? part : processChunk(part)))
    .join('');

  return { body: processed, toc };
}

function buildExcerptMap(body, toc) {
  const map = new Map();
  toc.forEach((heading, index) => {
    const needle = `id="${heading.id}"`;
    const at = body.indexOf(needle);
    if (at === -1) return;
    const close = body.indexOf(`</h${heading.level}>`, at);
    if (close === -1) return;
    const next = toc[index + 1];
    const nextAt = next ? body.indexOf(`id="${next.id}"`) : -1;
    const end = nextAt === -1 ? body.length : nextAt;
    const text = stripTags(body.slice(close + 5, end)).slice(0, 220);
    map.set(heading.id, text);
  });
  return map;
}

/* --------------------------------------------------------------- templates */

const head = ({
  title,
  description,
  keywords = [],
  canonical,
  prefix,
  type = 'website',
  withKatex = false,
  updated = '',
  section = '',
  jsonLd = null,
}) => `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(title)}</title>
  <meta name="description" content="${escapeHtml(description)}">
  <meta name="keywords" content="${escapeHtml(keywords.join(','))}">
  <meta name="author" content="PenShot Team">
  <meta name="application-name" content="PenShot">
  <meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
  <meta name="theme-color" content="#0b0d12">
  <link rel="canonical" href="${canonical}">
  <meta property="og:site_name" content="PenShot">
  <meta property="og:locale" content="zh_CN">
  <meta property="og:type" content="${type}">
  <meta property="og:title" content="${escapeHtml(title)}">
  <meta property="og:description" content="${escapeHtml(description)}">
  <meta property="og:url" content="${canonical}">
  <meta property="og:image" content="${site.url}/assets/img/og-cover.png">
  <meta property="og:image:type" content="image/png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="PenShot：把剧本拆成连贯的 AI 视频片段">
  ${updated ? `<meta property="article:published_time" content="${updated}T00:00:00+08:00">` : ''}
  ${updated ? `<meta property="article:modified_time" content="${updated}T00:00:00+08:00">` : ''}
  ${section ? `<meta property="article:section" content="${escapeHtml(section)}">` : ''}
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${escapeHtml(title)}">
  <meta name="twitter:description" content="${escapeHtml(description)}">
  <meta name="twitter:image" content="${site.url}/assets/img/og-cover.png">
  <link rel="icon" type="image/svg+xml" href="${prefix}assets/img/favicon.svg">
  <link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
  <link rel="stylesheet" href="${prefix}assets/css/site.css">
  <link rel="stylesheet" href="${prefix}assets/css/docs.css">
  ${withKatex ? '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">' : ''}
  <script>document.documentElement.classList.add('js');</script>
  ${jsonLd ? `<script type="application/ld+json">${JSON.stringify(jsonLd).replace(/</g, '\\u003c')}</script>` : ''}
</head>`;

const header = ({ prefix = '', active = '', searchIndex }) => {
  const docsHome = prefix ? 'index.html' : 'docs/';
  const quickStartHref = prefix ? 'quick-start.html' : 'docs/quick-start.html';
  return `<body class="docs-page" data-search-index="${searchIndex}">
<a class="skip-link" href="#main">跳到正文</a>

<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="${prefix}index.html" aria-label="PenShot 首页">
      <img src="${prefix}assets/img/logo-mark.svg" alt="" width="30" height="30">
      <span>PenShot<small>Storyboard Agent</small></span>
    </a>
    <nav class="site-nav" aria-label="主导航">
      <a href="${prefix}index.html"${active === 'home' ? ' class="is-active"' : ''}>首页</a>
      <a href="${prefix}index.html#features">功能</a>
      <a href="${prefix}index.html#workflow">工作流程</a>
      <a href="${prefix}index.html#integrations">集成</a>
      <a href="${docsHome}"${active === 'docs' ? ' class="is-active"' : ''}>文档</a>
      <a href="${site.blog}" target="_blank" rel="noopener">博客</a>
    </nav>
    <div class="header-actions">
      <button class="icon-btn search-trigger" type="button" data-search-open aria-label="搜索文档">
        ${icon('search', 15)}<span>搜索</span><kbd>Ctrl K</kbd>
      </button>
      <a class="header-github" href="${site.repo}" target="_blank" rel="noopener">
        ${icon('github', 16)}<span>GitHub</span>
      </a>
      <button class="menu-toggle" type="button" data-menu-toggle aria-expanded="false" aria-label="打开导航">
        ${icon('menu', 19)}
      </button>
    </div>
  </div>
</header>
<div class="mobile-nav" data-mobile-nav>
  <a href="${prefix}index.html">首页</a>
  <a href="${prefix}index.html#features">功能</a>
  <a href="${prefix}index.html#workflow">工作流程</a>
  <a href="${prefix}index.html#integrations">集成方式</a>
  <a href="${docsHome}">文档</a>
  <a href="${site.blog}" target="_blank" rel="noopener">技术博客</a>
  <div class="mobile-nav__cta">
    <a class="btn btn--primary" href="${quickStartHref}">快速开始</a>
    <a class="btn btn--ghost" href="${site.repo}" target="_blank" rel="noopener">GitHub</a>
  </div>
</div>

<main id="main">`;
};

const sidebar = (slug) => {
  const groups = categories
    .map((category) => {
      const links = category.docs
        .map((item) => {
          const doc = docs[item];
          return `<li><a href="${item}.html"${item === slug ? ' class="is-active" aria-current="page"' : ''}>${escapeHtml(doc.title)}</a></li>`;
        })
        .join('');
      return `<div class="sidebar-group">
        <div class="sidebar-group__title">${icon(category.icon, 12)}${escapeHtml(category.name)}</div>
        <ul class="sidebar-links">${links}</ul>
      </div>`;
    })
    .join('\n');

  return `<div class="docs-shell">
  <aside class="docs-sidebar" data-docs-sidebar aria-label="文档导航">
    <button class="sidebar-close" type="button" data-sidebar-close aria-label="关闭目录">${icon('x', 16)}</button>
    <div class="sidebar-search">
      <button type="button" data-search-open>${icon('search', 14)}<span>搜索文档</span><kbd>Ctrl K</kbd></button>
    </div>
    <a class="sidebar-home" href="index.html">${icon('home', 15)}文档中心</a>
    ${groups}
    <div class="sidebar-divider"></div>
    <div class="sidebar-extra">
      <a href="${site.repo}" target="_blank" rel="noopener">${icon('github', 13)}GitHub 源码</a>
      <a href="${site.pypi}" target="_blank" rel="noopener">${icon('package', 13)}PyPI 安装包</a>
      <a href="${site.url}" target="_blank" rel="noopener">${icon('globe', 13)}产品官网</a>
      <a href="${site.issues}" target="_blank" rel="noopener">${icon('prompt', 13)}问题反馈</a>
    </div>
    <div class="sidebar-foot">PenShot ${site.version}<br>MIT License · ${contentDate}</div>
  </aside>
  <div class="sidebar-overlay" data-sidebar-overlay></div>`;
};

const tocList = (toc) =>
  toc
    .map(
      (heading) =>
        `<li class="toc-depth-${heading.level}"><a href="#${heading.id}">${escapeHtml(heading.text)}</a></li>`
    )
    .join('');

const pager = (slug) => {
  const index = docOrder.findIndex((entry) => entry.slug === slug);
  const prev = index > 0 ? docOrder[index - 1] : null;
  const next = index > -1 && index < docOrder.length - 1 ? docOrder[index + 1] : null;
  const render = (entry, direction) => {
    if (!entry) return '<span class="pager-spacer"></span>';
    const doc = docs[entry.slug];
    return `<a class="pager-link${direction === 'next' ? ' pager-link--next' : ''}" href="${entry.slug}.html">
      <span class="pager-link__label">${direction === 'prev' ? '← 上一篇' : '下一篇 →'} · ${escapeHtml(entry.category.name)}</span>
      <strong>${escapeHtml(doc.title)}</strong>
      <small>${escapeHtml(doc.deck)}</small>
    </a>`;
  };
  return `<nav class="doc-pager" aria-label="文档翻页">
    ${render(prev, 'prev')}
    ${render(next, 'next')}
  </nav>`;
};

const docsFooter = () => `<footer class="docs-footer">
  <div class="docs-footer__inner">
    <span>© <span data-year>${today.slice(0, 4)}</span> PenShot · 文档基线 ${site.version} · MIT License</span>
    <div class="docs-footer__links">
      <a href="${site.url}">官网</a>
      <a href="${site.repo}" target="_blank" rel="noopener">GitHub</a>
      <a href="${site.pypi}" target="_blank" rel="noopener">PyPI</a>
      <a href="${site.issues}" target="_blank" rel="noopener">问题反馈</a>
      <a href="${site.blog}" target="_blank" rel="noopener">技术博客</a>
    </div>
  </div>
</footer>

<script src="../assets/js/site.js" defer></script>
<script src="../assets/js/docs.js" defer></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
<script defer src="../assets/js/katex-init.js"></script>
</body>
</html>`;

/* --------------------------------------------------------------- doc pages */

function renderDoc(slug) {
  const doc = docs[slug];
  const metaInfo = meta[slug];
  if (!doc || !metaInfo) throw new Error(`missing metadata for ${slug}`);

  const rawBody = fs.readFileSync(path.join(contentDir, `${slug}.html`), 'utf8');
  const { body, toc } = addHeadingIds(rawBody);
  const excerptMap = buildExcerptMap(body, toc);
  const category = categories.find((c) => c.docs.includes(slug));
  const updated = metaInfo.updated || today;
  const minutes = readingTime(body);
  const canonical = `${site.url}/docs/${slug}.html`;
  const title = `${doc.title} · PenShot 文档`;
  const description = metaInfo.description || doc.deck;
  const keywords = metaInfo.keywords || [];
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'TechArticle',
    headline: doc.title,
    name: doc.title,
    description,
    url: canonical,
    mainEntityOfPage: { '@type': 'WebPage', '@id': canonical },
    datePublished: updated,
    dateModified: updated,
    inLanguage: 'zh-CN',
    articleSection: category.name,
    keywords: keywords.join(', '),
    image: `${site.url}/assets/img/og-cover.png`,
    author: { '@type': 'Organization', name: 'PenShot Team', url: site.url },
    publisher: {
      '@type': 'Organization',
      name: 'PenShot',
      url: site.url,
      logo: { '@type': 'ImageObject', url: `${site.url}/assets/img/logo-512.png` },
      sameAs: [site.repo, site.pypi],
    },
    isPartOf: { '@type': 'WebSite', name: 'PenShot', url: site.url },
  };

  const tocHtml = toc.length
    ? `<div class="toc-title">${icon('list', 12)}本页目录</div>
      <ul class="toc-nav">${tocList(toc)}</ul>`
    : `<div class="toc-title">${icon('list', 12)}本页目录</div><p class="doc-deck" style="font-size:12px">本页暂无分节。</p>`;

  const page = `${head({
    title,
    description,
    keywords,
    canonical,
    prefix: '../',
    type: 'article',
    withKatex: true,
    updated,
    section: category.name,
    jsonLd,
  })}
${header({ prefix: '../', active: 'docs', searchIndex: 'search-index.json' })}
  ${sidebar(slug)}
  <div class="docs-main">
    <nav class="breadcrumbs" aria-label="面包屑">
      <a href="../index.html">首页</a>${icon('chevronRight', 11)}
      <a href="index.html">文档</a>${icon('chevronRight', 11)}
      <a href="index.html#${category.id}">${escapeHtml(category.name)}</a>${icon('chevronRight', 11)}
      <span>${escapeHtml(doc.title)}</span>
    </nav>
    <div class="docs-mobile-bar">
      <button type="button" data-sidebar-open>${icon('list', 14)}文档目录</button>
      <button type="button" data-search-open>${icon('search', 14)}搜索</button>
    </div>
    <details class="toc-mobile">
      <summary>${icon('list', 14)}本页目录 · ${toc.length} 节</summary>
      <ul class="toc-nav">${tocList(toc)}</ul>
    </details>
    <div class="docs-layout">
      <article class="doc-body">
        <header class="doc-header">
          <span class="doc-header__cat">${escapeHtml(category.name)}</span>
          <h1>${escapeHtml(doc.title)}</h1>
          <p class="doc-deck">${escapeHtml(doc.deck)}</p>
          <div class="doc-meta-row">
            <span>${icon('calendar', 12)}更新 ${updated}</span>
            <span>${icon('clock', 12)}约 ${minutes} 分钟阅读</span>
            <a href="${site.repoEdit}${slug}.html" target="_blank" rel="noopener">${icon('edit', 12)}在 GitHub 编辑</a>
          </div>
        </header>
        ${body}
        ${pager(slug)}
      </article>
      <aside class="doc-toc" aria-label="本页目录">
        <div class="toc-inner">
          ${tocHtml}
          <a class="toc-back" href="#main">${icon('arrowUp', 11)}回到顶部</a>
          <a class="toc-edit" href="${site.repoEdit}${slug}.html" target="_blank" rel="noopener">在 GitHub 编辑此页 →</a>
        </div>
      </aside>
    </div>
  </div>
</div>
</main>
${docsFooter()}`;

  fs.writeFileSync(path.join(outDir, `${slug}.html`), page, 'utf8');
  return { slug, title: doc.title, description, updated, minutes, toc, body, excerptMap, category };
}

/* ----------------------------------------------------------------- docs hub */

function renderHub() {
  const featured = ['quick-start', 'architecture', 'mcp'];
  const startCards = featured
    .map((slug, i) => {
      const doc = docs[slug];
      return `<a class="start-card" href="${slug}.html">
        <span class="start-card__num">0${i + 1} · ${escapeHtml(categories.find((c) => c.docs.includes(slug)).name)}</span>
        <h2>${escapeHtml(doc.title)}</h2>
        <p>${escapeHtml(doc.deck)}</p>
        <span class="start-card__arrow">开始阅读 ${icon('arrowRight', 14)}</span>
      </a>`;
    })
    .join('');

  const sections = categories
    .map(
      (category) => `<section class="hub-section" id="${category.id}">
        <div class="hub-section__head">
          <h2>${icon(category.icon, 18)}${escapeHtml(category.name)}</h2>
          <p>${escapeHtml(category.desc)} · ${category.docs.length} 篇</p>
        </div>
        <div class="hub-list">
          ${category.docs
            .map((slug) => {
              const doc = docs[slug];
              return `<a class="hub-item" href="${slug}.html">
                <strong>${escapeHtml(doc.title)}</strong>
                <span>${escapeHtml(doc.deck)}</span>
                <em>阅读 →</em>
              </a>`;
            })
            .join('')}
        </div>
      </section>`
    )
    .join('\n');

  const canonical = `${site.url}/docs/`;
  const title = 'PenShot 文档 · 剧本分镜智能体';
  const description =
    'PenShot 官方文档：快速开始、技术架构、工作流节点、一致性策略、资产计划与模型路由、MCP / REST / SDK 集成，以及记忆与检索实现。';
  const keywords = [
    'PenShot 文档',
    '剧本分镜',
    '快速开始',
    '技术架构',
    '资产计划',
    '模型路由',
    'MCP',
    'REST API',
    'Python SDK',
    'Docker 部署',
    '记忆系统',
    'RAG',
  ];
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name: title,
    description,
    url: canonical,
    inLanguage: 'zh-CN',
    isPartOf: { '@type': 'WebSite', name: 'PenShot', url: site.url },
    publisher: {
      '@type': 'Organization',
      name: 'PenShot',
      url: site.url,
      logo: { '@type': 'ImageObject', url: `${site.url}/assets/img/logo-512.png` },
    },
    mainEntity: {
      '@type': 'ItemList',
      numberOfItems: docOrder.length,
      itemListElement: docOrder.map(({ slug }, index) => ({
        '@type': 'ListItem',
        position: index + 1,
        name: docs[slug].title,
        url: `${site.url}/docs/${slug}.html`,
      })),
    },
  };

  const page = `${head({
    title,
    description,
    keywords,
    canonical,
    prefix: '../',
    type: 'website',
    jsonLd,
  })}
${header({ prefix: '../', active: 'docs', searchIndex: 'search-index.json' })}
  <main id="main">
    <section class="docs-hero">
      <div class="container">
        <div class="docs-hero__inner">
          <div>
            <span class="eyebrow">Documentation</span>
            <h1>PenShot 文档</h1>
            <p>从第一条剧本到可投喂给视频模型的分镜提示词包。这里记录 PenShot 的工作流、接入方式、记忆与检索实现。</p>
            <button class="docs-search" type="button" data-search-open>
              ${icon('search', 16)}<span>搜索文档、节点、API 或关键词</span><kbd>Ctrl K</kbd>
            </button>
            <div class="docs-hero__meta">
              <span class="meta-chip"><b>${Object.keys(docs).length}</b> 篇文档</span>
              <span class="meta-chip"><b>8</b> 个业务节点</span>
              <span class="meta-chip"><b>3</b> 种接入方式</span>
              <span class="meta-chip"><b>MIT</b> 开源协议</span>
            </div>
          </div>
          <span class="docs-hero__badge">${site.version} · 基于源码</span>
        </div>
      </div>
    </section>

    <div class="docs-hub">
      <div class="container">
        <div class="hub-start">${startCards}</div>
        ${sections}
        <section class="hub-section">
          <div class="hub-section__head">
            <h2>${icon('link', 18)}资源与社区</h2>
            <p>源码、安装包、镜像与问题反馈</p>
          </div>
          <div class="hub-resources">
            <a class="hub-resource" href="${site.repo}" target="_blank" rel="noopener">${icon('github', 16)}GitHub 源码</a>
            <a class="hub-resource" href="${site.pypi}" target="_blank" rel="noopener">${icon('package', 16)}PyPI 安装包</a>
            <a class="hub-resource" href="${site.docker}" target="_blank" rel="noopener">${icon('docker', 16)}Docker 镜像</a>
            <a class="hub-resource" href="${site.issues}" target="_blank" rel="noopener">${icon('prompt', 16)}问题反馈</a>
          </div>
        </section>
        <p class="doc-deck" style="margin-top:36px;font-size:12.5px">文档基于 PenShot ${site.version} 源码整理，功能、接口与默认值可能随版本变化；生产使用前请以仓库当前代码与 Release 记录为准。</p>
      </div>
    </div>
  </main>
${docsFooter()}`;

  fs.writeFileSync(path.join(outDir, 'index.html'), page, 'utf8');
  return { canonical, title, description };
}

/* -------------------------------------------------------------- search index */

function buildSearchIndex(renderedDocs) {
  const entries = [];
  for (const entry of docOrder) {
    const doc = docs[entry.slug];
    const rendered = renderedDocs.get(entry.slug);
    const metaInfo = meta[entry.slug];
    entries.push({
      t: doc.title,
      s: doc.deck,
      c: entry.category.name,
      u: `${entry.slug}.html`,
      x: (metaInfo.description || doc.deck).slice(0, 160),
      f: doc.featured ? 1 : 0,
    });
    rendered.toc.forEach((heading) => {
      entries.push({
        t: doc.title,
        s: doc.deck,
        c: entry.category.name,
        u: `${entry.slug}.html#${heading.id}`,
        h: heading.text,
        x: rendered.excerptMap.get(heading.id) || doc.deck,
      });
    });
  }
  fs.writeFileSync(
    path.join(outDir, 'search-index.json'),
    JSON.stringify(entries),
    'utf8'
  );
  console.log(`search-index.json: ${entries.length} entries`);
}

/* --------------------------------------------------------------- sitemaps */

function writeSitemaps(renderedDocs) {
  const url = (loc, lastmod) => `  <url><loc>${loc}</loc><lastmod>${lastmod}</lastmod></url>`;
  const docsEntries = docOrder
    .map((entry) => url(`${site.url}/docs/${entry.slug}.html`, meta[entry.slug].updated || today))
    .join('\n');

  const rootSitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${url(`${site.url}/`, today)}
${url(`${site.url}/docs/`, today)}
${docsEntries}
</urlset>
`;
  fs.writeFileSync(path.join(root, 'sitemap.xml'), rootSitemap, 'utf8');

  fs.writeFileSync(
    path.join(root, 'robots.txt'),
    `User-agent: *\nAllow: /\n\nSitemap: ${site.url}/sitemap.xml\n`,
    'utf8'
  );
  console.log('sitemap + robots written');
}

/* ------------------------------------------------------------------- build */

const rendered = new Map();
for (const entry of docOrder) {
  rendered.set(entry.slug, renderDoc(entry.slug));
  console.log(`docs/${entry.slug}.html`);
}

const extra = Object.keys(meta).filter((slug) => !docs[slug]);
if (extra.length) {
  console.warn(`unlisted content slugs: ${extra.join(', ')}`);
}

renderHub();
console.log('docs/index.html (hub)');
buildSearchIndex(rendered);
writeSitemaps(rendered);
console.log(`\nBuilt ${docOrder.length} docs pages + hub`);
