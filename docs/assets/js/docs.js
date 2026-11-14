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
  const iconExpand =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/><path d="M8 21H5a2 2 0 0 1-2-2v-3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>';
  const iconClose =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';

  let zoom = null;

  const buildZoom = () => {
    const root = document.createElement('div');
    root.className = 'diagram-zoom';
    root.hidden = true;
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-label', '图表放大查看');
    root.innerHTML = `
      <div class="diagram-zoom__panel">
        <header class="diagram-zoom__bar">
          <span class="diagram-zoom__title"></span>
          <div class="diagram-zoom__tools">
            <button type="button" data-zoom-action="out" aria-label="缩小">−</button>
            <span class="diagram-zoom__level" aria-live="polite">100%</span>
            <button type="button" data-zoom-action="in" aria-label="放大">+</button>
            <button type="button" data-zoom-action="fit" aria-label="适应窗口">适应</button>
            <button type="button" class="diagram-zoom__close" data-zoom-action="close" aria-label="关闭">${iconClose}</button>
          </div>
        </header>
        <div class="diagram-zoom__viewport">
          <div class="diagram-zoom__stage"></div>
        </div>
        <p class="diagram-zoom__hint">滚轮或双指缩放 · 拖拽平移 · 双击复位 · Esc 关闭</p>
      </div>`;
    document.body.appendChild(root);

    const panel = $('.diagram-zoom__panel', root);
    const viewport = $('.diagram-zoom__viewport', root);
    const stage = $('.diagram-zoom__stage', root);
    const level = $('.diagram-zoom__level', root);
    const title = $('.diagram-zoom__title', root);

    const state = {
      scale: 1,
      tx: 0,
      ty: 0,
      fit: 1,
      min: 0.05,
      max: 8,
      width: 0,
      height: 0,
      pointers: new Map(),
      lastPinch: 0,
      dragging: false,
    };
    let lastFocus = null;

    const boxRect = () => viewport.getBoundingClientRect();

    const paint = (animate) => {
      stage.style.transition = animate
        ? 'transform 180ms cubic-bezier(0.2, 0.7, 0.2, 1)'
        : 'none';
      stage.style.transform = `translate(${state.tx}px, ${state.ty}px) scale(${state.scale})`;
      level.textContent = `${Math.round((state.scale / state.fit) * 100)}%`;
    };

    const fit = (animate) => {
      const box = boxRect();
      state.scale = Math.min(box.width / state.width, box.height / state.height) * 0.94 || 1;
      state.fit = state.scale;
      state.min = state.fit * 0.5;
      state.max = Math.max(state.fit * 10, 4);
      state.tx = (box.width - state.width * state.scale) / 2;
      state.ty = (box.height - state.height * state.scale) / 2;
      paint(animate);
    };

    const zoomAt = (clientX, clientY, next) => {
      const scale = Math.min(state.max, Math.max(state.min, next));
      if (!Number.isFinite(scale) || scale === state.scale) return;
      const box = boxRect();
      const x = clientX - box.left;
      const y = clientY - box.top;
      const k = scale / state.scale;
      state.tx = x - (x - state.tx) * k;
      state.ty = y - (y - state.ty) * k;
      state.scale = scale;
      paint(false);
    };

    const zoomCenter = (factor) => {
      const box = boxRect();
      zoomAt(box.left + box.width / 2, box.top + box.height / 2, state.scale * factor);
    };

    const pinchDistance = () => {
      const [a, b] = Array.from(state.pointers.values());
      return Math.hypot(a.x - b.x, a.y - b.y);
    };

    const pinchMidpoint = () => {
      const [a, b] = Array.from(state.pointers.values());
      return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    };

    const refit = () => {
      const box = boxRect();
      const ratio = state.fit ? state.scale / state.fit : 1;
      const nextFit =
        Math.min(box.width / state.width, box.height / state.height) * 0.94 || 1;
      state.fit = nextFit;
      state.min = nextFit * 0.5;
      state.max = Math.max(nextFit * 10, 4);
      state.scale = Math.min(state.max, Math.max(state.min, nextFit * ratio));
      state.tx = (box.width - state.width * state.scale) / 2;
      state.ty = (box.height - state.height * state.scale) / 2;
      paint(false);
    };

    const open = (node, heading) => {
      const source = node.querySelector('svg');
      if (!source) return;
      const viewBox = source.viewBox && source.viewBox.baseVal;
      const rect = source.getBoundingClientRect();
      const width = (viewBox && viewBox.width) || rect.width;
      const height = (viewBox && viewBox.height) || rect.height;
      if (!width || !height) return;

      const clone = source.cloneNode(true);
      clone.removeAttribute('style');
      clone.setAttribute('width', width);
      clone.setAttribute('height', height);
      clone.style.width = `${width}px`;
      clone.style.height = `${height}px`;
      clone.style.maxWidth = 'none';
      clone.style.display = 'block';

      state.width = width;
      state.height = height;
      state.pointers.clear();
      state.lastPinch = 0;
      state.dragging = false;
      viewport.classList.remove('is-dragging');
      stage.replaceChildren(clone);
      title.textContent = heading || '图表';
      root.hidden = false;
      document.body.classList.add('no-scroll');
      lastFocus = document.activeElement;

      let frame = 0;
      const start = () => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => {
          fit(false);
          $('.diagram-zoom__close', root).focus({ preventScroll: true });
        });
      };
      start();
    };

    const close = () => {
      if (root.hidden) return;
      root.hidden = true;
      stage.replaceChildren();
      state.pointers.clear();
      state.dragging = false;
      viewport.classList.remove('is-dragging');
      document.body.classList.remove('no-scroll');
      if (lastFocus && typeof lastFocus.focus === 'function') {
        lastFocus.focus({ preventScroll: true });
      }
      lastFocus = null;
    };

    const trapFocus = (event) => {
      const items = $$(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        panel
      ).filter((el) => !el.disabled && el.offsetParent !== null);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    root.querySelector('[data-zoom-action="in"]').addEventListener('click', () => zoomCenter(1.25));
    root.querySelector('[data-zoom-action="out"]').addEventListener('click', () => zoomCenter(1 / 1.25));
    root.querySelector('[data-zoom-action="fit"]').addEventListener('click', () => fit(true));
    root.querySelector('[data-zoom-action="close"]').addEventListener('click', close);

    root.addEventListener('click', (event) => {
      if (event.target === root) close();
    });

    root.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
      } else if (event.key === '+' || event.key === '=') {
        event.preventDefault();
        zoomCenter(1.25);
      } else if (event.key === '-' || event.key === '_') {
        event.preventDefault();
        zoomCenter(1 / 1.25);
      } else if (event.key === '0') {
        event.preventDefault();
        fit(true);
      } else if (event.key === 'Tab') {
        trapFocus(event);
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !root.hidden) close();
    });

    viewport.addEventListener(
      'wheel',
      (event) => {
        event.preventDefault();
        zoomAt(event.clientX, event.clientY, state.scale * Math.exp(-event.deltaY * 0.0015));
      },
      { passive: false }
    );

    viewport.addEventListener('pointerdown', (event) => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      event.preventDefault();
      try {
        viewport.setPointerCapture(event.pointerId);
      } catch (error) {
        /* synthetic or stale pointers cannot be captured; dragging still works */
      }
      state.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (state.pointers.size === 1) {
        state.dragging = true;
        viewport.classList.add('is-dragging');
      } else if (state.pointers.size === 2) {
        state.dragging = false;
        state.lastPinch = pinchDistance();
      }
    });

    viewport.addEventListener('pointermove', (event) => {
      if (!state.pointers.has(event.pointerId)) return;
      const previous = state.pointers.get(event.pointerId);
      state.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

      if (state.pointers.size >= 2) {
        const distance = pinchDistance();
        if (state.lastPinch > 0 && distance > 0) {
          const mid = pinchMidpoint();
          zoomAt(mid.x, mid.y, state.scale * (distance / state.lastPinch));
        }
        state.lastPinch = distance;
        return;
      }

      if (!state.dragging) return;
      state.tx += event.clientX - previous.x;
      state.ty += event.clientY - previous.y;
      paint(false);
    });

    const endPointer = (event) => {
      state.pointers.delete(event.pointerId);
      if (state.pointers.size < 2) state.lastPinch = 0;
      if (state.pointers.size === 0) {
        state.dragging = false;
        viewport.classList.remove('is-dragging');
      }
    };
    viewport.addEventListener('pointerup', endPointer);
    viewport.addEventListener('pointercancel', endPointer);

    viewport.addEventListener('dblclick', (event) => {
      event.preventDefault();
      if (state.scale > state.fit * 1.05) {
        fit(true);
      } else {
        zoomAt(event.clientX, event.clientY, state.fit * 2.5);
      }
    });

    window.addEventListener('resize', () => {
      if (!root.hidden) refit();
    });

    return { open, close };
  };

  const nearestHeading = (node) => {
    let el = node.previousElementSibling;
    while (el) {
      if (/^H[2-4]$/.test(el.tagName)) {
        return el.textContent.replace(/#$/, '').trim() || '图表';
      }
      el = el.previousElementSibling;
    }
    return '图表';
  };

  const setupDiagrams = (nodes) => {
    nodes.forEach((node) => {
      if (node.dataset.zoomReady || !node.querySelector('svg')) return;
      node.dataset.zoomReady = 'true';
      node.classList.add('is-zoomable');
      node.setAttribute('tabindex', '0');
      node.setAttribute('role', 'button');
      node.setAttribute('aria-label', '点击放大查看图表');

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'diagram-expand';
      button.innerHTML = iconExpand + '<span>全屏</span>';
      button.setAttribute('aria-label', '全屏查看图表');
      node.appendChild(button);

      const openZoom = () => {
        if (!zoom) zoom = buildZoom();
        zoom.open(node, nearestHeading(node));
      };
      button.addEventListener('click', (event) => {
        event.stopPropagation();
        openZoom();
      });
      node.addEventListener('click', (event) => {
        if (event.target.closest('.diagram-expand')) return;
        openZoom();
      });
      node.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          openZoom();
        }
      });
    });
  };

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
      .then(() => setupDiagrams(mermaidNodes))
      .catch((error) => {
        console.warn('Mermaid failed to render:', error);
      });
  }
})();
