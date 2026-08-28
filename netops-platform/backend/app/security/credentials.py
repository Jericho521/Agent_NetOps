"""
凭据加密/解密模块 - AES-256-GCM
- 密钥从环境变量 CREDENTIALS_KEY 读取（Base64 编码的 32 字节随机值）
- 所有 SNMP community/v3 密码必须加密后存库，禁止明文落盘
"""
import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import settings


def _get_encryption_key() -> bytes:
    """
    获取 AES-256 加密密钥（原始字节）。
    从 CREDENTIALS_KEY 环境变量（Base64 编码的 32 字节随机值）解码。
    """
    key_b64 = settings.credentials_key
    if not key_b64:
        raise ValueError(
            "CREDENTIALS_KEY 未设置！请在 .env 文件中配置。"
            "\n生成方式: python -c \"import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())\""
        )
    raw = base64.urlsafe_b64decode(key_b64)
    if len(raw) != 32:
        raise ValueError(f"CREDENTIALS_KEY 长度错误：需要 32 字节，当前 {len(raw)} 字节")
    return raw


def encrypt_credential(plaintext: str) -> str:
    """
    加密凭据明文 → 返回 Base64 编码的密文（含 nonce + ciphertext + tag）

    Args:
        plaintext: 明文字符串（如 SNMP community、认证密码等）

    Returns:
        Base64 编码的加密结果，可直接存入数据库 secret_enc 字段
    """
    if not plaintext:
        return ""
    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # GCM 推荐 nonce 长度 12 字节
    encrypted = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # 将 nonce + 密文一起 Base64 编码（解密时需要 nonce）
    return base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def decrypt_credential(encrypted_b64: str) -> str:
    """
    解密密文 → 返回明文字符串

    Args:
        encrypted_b64: encrypt_credential() 输出的 Base64 编码密文

    Returns:
        原始明文字符串
    """
    if not encrypted_b64:
        return ""
    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    raw = base64.urlsafe_b64decode(encrypted_b64)
    nonce, ciphertext = raw[:12], raw[12:]
    decrypted = aesgcm.decrypt(nonce, ciphertext, None)
    return decrypted.decode("utf-8")
