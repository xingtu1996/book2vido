# 06 · 发布自动化（可选）

## 角色
把成片一键发到公众号 / 视频号 / 小红书。

## 选型
- **UI-TARS-desktop**（`github.com/bytedance/UI-TARS`, 38k★）：字节开源桌面 GUI Agent，可自动化操作公众号后台上传封面 + 发文。
- **Midscene.js**：UI-TARS 配套的浏览器自动化，可做网页端发布。

## 接入
- 作为可选 publisher 模块，复用 `tools/batch_fetch_yuanbao.py` 同源的浏览器自动化思路。
- **注意**：个人主体小程序/公众号做音视频类目有资质限制（ICP / 网文证），发布自动化仅用于已合规账号。

## 合规
- 开源工具，零公司资源。发布动作需 boss 人工确认（不涉及自动群发）。
