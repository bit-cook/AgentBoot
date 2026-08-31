# Cloudflare Worker 部署

`cloudflare/worker.js` 为 `https://boot.ide.pub` 提供：

- `/`、`/en`：中英文产品页；
- `/assets/*`：与 Pages 共用的样式、交互与图标，按版本长期缓存；
- `/install.sh`、`/install.ps1`：当前 Release 安装器；
- `/rel/<asset>`：Release 资产代理，支持 `Range` / `If-Range`；
- `/health`：实际探测当前版本安装器、在线包与 SHA-256 旁车。

Worker 名称固定为 `boot`，配置见 `wrangler.jsonc`。部署只使用 Wrangler OAuth 或最小权限 API Token，不使用 Cloudflare Global API Key。

## 首次登录

```sh
npx wrangler login
npx wrangler whoami
```

浏览器授权应至少允许 Workers Scripts 与 Routes 写入，以及 Zone 读取。

## 发布

先确保 GitHub Release 与 Pages 已发布当前 `VERSION`，再执行：

```sh
cd cloudflare
sh deploy.sh
```

`deploy.sh` 会执行：

```sh
python3 ../scripts/sync-web-assets.py --check
npx wrangler deploy --config wrangler.jsonc
python3 ../scripts/verify-live-release.py
```

网页以 `pages/` 为唯一源。修改主页、404、CSS、JavaScript 或图标后，先在仓库根目录运行 `python3 scripts/sync-web-assets.py`。CI 与部署脚本会用 `--check` 阻止 Worker 和 Pages 内容漂移。

只有以下条件全部满足才算发布成功：

- `/health` 返回当前 tag 且 `ok=true`；
- Worker 与 Pages 的 `install.sh` / `install.ps1` 都指向当前 tag；
- 两个来源的在线 tar/zip 与各自 `.sha256` 一致；
- Worker `/rel/` 正确返回 `206 Partial Content`。

## 回滚

```sh
npx wrangler deployments list --name boot
npx wrangler rollback --name boot
python3 ../scripts/verify-live-release.py
```

回滚 Worker 后，验证器会按仓库当前 `VERSION` 检查。如果同时回滚 GitHub Release，需要先切换到对应源码/tag再运行验证。
