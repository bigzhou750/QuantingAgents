#!/usr/bin/env python3
"""
zhitouagent Gitee Webhook 接收器
接收 Gitee Push 事件，触发自动部署

用法:
    python3 webhook-server.py --secret YOUR_SECRET --deploy-script /path/to/deploy.sh [--port 9000] [--branch feat/assistant]

Gitee Webhook 配置:
    URL: http://your-server-ip:9000/webhook
    密码: 与 --secret 参数一致
    事件: Push
"""

import argparse
import hashlib
import hmac
import json
import logging
import subprocess
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class DeployWebhookHandler(BaseHTTPRequestHandler):
    """处理 Gitee Webhook 请求"""

    def do_POST(self):
        if self.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        # 读取请求体
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # 验证签名 (Gitee 使用 X-Gitee-Token)
        token = self.headers.get("X-Gitee-Token", "")
        if not self._verify_token(token):
            logger.warning("❌ Webhook 签名验证失败")
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden")
            return

        # 解析事件
        event = self.headers.get("X-Gitee-Event", "unknown")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.error("❌ 无法解析 JSON payload")
            self.send_response(400)
            self.end_headers()
            return

        # 只处理 Push 事件
        if event != "Push Hook":
            logger.info(f"⏭️  忽略非 Push 事件: {event}")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK (ignored)")
            return

        # 检查分支
        ref = payload.get("ref", "")
        target_branch = f"refs/heads/{self.server.deploy_branch}"
        if ref != target_branch:
            logger.info(f"⏭️  忽略非目标分支: {ref} (期望: {target_branch})")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK (wrong branch)")
            return

        # 提取推送信息
        pusher = payload.get("pusher", {}).get("name", "unknown")
        commits_count = len(payload.get("commits", []))
        head_commit = payload.get("head_commit", {})
        commit_msg = head_commit.get("message", "").split("\n")[0][:80]
        commit_id = head_commit.get("id", "")[:8]

        logger.info(f"📥 收到 Push: {pusher} → {ref}")
        logger.info(f"   提交: {commit_id} ({commits_count} commits) {commit_msg}")

        # 异步执行部署（避免阻塞 webhook 响应）
        threading.Thread(
            target=self._trigger_deploy,
            args=(commit_id, pusher, commit_msg),
            daemon=True,
        ).start()

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK (deploying)")

    def do_GET(self):
        """健康检查端点"""
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def _verify_token(self, token: str) -> bool:
        """验证 Gitee Webhook Token"""
        expected = self.server.webhook_secret
        if not expected:
            logger.warning("⚠️  未配置 webhook secret，跳过验证")
            return True
        return hmac.compare_digest(token, expected)

    def _trigger_deploy(self, commit_id: str, pusher: str, commit_msg: str):
        """触发部署脚本"""
        deploy_script = self.server.deploy_script
        branch = self.server.deploy_branch

        logger.info(f"🚀 触发部署: {deploy_script} {branch}")
        try:
            result = subprocess.run(
                ["bash", deploy_script, branch],
                capture_output=True,
                text=True,
                timeout=600,  # 10分钟超时
            )
            if result.returncode == 0:
                logger.info(f"✅ 部署成功 ({commit_id} by {pusher})")
            else:
                logger.error(f"❌ 部署失败 (exit code: {result.returncode})")
                logger.error(f"   stderr: {result.stderr[-500:]}")
        except subprocess.TimeoutExpired:
            logger.error("❌ 部署超时 (>10min)")
        except Exception as e:
            logger.error(f"❌ 部署异常: {e}")

    def log_message(self, format, *args):
        """重写日志输出到 logger"""
        logger.debug(f"{self.client_address[0]} - {format % args}")


def main():
    parser = argparse.ArgumentParser(description="zhitouagent Gitee Webhook Server")
    parser.add_argument("--port", type=int, default=9000, help="监听端口 (默认 9000)")
    parser.add_argument("--secret", required=True, help="Webhook 验证密钥")
    parser.add_argument("--deploy-script", required=True, help="部署脚本路径")
    parser.add_argument("--branch", default="feat/assistant", help="监听分支 (默认 feat/assistant)")
    args = parser.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), DeployWebhookHandler)
    server.webhook_secret = args.secret
    server.deploy_script = args.deploy_script
    server.deploy_branch = args.branch

    logger.info(f"🎧 Webhook 服务启动: 0.0.0.0:{args.port}")
    logger.info(f"   监听分支: {args.branch}")
    logger.info(f"   部署脚本: {args.deploy_script}")
    logger.info(f"   Secret: {'已配置' if args.secret else '未配置'}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("🛑 Webhook 服务停止")
        server.shutdown()


if __name__ == "__main__":
    main()
