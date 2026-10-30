export const site = {
  name: 'PenShot',
  cnName: '剧本分镜智能体',
  tagline: '把剧本变成连贯的 AI 视频分镜',
  description:
    'PenShot 是一个基于 LangGraph 的开源剧本分镜智能体。自动解析剧本、拆分镜头、切割片段并生成中英双语视频提示词，输出可直接投喂 Sora、Veo、Runway、可灵的 5 秒级分镜脚本。',
  url: 'https://shot.helpenx.com',
  version: 'v0.3.x',
  license: 'MIT',
  repo: 'https://github.com/neopen/story-shot-agent',
  repoEdit:
    'https://github.com/neopen/story-shot-agent/edit/gh-pages/docs/content/docs/',
  pypi: 'https://pypi.org/project/penshot/',
  docker: 'https://hub.docker.com/r/neotems/penshot',
  issues: 'https://github.com/neopen/story-shot-agent/issues',
  blog: 'https://pengline.cn',
  email: 'helpenx@gmail.com',
};

export const categories = [
  {
    id: 'start',
    name: '开始使用',
    desc: '安装、配置，跑通第一个分镜任务',
    icon: 'rocket',
    docs: ['overview', 'quick-start', 'dev-guide'],
  },
  {
    id: 'core',
    name: '核心设计',
    desc: '工作流、节点、一致性、检查点与核心实现',
    icon: 'layers',
    docs: [
      'architecture',
      'nodes',
      'consistency',
      'checkpoint',
      'core-implementation',
      'dev-guide',
    ],
  },
  {
    id: 'integration',
    name: '集成与接口',
    desc: 'Python SDK、REST 与 MCP 接入',
    icon: 'plug',
    docs: ['integration', 'mcp'],
  },
  {
    id: 'retrieval',
    name: '检索与记忆',
    desc: '三层记忆、RAG 知识库与检索链路',
    icon: 'database',
    docs: ['memory', 'rag-knowledge-base'],
  },
];

export const docs = {
  overview: {
    title: '项目概览',
    deck: '一个基于 LangGraph 的多智能体系统：把任意长度的剧本拆成 5 秒级、视觉连贯的视频片段脚本。',
    featured: true,
  },
  'quick-start': {
    title: '快速开始',
    deck: '从安装、配置到跑通第一个分镜任务，完整走一遍最小可用链路。',
    featured: true,
  },
  'dev-guide': {
    title: '开发指南',
    deck: '理解双启动链、双层状态机与二次开发扩展点，把 PenShot 接进自己的工程。',
  },
  architecture: {
    title: '技术架构',
    deck: '十个节点、决策路由与三级循环防护：PenShot 如何把一条剧本变成可执行的分镜流水线。',
    featured: true,
  },
  nodes: {
    title: '工作流节点',
    deck: '逐个拆解六大智能体节点：输入、规则、LLM 调用与失败降级。',
  },
  consistency: {
    title: '一致性策略',
    deck: '三层记忆、快照与连续性检查，如何压制跨片段的角色与场景漂移。',
  },
  checkpoint: {
    title: '检查点与恢复',
    deck: '状态如何落盘、任务如何恢复，以及当前版本的能力边界。',
  },
  'core-implementation': {
    title: '核心实现',
    deck: 'LLM 客户端、提示词管理、循环控制与任务调度的实现要点。',
  },
  integration: {
    title: '集成指南',
    deck: 'Python SDK、REST API、MCP 与 LangGraph/A2A 的接入方式。',
    featured: true,
  },
  mcp: {
    title: 'MCP 服务',
    deck: '七个工具、双传输与 Claude Desktop / Cursor 客户端配置。',
  },
  memory: {
    title: '记忆系统',
    deck: '短期、中期、长期三层记忆的写入、召回、降级与已知边界。',
  },
  'rag-knowledge-base': {
    title: '知识库与检索',
    deck: 'RAG 知识库、分块、向量检索与重排序的当前实现。',
  },
};

