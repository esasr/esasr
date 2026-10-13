# esasr-web

## 阅读布局与动效

- 导航、检索结果、详情页共用 1280px 内容网格及响应式左右留白。
- 桌面结果页使用吸顶筛选栏和排序工具栏；窄屏下筛选折叠，避免占用阅读区域。
- 详情页提供吸顶章节导航、阅读进度、平滑锚点与关联论文侧栏。页面使用原生滚动，不强制滚动吸附或正文视差。
- Morphicons 处理主题、筛选开合与收藏状态；Lordicon 提供按需加载的反馈插图，素材保存在 `public/icons/lordicon/`，来源与许可随素材保存，关于页提供署名。
- 动画遵循 `prefers-reduced-motion`；图标有固定尺寸与静态回退，卡片进入视口时仅轻微过渡，正文不会因脚本失败而隐藏。

```sh
npm run test:ui
npm run build
npm run preview:ui
```

`preview:ui` 在 `http://127.0.0.1:5173/search?q=UI-layout-test` 启动本地布局样例，
所有论文均标记为 UI 测试数据，不请求真实模型或学术 API，也不计入实验。
常规开发仍使用 `npm run dev`。请用 Chrome/Safari 检查 1440px、768px、390px 下的
筛选展开、结果到详情往返、章节吸顶、深色模式及系统减少动态效果设置。

This template should help get you started developing with Vue 3 in Vite.

## Recommended IDE Setup

[VS Code](https://code.visualstudio.com/) + [Vue (Official)](https://marketplace.visualstudio.com/items?itemName=Vue.volar) (and disable Vetur).

## Recommended Browser Setup

- Chromium-based browsers (Chrome, Edge, Brave, etc.):
  - [Vue.js devtools](https://chromewebstore.google.com/detail/vuejs-devtools/nhdogjmejiglipccpnnnanhbledajbpd)
  - [Turn on Custom Object Formatter in Chrome DevTools](http://bit.ly/object-formatters)
- Firefox:
  - [Vue.js devtools](https://addons.mozilla.org/en-US/firefox/addon/vue-js-devtools/)
  - [Turn on Custom Object Formatter in Firefox DevTools](https://fxdx.dev/firefox-devtools-custom-object-formatters/)

## Type Support for `.vue` Imports in TS

TypeScript cannot handle type information for `.vue` imports by default, so we replace the `tsc` CLI with `vue-tsc` for type checking. In editors, we need [Volar](https://marketplace.visualstudio.com/items?itemName=Vue.volar) to make the TypeScript language service aware of `.vue` types.

## Customize configuration

See [Vite Configuration Reference](https://vite.dev/config/).

## Project Setup

```sh
npm install
```

### Compile and Hot-Reload for Development

```sh
npm run dev
```

### Type-Check, Compile and Minify for Production

```sh
npm run build
```

## 论文关系图

### 本地真实接口联调

先在 `esasr-api` 中启动 `venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000`，再在本目录运行 `npm run dev`。开发服务器默认将 `/api` 和 `/health` 转发到本机 8000 端口；如设置 `VITE_API_BASE_URL`，则使用该显式地址。`npm run preview:ui` 仅用于界面样例，不用于真实检索验收。完整依赖健康检查需要 PostgreSQL、Redis 和 Neo4j 运行。

### 图谱交互

详情页采用 Vue Flow 自定义论文卡片，按参考文献、引用本文、相关研究分组。实线箭头保持“引用方 → 被引用方”的数据方向；相关关系采用无箭头虚线，不补造缺失题名或引用关系。支持关系筛选、卡片预览、缩放适配与浏览器全屏。滚轮保留页面滚动，使用工具栏或双指缩放画布；减少动态效果设置会关闭视口过渡。关系接口失败提供重试，切换论文时取消旧请求。
