/* PenShot documentation behaviour */
(function () {
  'use strict';

  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const $ = (sel, root) => (root || document).querySelector(sel);

  /* ------------------------------------------------------ mobile sidebar */
  const sidebar = $('[data-docs-sidebar]');
  const overlay = $('[data-sidebar-overlay]');
  const openBtn = $('[data-sidebar-open]');
  const closeBtn = $('[data-sidebar-close]');

  const setSidebar = (open) => {
    if (!sidebar) return;
    sidebar.classList.toggle('is-open', open);
    if (overlay) overlay.classList.toggle('is-open', open);
    if (openBtn) openBtn.setAttribute('aria-expanded', String(open));
    document.body.classList.toggle('no-scroll', open);
  };

  if (openBtn) openBtn.addEventListener('click', () => setSidebar(true));
  if (closeBtn) closeBtn.addEventListener('click', () => setSidebar(false));
  if (overlay) overlay.addEventListener('click', () => setSidebar(false));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setSidebar(false);
  });
  window.addEventListener('resize', () => {
    if (window.innerWidth > 1080) setSidebar(false);
  });

  /* ---------------------------------------------------- code copy buttons */
  const copyText = async (text) => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return true;
      }
      const area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      document.execCommand('copy');
      area.remove();
      return true;
    } catch (error) {
      return false;
    }
  };

  const iconCopy =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';

  $$('.doc-body pre').forEach((pre) => {
    if (pre.classList.contains('mermaid') || pre.closest('.pre-block')) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'pre-block';
    pre.parentNode.insertBefore(wrapper, pre);
    wrapper.appendChild(pre);

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'code-copy';
    button.innerHTML = iconCopy + '<span>复制</span>';
    button.setAttribute('aria-label', '复制代码');
    button.addEventListener('click', async () => {
      const ok = await copyText(pre.textContent);
      button.classList.toggle('is-copied', ok);
      button.querySelector('span').textContent = ok ? '已复制' : '失败';
      setTimeout(() => {
        button.classList.remove('is-copied');
        button.querySelector('span').textContent = '复制';
      }, 1800);
    });
    wrapper.appendChild(button);
  });

  /* ------------------------------------------------------- heading anchors */
  $$('.doc-body h2[id], .doc-body h3[id], .doc-body h4[id]').forEach((heading) => {
    const link = document.createElement('a');
    link.className = 'anchor';
    link.href = '#' + heading.id;
    link.setAttribute('aria-hidden', 'true');
    link.tabIndex = -1;
    link.textContent = '#';
    heading.appendChild(link);
  });

  /* ------------------------------------------------------------ scrollspy */
  const headings = $$('.doc-body h2[id], .doc-body h3[id]');
  const tocLinks = $$('.doc-toc a[href^="#"], .toc-mobile a[href^="#"]');

  if (headings.length && tocLinks.length) {
    const offset = () => {
      const header = document.querySelector('.site-header');
      return (header ? header.offsetHeight : 68) + 28;
    };

    let ticking = false;
    const update = () => {
      ticking = false;
      const line = offset();
      let current = null;
      for (const heading of headings) {
        if (heading.getBoundingClientRect().top <= line) current = heading.id;
        else break;
      }
      tocLinks.forEach((link) => {
        const active = current && link.getAttribute('href') === '#' + current;
        link.classList.toggle('is-active', Boolean(active));
      });
    };

    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(update);
    };

    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
  }

  /* ------------------------------------------------------------- mermaid */
  const mermaidNodes = $$('.doc-body pre.mermaid');
  if (mermaidNodes.length) {
    import('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs')
      .then(({ default: mermaid }) => {
        mermaid.initialize({
          startOnLoad: false,
          theme: 'neutral',
          securityLevel: 'loose',
          suppressErrors: true,
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
          flowchart: { useMaxWidth: true, htmlLabels: true, curve: 'basis' },
        });
        return mermaid.run({ nodes: mermaidNodes });
      })
      .catch((error) => {
        console.warn('Mermaid failed to render:', error);
      });
  }
})();