export const iconPaths = {
  rocket:
    '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09Z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2Z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>',
  layers:
    '<path d="m12 2 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/>',
  plug:
    '<path d="M12 22v-5"/><path d="M9 8V2"/><path d="M15 8V2"/><path d="M18 8v5a6 6 0 0 1-12 0V8Z"/>',
  database:
    '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/><path d="M4 11v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6"/>',
  chart:
    '<path d="M3 3v18h18"/><path d="M7 15v3"/><path d="M12 10v8"/><path d="M17 6v12"/>',
  book:
    '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/>',
  search:
    '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  menu:
    '<path d="M4 7h16M4 12h16M4 17h16"/>',
  list:
    '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>',
  home:
    '<path d="m3 10 9-8 9 8"/><path d="M5 9v12h14V9"/><path d="M9 21v-6h6v6"/>',
  arrowRight:
    '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
  arrowLeft:
    '<path d="M19 12H5"/><path d="m11 18-6-6 6-6"/>',
  arrowUp:
    '<path d="M12 19V5"/><path d="m6 11 6-6 6 6"/>',
  arrowUpRight:
    '<path d="M7 17 17 7"/><path d="M7 7h10v10"/>',
  chevronRight:
    '<path d="m9 18 6-6-6-6"/>',
  check:
    '<path d="m20 6-11 11-5-5"/>',
  clock:
    '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  calendar:
    '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/>',
  edit:
    '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  github:
    '<path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5a5.4 5.4 0 0 0-1.5-3.8 5 5 0 0 0-.1-3.7s-1.2-.4-4 1.5a13.4 13.4 0 0 0-7 0C4.6 1.6 3.4 2 3.4 2a5 5 0 0 0-.1 3.7A5.4 5.4 0 0 0 2 9.5c0 3.5 3 5.5 6 5.5a4.8 4.8 0 0 0-1 3.5v4"/><path d="M9 18c-3 1-3-1.5-4-2"/>',
  star:
    '<path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8-6.2-3.3L5.8 21 7 14.2 2 9.3l6.9-1L12 2Z"/>',
  package:
    '<path d="m12 2 9 5v10l-9 5-9-5V7Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
  docker:
    '<path d="M4 12h3V9H4v3Zm4 0h3V9H8v3Zm0-4h3V5H8v3Zm4 4h3V9h-3v3Zm0-4h3V5h-3v3Zm4 4h3V9h-3v3Z"/><path d="M3 16c1.5 4 4.5 5 8.5 5 5 0 8-2.5 9.5-7-1.5 0-2.5.5-3 1-1-1-2.5-1.5-4-1.5"/>',
  mail:
    '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  terminal:
    '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/>',
  cpu:
    '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
  gitBranch:
    '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="6" r="3"/><path d="M6 9v6"/><path d="M18 9c0 3-3 3-6 3H6"/>',
  shield:
    '<path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3Z"/><path d="m9 12 2 2 4-4"/>',
  split:
    '<path d="M12 3v18"/><path d="m8 7-4 5 4 5"/><path d="m16 7 4 5-4 5"/>',
  prompt:
    '<path d="M4 5h16v12H8l-4 4V5Z"/><path d="M8 9h8M8 13h5"/>',
  memory:
    '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 9h6v6H9z"/><path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2"/>',
  globe:
    '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.5 2.6 3.8 5.7 3.8 9S14.5 18.4 12 21c-2.5-2.6-3.8-5.7-3.8-9S9.5 5.6 12 3Z"/>',
  x:
    '<path d="M6 6l12 12M18 6 6 18"/>',
  spark:
    '<path d="m12 2 1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2Z"/><path d="M19 16v4M17 18h4"/>',
  route:
    '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.5 6H15a3 3 0 0 1 3 3v2a3 3 0 0 1-3 3H9a3 3 0 0 0-3 3v.5"/>',
  refresh:
    '<path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/>',
  info:
    '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  code:
    '<path d="m8 6-6 6 6 6"/><path d="m16 6 6 6-6 6"/>',
  link:
    '<path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.2 1.2"/><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.2-1.2"/>',
};

export function icon(name, size = 16) {
  const path = iconPaths[name] || iconPaths.info;
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
}

export const docOrder = categories.flatMap((category) =>
  category.docs.map((slug) => ({ slug, category }))
);

export function findDoc(slug) {
  return docs[slug] ? { slug, ...docs[slug] } : null;
}

export function categoryOf(slug) {
  return categories.find((category) => category.docs.includes(slug)) || null;
}
