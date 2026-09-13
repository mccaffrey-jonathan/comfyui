"""Signer configuration: certificate chain + private key from files, env vars or config."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("content_credentials")

PACK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(PACK_DIR, "config")
DEFAULT_CERT = os.path.join(CONFIG_DIR, "c2pa_cert_chain.pem")
DEFAULT_KEY = os.path.join(CONFIG_DIR, "c2pa_private_key.pem")
DEFAULT_ROOT = os.path.join(CONFIG_DIR, "c2pa_test_root.pem")

ENV_CERT = "C2PA_SIGN_CERT"          # PEM text or path
ENV_KEY = "C2PA_PRIVATE_KEY"         # PEM text or path
ENV_ALG = "C2PA_SIGNING_ALG"
ENV_TSA = "C2PA_TSA_URL"

ALGORITHMS = ("es256", "es384", "es512", "ps256", "ps384", "ps512", "ed25519")
DEFAULT_TSA = "http://timestamp.digicert.com"


class SignerError(RuntimeError):
    pass


def _read_pem_source(value: str, what: str) -> str:
    """Accept PEM text, ``env:NAME``, ``file:PATH`` or a plain path."""
    v = (value or "").strip()
    if not v:
        raise SignerError(f"{what} not configured")
    if v.startswith("env:"):
        got = os.environ.get(v[4:].strip(), "")
        if not got:
            raise SignerError(f"{what}: environment variable {v[4:].strip()!r} is not set")
        return _read_pem_source(got, what)
    if v.startswith("file:"):
        v = v[5:].strip()
    if "-----BEGIN" in v:
        return v.strip() + "\n"
    path = os.path.expanduser(v)
    if not os.path.isabs(path):
        cand = os.path.join(CONFIG_DIR, path)
        if os.path.exists(cand):
            path = cand
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().strip() + "\n"
    except OSError as exc:
        raise SignerError(f"{what}: cannot read {path!r}: {exc}") from exc


@dataclass
class SignerConfig:
    cert_chain_pem: str
    private_key_pem: str
    alg: str = "es256"
    tsa_url: Optional[str] = DEFAULT_TSA
    is_test_certificate: bool = False

    def subject(self) -> dict:
        """Best-effort subject / issuer info of the end-entity certificate."""
        try:
            from cryptography import x509

            cert = x509.load_pem_x509_certificates(self.cert_chain_pem.encode("utf-8"))[0]
            def _get(name, oid):
                vals = name.get_attributes_for_oid(oid)
                return vals[0].value if vals else None
            from cryptography.x509.oid import NameOID

            return {
                "common_name": _get(cert.subject, NameOID.COMMON_NAME),
                "organization": _get(cert.subject, NameOID.ORGANIZATION_NAME),
                "issuer": _get(cert.issuer, NameOID.COMMON_NAME),
                "not_after": cert.not_valid_after_utc.isoformat() if hasattr(cert, "not_valid_after_utc") else str(cert.not_valid_after),
                "serial": format(cert.serial_number, "x"),
            }
        except Exception as exc:  # pragma: no cover
            return {"error": str(exc)}


def load_signer_config(cert: str = "", key: str = "", alg: str = "", tsa_url: str = "",
                       generate_test_if_missing: bool = False, test_org: str = "ComfyUI Test",
                       ) -> SignerConfig:
    """Resolve the signer from widget values, environment, or the pack's config dir."""
    cert = cert or os.environ.get(ENV_CERT, "") or (DEFAULT_CERT if os.path.exists(DEFAULT_CERT) else "")
    key = key or os.environ.get(ENV_KEY, "") or (DEFAULT_KEY if os.path.exists(DEFAULT_KEY) else "")
    alg = (alg or os.environ.get(ENV_ALG, "") or "es256").lower()
    tsa = tsa_url if tsa_url is not None else ""
    tsa = tsa or os.environ.get(ENV_TSA, DEFAULT_TSA)
    if tsa.strip().lower() in ("", "none", "off"):
        tsa = None
    is_test = False
    if (not cert or not key):
        if generate_test_if_missing:
            from .certs import generate_test_chain

            paths = generate_test_chain(organization=test_org, common_name=f"{test_org} C2PA Signer",
                                        out_dir=CONFIG_DIR)
            cert, key = paths["cert_chain"], paths["private_key"]
            is_test = True
            log.warning("content_credentials: generated a self-issued TEST certificate chain in %s. "
                        "Manifests will validate as 'Valid' but not 'Trusted'. Obtain a certificate from a "
                        "C2PA-conformant CA for production.", CONFIG_DIR)
        else:
            raise SignerError(
                "No C2PA signing certificate/key configured. Provide cert_chain/private_key (path, PEM, "
                f"env:NAME or file:PATH), set {ENV_CERT}/{ENV_KEY}, place c2pa_cert_chain.pem and "
                f"c2pa_private_key.pem in {CONFIG_DIR}, or enable generate_test_certificate."
            )
    if alg not in ALGORITHMS:
        raise SignerError(f"unsupported algorithm {alg!r}; choose one of {ALGORITHMS}")
    cfg = SignerConfig(
        cert_chain_pem=_read_pem_source(cert, "certificate chain"),
        private_key_pem=_read_pem_source(key, "private key"),
        alg=alg, tsa_url=tsa, is_test_certificate=is_test or "FOR TESTING ONLY" in _read_pem_subject(cert),
    )
    return cfg


def _read_pem_subject(cert_source: str) -> str:
    try:
        from cryptography import x509

        pem = _read_pem_source(cert_source, "certificate chain")
        cert = x509.load_pem_x509_certificates(pem.encode("utf-8"))[0]
        return cert.subject.rfc4514_string()
    except Exception:
        return ""


def make_signer(cfg: SignerConfig):
    """Create a c2pa.Signer (local keys).  For HSM/KMS use c2pa.Signer.from_callback directly."""
    try:
        import c2pa
    except ImportError as exc:  # pragma: no cover
        raise SignerError("c2pa-python is not installed (pip install c2pa-python>=0.37)") from exc
    info = c2pa.C2paSignerInfo(
        alg=cfg.alg.encode("utf-8"),
        sign_cert=cfg.cert_chain_pem.encode("utf-8"),
        private_key=cfg.private_key_pem.encode("utf-8"),
        ta_url=cfg.tsa_url.encode("utf-8") if cfg.tsa_url else None,
    )
    return c2pa.Signer.from_info(info)
