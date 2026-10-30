/* PenShot shared site behaviour */
(function () {
  'use strict';

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  /* ---------------------------------------------------------------- header */
  const header = $('.site-header');
  const onScroll = () => {
    if (!header) return;
    header.classList.toggle('is-scrolled', window.scrollY > 6);
  };
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });

  /* ------------------------------------------------------------ mobile nav */
  const menuToggle = $('[data-menu-toggle]');
  const mobileNav = $('[data-mobile-nav]');
  if (menuToggle && mobileNav) {
    const setOpen = (open) => {
      mobileNav.classList.toggle('is-open', open);
      menuToggle.setAttribute('aria-expanded', String(open));
      menuToggle.innerHTML = open
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6L6 18"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
    };
    menuToggle.addEventListener('click', () => {
      setOpen(!mobileNav.classList.contains('is-open'));
    });
    $$('a', mobileNav).forEach((a) => a.addEventListener('click', () => setOpen(false)));
    window.addEventListener('resize', () => {
      if (window.innerWidth > 900) setOpen(false);
    });
  }

  /* ---------------------------------------------------------------- tabs */
  $$('[data-tabs]').forEach((group) => {
    const tabs = $$('[role="tab"]', group);
    const panels = tabs
      .map((tab) => document.getElementById(tab.getAttribute('aria-controls')))
      .filter(Boolean);

    const activate = (index, focus) => {
      tabs.forEach((tab, i) => {
        const selected = i === index;
        tab.setAttribute('aria-selected', String(selected));
        tab.tabIndex = selected ? 0 : -1;
        if (selected && focus) tab.focus();
      });
      panels.forEach((panel, i) => {
        panel.hidden = i !== index;
      });
    };

    tabs.forEach((tab, i) => {
      tab.addEventListener('click', () => activate(i));
      tab.addEventListener('keydown', (event) => {
        if (!['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        let next = i;
        if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = (i + 1) % tabs.length;
        if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') next = (i - 1 + tabs.length) % tabs.length;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = tabs.length - 1;
        activate(next, true);
      });
    });

    activate(Math.max(0, tabs.findIndex((t) => t.getAttribute('aria-selected') === 'true')), false);
  });

  /* ---------------------------------------------------------------- copy */
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

  $$('[data-copy-target]').forEach((button) => {
    button.addEventListener('click', async () => {
      const target = document.querySelector(button.getAttribute('data-copy-target'));
      if (!target) return;
      const original = button.innerHTML;
      const ok = await copyText(target.textContent);
      button.textContent = ok ? '已复制' : '复制失败';
      setTimeout(() => {
        button.innerHTML = original;
      }, 1600);
    });
  });

  /* -------------------------------------------------------------- reveals */
  const revealItems = $$('[data-reveal]');
  if ('IntersectionObserver' in window && revealItems.length && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.08 }
    );
    revealItems.forEach((item) => observer.observe(item));
  } else {
    revealItems.forEach((item) => item.classList.add('is-visible'));
  }

  /* ------------------------------------------------------------ footer year */
  $$('[data-year]').forEach((el) => {
    el.textContent = String(new Date().getFullYear());
  });

  /* --------------------------------------------------------------- search */
  const indexUrl = document.body.getAttribute('data-search-index');
  const iconSearch =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>';
  const iconDoc =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/></svg>';

  if (!indexUrl) return;

  let overlay = null;
  let input = null;
  let resultsEl = null;
  let index = null;
  let loading = null;
  let activeIndex = -1;
  let rendered = [];

  const escapeHtml = (value) =>
    String(value).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

  const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  const highlight = (value, query) => {
    const safe = escapeHtml(value);
    if (!query) return safe;
    try {
      return safe.replace(new RegExp('(' + escapeRegExp(escapeHtml(query)) + ')', 'ig'), '<mark>$1</mark>');
    } catch (error) {
      return safe;
    }
  };

  const buildOverlay = () => {
    overlay = document.createElement('div');
    overlay.className = 'search-overlay';
    overlay.hidden = true;
    overlay.innerHTML =
      '<div class="search-dialog" role="dialog" aria-modal="true" aria-label="搜索文档">' +
      '<div class="search-field">' +
      iconSearch +
      '<input type="search" placeholder="搜索文档、节点、API 或关键词…" autocomplete="off" spellcheck="false" aria-label="搜索关键词">' +
      '<kbd>ESC</kbd>' +
      '</div>' +
      '<div class="search-results" role="listbox" aria-label="搜索结果"></div>' +
      '<div class="search-foot"><span><kbd>↑</kbd><kbd>↓</kbd> 选择</span><span><kbd>↵</kbd> 打开</span><span><kbd>esc</kbd> 关闭</span></div>' +
      '</div>';
    document.body.appendChild(overlay);
    input = $('input', overlay);
    resultsEl = $('.search-results', overlay);

    overlay.addEventListener('mousedown', (event) => {
      if (event.target === overlay) closeSearch();
    });
    input.addEventListener('input', () => render(input.value.trim()));
    input.addEventListener('keydown', onKeyDown);
    resultsEl.addEventListener('click', (event) => {
      if (event.target.closest('a')) closeSearch();
    });
  };

  const loadIndex = () => {
    if (index) return Promise.resolve(index);
    if (loading) return loading;
    loading = fetch(indexUrl, { credentials: 'same-origin' })
      .then((res) => {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then((data) => {
        index = Array.isArray(data) ? data : [];
        return index;
      })
      .catch(() => {
        index = [];
        return index;
      });
    return loading;
  };

  const absolute = (href) => {
    try {
      return new URL(href, new URL(indexUrl, window.location.href)).href;
    } catch (error) {
      return href;
    }
  };

  const render = (query) => {
    if (!resultsEl) return;
    const data = index || [];
    let items;
    if (!query) {
      items = data.filter((item) => item.f).slice(0, 6);
      if (!items.length) items = data.filter((item) => !item.h).slice(0, 6);
    } else {
      const q = query.toLowerCase();
      items = data
        .map((item) => {
          const title = (item.t || '').toLowerCase();
          const heading = (item.h || '').toLowerCase();
          const text = (item.x || '').toLowerCase();
          let score = 0;
          if (title.includes(q)) score += 12;
          if (heading.includes(q)) score += 8;
          if (text.includes(q)) score += 3;
          if ((item.c || '').toLowerCase().includes(q)) score += 2;
          if (score === 0) return null;
          if (!item.h) score += 1;
          return { item, score };
        })
        .filter(Boolean)
        .sort((a, b) => b.score - a.score || (a.item.h ? 1 : 0) - (b.item.h ? 1 : 0))
        .slice(0, 14)
        .map((entry) => entry.item);
    }

    rendered = items;
    activeIndex = items.length ? 0 : -1;

    if (!items.length) {
      resultsEl.innerHTML =
        '<div class="search-empty">没有找到与「' + escapeHtml(query) + '」相关的内容。<br>试试“MCP”“一致性”或“快速开始”。</div>';
      return;
    }

    const groupLabel = query ? '搜索结果' : '热门文档';
    let html = '<div class="search-group-label">' + groupLabel + '</div>';
    items.forEach((item, i) => {
      const title = item.h ? item.h : item.t;
      const context = item.h ? item.t : item.s || item.x || '';
      html +=
        '<a class="search-result' + (i === activeIndex ? ' is-active' : '') + '" href="' + escapeHtml(absolute(item.u)) + '" data-index="' + i + '">' +
        '<strong>' + iconDoc + highlight(title, query) + '</strong>' +
        '<small>' + highlight(context, query) + '</small>' +
        '</a>';
    });
    resultsEl.innerHTML = html;
  };

  const setActive = (next) => {
    const nodes = $$('.search-result', resultsEl);
    if (!nodes.length) return;
    activeIndex = (next + nodes.length) % nodes.length;
    nodes.forEach((node, i) => node.classList.toggle('is-active', i === activeIndex));
    const active = nodes[activeIndex];
    if (active) active.scrollIntoView({ block: 'nearest' });
  };

  const onKeyDown = (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive(activeIndex + 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive(activeIndex - 1);
    } else if (event.key === 'Enter') {
      const active = $('.search-result.is-active', resultsEl);
      if (active) {
        event.preventDefault();
        window.location.href = active.getAttribute('href');
      }
    } else if (event.key === 'Escape') {
      closeSearch();
    }
  };

  const openSearch = () => {
    if (!overlay) buildOverlay();
    overlay.hidden = false;
    document.body.classList.add('no-scroll');
    input.value = '';
    resultsEl.innerHTML = '<div class="search-empty">正在加载文档索引…</div>';
    loadIndex().then(() => render(''));
    setTimeout(() => input.focus(), 20);
  };

  const closeSearch = () => {
    if (!overlay) return;
    overlay.hidden = true;
    document.body.classList.remove('no-scroll');
    if (input) input.blur();
  };

  $$('[data-search-open]').forEach((trigger) => trigger.setAttribute('aria-haspopup', 'dialog'));

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && overlay && !overlay.hidden) closeSearch();
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if (overlay && !overlay.hidden) closeSearch();
      else openSearch();
    }
  });

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-search-open]');
    if (trigger) {
      event.preventDefault();
      openSearch();
    }
  });
})();
