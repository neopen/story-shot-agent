import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourceDir = path.join(root, 'docs');
const outDir = path.join(root, 'content', 'docs');

fs.mkdirSync(outDir, { recursive: true });

const files = fs.readdirSync(sourceDir).filter((f) => f.endsWith('.html') && f !== 'sitemap.xml');
const meta = {};

for (const file of files) {
  const slug = file === 'index.html' ? 'overview' : file.replace(/\.html$/, '');
  const html = fs.readFileSync(path.join(sourceDir, file), 'utf8');

  const article = html.match(/<article class="article">([\s\S]*?)<\/article>/);
  if (!article) {
    console.warn(`skip ${file}: no article block`);
    continue;
  }

  const title = (html.match(/<title>([\s\S]*?)<\/title>/) || [])[1] || '';
  const description = (html.match(/<meta name="description" content="([\s\S]*?)">/) || [])[1] || '';
  const updated = (html.match(/<span class="tag">更新 ([\d-]+)<\/span>/) || [])[1] || '2026-02-12';
  const h1 = (article[1].match(/<h1[^>]*>([\s\S]*?)<\/h1>/) || [])[1] || '';

  let body = article[1];
  body = body.replace(/<div class="doc-meta">[\s\S]*?<\/div>\s*/, '');
  body = body.replace(/<h1[^>]*>[\s\S]*?<\/h1>\s*/, '');
  body = body.replace(/<p>相关链接：[\s\S]*?<\/p>\s*/, '');
  body = body.replace(
    /<p><img src="\/imgs\/math\/image-20260914175909622\.png" alt="[^"]*"><\/p>/,
    () =>
      '<p>$$\\mathrm{MMR}=\\arg\\max_{d_i\\in D\\setminus S}\\left[\\lambda\\cdot\\mathrm{sim}(d_i,q)-(1-\\lambda)\\cdot\\max_{d_j\\in S}\\mathrm{sim}(d_i,d_j)\\right]$$</p>'
  );

  fs.writeFileSync(path.join(outDir, `${slug}.html`), body.trim() + '\n', 'utf8');

  meta[slug] = {
    title: title.replace(/\s*·\s*PenShot 文档\s*$/, '').trim(),
    h1: h1.replace(/<[^>]+>/g, '').trim(),
    description: description.trim(),
    updated,
  };
  console.log(`${slug}.html  ${(body.length / 1024).toFixed(1)} KB  ${updated}`);
}

fs.writeFileSync(path.join(outDir, 'meta.json'), JSON.stringify(meta, null, 2) + '\n', 'utf8');
console.log(`\nExtracted ${Object.keys(meta).length} documents to content/docs`);
