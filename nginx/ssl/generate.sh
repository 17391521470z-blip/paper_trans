#!/usr/bin/env bash
set -euo pipefail
set -o pipefail

CERTS_DIR="$(cd "$(dirname "$0")/../certs" && pwd)"
mkdir -p "$CERTS_DIR"

print_usage() {
    cat <<EOF
Usage: $(basename "$0") [mode] [domain]

Modes:
  selfsign         Generate a self-signed certificate (for testing/staging)
  letsencrypt      Print Let's Encrypt instructions (for production)

Examples:
  ./$(basename "$0") selfsign
  ./$(basename "$0") selfsign localhost
  ./$(basename "$0") letsencrypt yourdomain.com
EOF
    exit 0
}

if [ $# -lt 1 ]; then
    print_usage
fi

MODE="$1"
DOMAIN="${2:-localhost}"

case "$MODE" in
    selfsign)
        echo "[INFO] Generating self-signed certificate for domain: $DOMAIN"
        echo "[INFO] Output directory: $CERTS_DIR"

        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "$CERTS_DIR/privkey.pem" \
            -out "$CERTS_DIR/fullchain.pem" \
            -subj "/CN=$DOMAIN" \
            -addext "subjectAltName=DNS:$DOMAIN,DNS:localhost,IP:127.0.0.1" 2>/dev/null

        chmod 600 "$CERTS_DIR/privkey.pem"

        echo "[OK] Self-signed certificate generated:"
        echo "     Private key: $CERTS_DIR/privkey.pem"
        echo "     Certificate: $CERTS_DIR/fullchain.pem"
        echo ""
        echo "[INFO] For production, use Let's Encrypt instead:"
        echo "  ./$(basename "$0") letsencrypt yourdomain.com"
        ;;

    letsencrypt)
        if [ "$DOMAIN" = "localhost" ]; then
            echo "[ERROR] Please provide a real domain name for Let's Encrypt."
            echo "  Example: ./$(basename "$0") letsencrypt yourdomain.com"
            exit 1
        fi

        cat <<EOF
===========================================
 Let's Encrypt 生产证书安装指南
===========================================

前置条件：
  - 域名 $DOMAIN 已解析到本服务器 IP
  - 端口 80 和 443 已开放
  - Nginx 已安装并运行

步骤 1：安装 Certbot
  Ubuntu/Debian:
    sudo apt-get update
    sudo apt-get install -y certbot python3-certbot-nginx

  CentOS/RHEL:
    sudo yum install -y epel-release
    sudo yum install -y certbot python3-certbot-nginx

步骤 2：获取证书
  sudo certbot --nginx -d $DOMAIN

  或使用 standalone 模式（无需 Nginx）：
  sudo certbot certonly --standalone -d $DOMAIN

步骤 3：复制证书到项目目录
  mkdir -p $CERTS_DIR
  sudo cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem $CERTS_DIR/
  sudo cp /etc/letsencrypt/live/$DOMAIN/privkey.pem $CERTS_DIR/
  sudo chmod 600 $CERTS_DIR/privkey.pem

步骤 4：配置自动续期
  # Certbot 会自动添加 systemd timer
  # 测试续期：
  sudo certbot renew --dry-run

  # 续期后自动复制证书到项目目录：
  cat <<'REHOOK' | sudo tee /etc/letsencrypt/renewal-hooks/post/copy-to-paper-translate.sh
#!/bin/bash
CERTS_DIR=$CERTS_DIR
mkdir -p \$CERTS_DIR
cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem \$CERTS_DIR/
cp /etc/letsencrypt/live/$DOMAIN/privkey.pem \$CERTS_DIR/
chmod 600 \$CERTS_DIR/privkey.pem
docker exec paper-translate-nginx nginx -s reload
REHOOK
  sudo chmod +x /etc/letsencrypt/renewal-hooks/post/copy-to-paper-translate.sh

===========================================
EOF
        ;;

    *)
        print_usage
        ;;
esac
