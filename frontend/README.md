# zhitouagent Frontend

智能投研助手前端，基于 Vue 3、TypeScript、Vite 和 Element Plus。

## 环境要求

- Node.js >= 18.0.0
- Yarn 1.x

## 开发

```bash
yarn install
yarn dev
```

## 构建

```bash
yarn type-check
yarn build
```

生产环境通过 Nginx 同源代理后端 API，不依赖跨域配置。
